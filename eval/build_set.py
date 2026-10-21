"""Build the perception eval set from the six real photos, deterministically.

    python eval/build_set.py            # writes eval/cases/*.jpg and eval/cases/manifest.json

Every case is (reference, evidence, zones, expects_change, earlier photos) plus the
decision the gate SHOULD reach, with its provenance:

* ``real``       — two of our own photos as taken (rights: fixtures/perception/scenes.json);
* ``synthetic``  — one of our photos through a named generator with fixed parameters and
                   seeds (stepspotter/perception/synthetic.py), so the ground truth is known
                   by construction and the bytes can be regenerated and checked (sha256).

No public dataset is used yet (none was licence-checked in time; see docs/PERCEPTION.md).

Split, by SCENE, never by case (fixtures/perception/scenes.json "split"): calibration =
the panel (01, 02, 03), test = the office jack and the dining node (04, 05, 06). No case
mixes photos from both halves. Consequence, stated rather than hidden: the calibration
half has no "different place" pairs, because all three of its photos are one panel.

The generated JPEGs are not committed (eval/cases/*.jpg is gitignored); the manifest is,
with a sha256 per file, so a rebuild on another machine can prove it made the same set.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stepspotter.perception import imgio, synthetic as S  # noqa: E402

SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())
PHOTOS: dict[str, dict] = SCENES["photos"]
#: Where the cases go. ``STEPSPOTTER_EVAL_CASES`` moves it (the tests build into a tmp dir).
CASES = Path(os.environ.get("STEPSPOTTER_EVAL_CASES") or (ROOT / "eval" / "cases"))
JPEG_Q = 92


def split_of(pid: str) -> str:
    scene = PHOTOS[pid]["scene"]
    return "calibration" if scene in SCENES["split"]["calibration"] else "test"


def zones(pid: str) -> list[dict]:
    return [dict(z) for z in PHOTOS[pid]["zones"]]


def box(pid: str, kind: str) -> tuple[float, float, float, float]:
    return tuple(next(z["box"] for z in PHOTOS[pid]["zones"] if z["kind"] == kind))  # type: ignore[return-value]


def load(pid: str) -> np.ndarray:
    return imgio.load(ROOT / PHOTOS[pid]["file"])


def part() -> np.ndarray:
    """The foreign part pasted into a zone: the yellow keystone cut from photo 04."""
    img = load("04")
    h, w = img.shape[:2]
    return img[int(0.38 * h) : int(0.80 * h), int(0.22 * w) : int(0.80 * w)].copy()


def _seed(pid: str, k: int) -> int:
    return int(pid) * 100 + k


#: class -> (expected decision, expects_change, generator(pid) -> (image, params, earlier))
#: ``earlier`` is a list of (name, image) photos the job had already seen.
Gen = Callable[[str], tuple[np.ndarray, dict, list[tuple[str, np.ndarray]]]]


def _g(fn: Callable[[str], tuple[np.ndarray, dict]]) -> Gen:
    def wrapped(pid: str):
        img, params = fn(pid)
        return img, params, []

    return wrapped


SYNTH: dict[str, tuple[str, bool | None, Gen]] = {
    # ---- good evidence: the gate must NOT block these
    "good_rotate": ("ok", None, _g(lambda p: (S.rotate(load(p), 8), {"rotate_deg": 8}))),
    "good_reshot": ("ok", None, _g(lambda p: (
        S.sensor_noise(S.perspective(load(p), 0.10, _seed(p, 1)), 3.0, _seed(p, 1)),
        {"perspective_k": 0.10, "noise_sigma": 3.0, "seed": _seed(p, 1)}))),
    # v2 (2026-10-21): a lamp from one side — a smooth gain ramp 0.85 -> 1.15 across the
    # frame, clipping only what was already near white. v1 (gain 1.15 +10, gamma 0.8)
    # clipped 7-31 % of the pixels of the brighter photos: those were overexposed photos
    # mislabelled as good (eval/results/opencv-run1-2026-10-21.md).
    "good_light": ("ok", None, _g(lambda p: (
        S.side_light(load(p), 0.85, 1.15), {"side_light": [0.85, 1.15], "version": 2,
                                           "new_clipped_frac": S.new_clipped(load(p), S.side_light(load(p), 0.85, 1.15))}))),
    "good_closeup": ("ok", None, _g(lambda p: (
        S.crop_around(load(p), box(p, "act"), 0.55), {"crop_around": "act zone", "min_frac": 0.55, "upscale": False}))),
    "good_act_edit": ("ok", True, _g(lambda p: (
        S.perspective(S.paste_patch(load(p), box(p, "act"), part(), cover=0.6, seed=_seed(p, 2)), 0.05, _seed(p, 2)),
        {"paste_into": "act zone", "cover": 0.6, "perspective_k": 0.05, "seed": _seed(p, 2)}))),
    # ---- bad evidence: quality
    "blur_gaussian": ("retake", None, _g(lambda p: (S.gaussian_blur(load(p), 3), {"sigma": 3}))),
    "blur_motion": ("retake", None, _g(lambda p: (S.motion_blur(load(p), 21, 30), {"length": 21, "angle_deg": 30}))),
    "dark": ("retake", None, _g(lambda p: (S.exposure(load(p), 0.12), {"gain": 0.12}))),
    "overexposed": ("retake", None, _g(lambda p: (S.exposure(load(p), 2.8, 50), {"gain": 2.8, "offset": 50}))),
    "glare": ("retake", None, _g(lambda p: (
        S.glare(load(p), 0.06, (box(p, "act")[0] + box(p, "act")[2]) / 2, (box(p, "act")[1] + box(p, "act")[3]) / 2),
        {"frac": 0.06, "centre": "act zone"}))),
    "zone_cut": ("retake", None, _g(lambda p: (S.cut_zone(load(p), box(p, "act"), 0.25), {"cut_zone": "act", "keep_frac": 0.25}))),
    # ---- bad evidence: replay
    "replay_reference": ("replay", True, _g(lambda p: (
        S.resize(S.jpeg(load(p), 70), 0.8), {"of": "reference", "jpeg_q": 70, "resize": 0.8}))),
    "replay_earlier": ("replay", None, lambda p: (
        S.rotate(S.resize(S.sensor_noise(S.perspective(load(p), 0.10, _seed(p, 3)), 3.0, _seed(p, 3)), 0.85), 1.5),
        {"of": "an earlier evidence photo (a re-shot)", "resize": 0.85, "rotate_deg": 1.5, "seed": _seed(p, 3)},
        [("earlier evidence", S.sensor_noise(S.perspective(load(p), 0.10, _seed(p, 3)), 3.0, _seed(p, 3)))],
    )),
    # ---- bad evidence: change
    "no_change": ("no_change", True, _g(lambda p: (
        S.sensor_noise(S.perspective(load(p), 0.10, _seed(p, 4)), 3.0, _seed(p, 4)),
        {"perspective_k": 0.10, "noise_sigma": 3.0, "seed": _seed(p, 4)}))),
    "touched_avoid": ("touched_avoid", None, _g(lambda p: (
        S.perspective(S.paste_patch(load(p), box(p, "avoid"), part(), cover=0.6, seed=_seed(p, 5)), 0.05, _seed(p, 5)),
        {"paste_into": "avoid zone", "cover": 0.6, "perspective_k": 0.05, "seed": _seed(p, 5)}))),
}

#: Real pairs of our own photos (reference id, evidence id, expected, why).
REAL: list[tuple[str, str, str, str]] = [
    ("02", "01", "ok", "the same panel, from across the room (real re-shot, another distance and angle)"),
    ("01", "02", "ok", "the same panel, closer (real re-shot)"),
    ("02", "03", "ok", "a close-up of the same panel's telecom module, taken at another time (cables moved)"),
    ("01", "03", "ok", "a close-up of the same panel's telecom module, from the overview"),
    ("04", "05", "ok", "the same wall jack, box opened and the jack pulled out (another view of the same place)"),
    ("04", "06", "wrong_place", "a different room: the dining node, not the office jack"),
    ("05", "06", "wrong_place", "a different room: the dining node, not the office wall box"),
    ("06", "04", "wrong_place", "a different room: the office jack, not the dining node"),
    ("06", "05", "wrong_place", "a different room: the office wall box, not the dining node"),
]

CLASS_KIND = {
    **{k: ("good" if v[0] == "ok" else "bad") for k, v in SYNTH.items()},
    "real_same_place": "good",
    "real_wrong_place": "bad",
}


def _rel(path: Path) -> str:
    """Repo-relative when inside the repo (the committed manifest), absolute otherwise."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _write(img: np.ndarray, rel: str) -> tuple[str, str]:
    path = CASES / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
    if not ok:
        raise RuntimeError(f"could not encode {rel}")
    data = buf.tobytes()
    path.write_bytes(data)
    return _rel(path), hashlib.sha256(data).hexdigest()


def _file_sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def build() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for pid in sorted(PHOTOS):
        meta = PHOTOS[pid]
        for cls, (expected, expects_change, gen) in SYNTH.items():
            img, params, earlier = gen(pid)
            cid = f"{pid}-{cls}"
            ev_rel, ev_sha = _write(img, f"{cid}.jpg")
            earlier_out = []
            for i, (name, eimg) in enumerate(earlier):
                rel, sha = _write(eimg, f"{cid}-earlier-{i}.jpg")
                earlier_out.append({"name": name, "path": rel, "sha256": sha, "accepted": False})
            cases.append(
                {
                    "id": cid,
                    "class": cls,
                    "kind": CLASS_KIND[cls],
                    "group": pid,
                    "scene": meta["scene"],
                    "split": split_of(pid),
                    "expected": expected,
                    "expects_change": expects_change,
                    "reference": meta["file"],
                    "reference_sha256": _file_sha(meta["file"]),
                    "evidence": ev_rel,
                    "evidence_sha256": ev_sha,
                    "earlier": earlier_out,
                    "zones": zones(pid),
                    "step": dict(meta["step"]),
                    "provenance": {
                        "kind": "synthetic",
                        "source": meta["name"],
                        "generator": f"stepspotter.perception.synthetic ({cls})",
                        "params": params,
                        "rights": "our own photo (scenes.json _rights)",
                    },
                }
            )
    for ref, ev, expected, why in REAL:
        if split_of(ref) != split_of(ev):  # never mix the halves
            raise ValueError(f"real pair {ref}->{ev} crosses the split")
        cls = "real_same_place" if expected == "ok" else "real_wrong_place"
        cases.append(
            {
                "id": f"{ref}-{cls}-{ev}",
                "class": cls,
                "kind": CLASS_KIND[cls],
                "group": ref,
                "scene": PHOTOS[ref]["scene"],
                "split": split_of(ref),
                "expected": expected,
                "expects_change": None,
                "reference": PHOTOS[ref]["file"],
                "reference_sha256": _file_sha(PHOTOS[ref]["file"]),
                "evidence": PHOTOS[ev]["file"],
                "evidence_sha256": _file_sha(PHOTOS[ev]["file"]),
                "earlier": [],
                "zones": zones(ref),
                "step": dict(PHOTOS[ref]["step"]),
                "provenance": {
                    "kind": "real",
                    "source": f"{PHOTOS[ref]['name']} -> {PHOTOS[ev]['name']}",
                    "why": why,
                    "rights": "our own photos (scenes.json _rights)",
                },
            }
        )
    return cases


def main() -> int:
    CASES.mkdir(parents=True, exist_ok=True)
    cases = build()
    manifest = {
        "_about": __doc__.strip().splitlines()[0],
        "_built_with": {"opencv": cv2.__version__, "numpy": np.__version__, "jpeg_quality": JPEG_Q},
        "_split": SCENES["_split"],
        "counts": {
            "cases": len(cases),
            "by_split": {s: sum(1 for c in cases if c["split"] == s) for s in ("calibration", "test")},
            "by_kind": {k: sum(1 for c in cases if c["kind"] == k) for k in ("good", "bad")},
        },
        "cases": cases,
    }
    (CASES / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"wrote {len(cases)} cases to {_rel(CASES)}/ "
          f"({manifest['counts']['by_split']}, {manifest['counts']['by_kind']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
