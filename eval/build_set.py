"""Build the perception eval set from the six real photos, deterministically.

    python eval/build_set.py            # writes eval/cases/*.jpg and eval/cases/manifest.json

Every case is (reference, evidence, zones, expects_change, earlier photos) plus the
decision the gate SHOULD reach, with its provenance:

* ``real``       — two of our own photos as taken (rights: fixtures/perception/scenes.json);
* ``synthetic``  — one of our photos through a named generator with fixed parameters and
                   seeds (stepspotter/perception/synthetic.py), so the ground truth is known
                   by construction and the bytes can be regenerated and checked (sha256).

* ``public``     — since 2026-10-21 (lane L2): Wikimedia Commons files of the same kinds of
                   scenes (licence read from the Commons API, CC0 / PD / CC BY / CC BY-SA)
                   and frames of Mikhail's own under-sink phone video (his consent), listed
                   with zones, steps, licence and sha256 in eval/cases/public/sources.json.
                   They give real "same place, another shot" pairs, real look-alikes of
                   another place, real blur, and synthetic damage on photos nobody tuned on.

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
    return cases + build_public()


# ============================================================ public sources (lane L2)

PUBLIC = ROOT / "eval" / "cases" / "public"
_SRC_PATH = PUBLIC / "sources.json"
PUB = json.loads(_SRC_PATH.read_text()) if _SRC_PATH.is_file() else {"sources": {}, "steps": {}}
SOURCES: dict[str, dict] = PUB["sources"]
SPLIT_SALT = "stepspotter-eval-split:"


def group_split(group: str) -> str:
    """Split of a public group: by a hash of the group name, fixed before any result."""
    return "calibration" if hashlib.sha256((SPLIT_SALT + group).encode()).digest()[0] < 128 else "test"


def _hseed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


def sticker(seed: int) -> np.ndarray:
    """A foreign part drawn by code (a coloured plastic block with a label and ribs), so a
    public photo's edit never borrows pixels from a photo in the other half of the split."""
    rng = np.random.default_rng(seed)
    colours = [(30, 200, 240), (200, 120, 30), (40, 40, 200), (60, 160, 60)]
    b, g, r = colours[int(rng.integers(len(colours)))]
    h, w = 150, 220
    ramp = np.linspace(0.75, 1.15, h, dtype=np.float32)[:, None, None]
    img = np.clip(np.ones((h, w, 3), np.float32) * np.array([b, g, r], np.float32) * ramp, 0, 255).astype(np.uint8)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (20, 20, 20), 6)
    cv2.rectangle(img, (40, 30), (180, 70), (245, 245, 245), -1)
    for i in range(4):
        y = 90 + i * 14
        cv2.line(img, (20, y), (200, y), (25, 25, 25), 4)
    return img


def _zone(src: dict, kind: str) -> tuple[float, float, float, float]:
    return tuple(next(z["box"] for z in src["zones"] if z["kind"] == kind))  # type: ignore[return-value]


def _centre(b) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def view_light(img: np.ndarray, seed: int) -> np.ndarray:
    """Another viewpoint AND another light: rotate 10 deg, zoom 1.15 about the centre,
    hand-held perspective 0.10, a side lamp 0.80 -> 1.15 and gamma 0.9."""
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 10, 1.15)
    out = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    out = S.perspective(out, 0.10, seed)
    return S.gamma(S.side_light(out, 0.80, 1.15), 0.9)


#: class -> (expected, expects_change, generator(img, src, seed) -> (img|None, params, earlier))
#: a generator returning None as the image means "the evidence IS the reference file".
PGen = Callable[[np.ndarray, dict, int], tuple[np.ndarray | None, dict, list[tuple[str, np.ndarray]]]]
PUB_SYNTH: dict[str, tuple[str, bool | None, PGen]] = {
    "good_rotate": ("ok", None, lambda im, s, sd: (S.rotate(im, 8), {"rotate_deg": 8}, [])),
    "good_reshot": ("ok", None, lambda im, s, sd: (S.sensor_noise(S.perspective(im, 0.10, sd), 3.0, sd),
                                                  {"perspective_k": 0.10, "noise_sigma": 3.0, "seed": sd}, [])),
    "good_light": ("ok", None, lambda im, s, sd: (S.side_light(im, 0.85, 1.15),
                                                 {"side_light": [0.85, 1.15], "new_clipped_frac": S.new_clipped(im, S.side_light(im, 0.85, 1.15))}, [])),
    "good_view_light": ("ok", None, lambda im, s, sd: (view_light(im, sd),
                                                      {"rotate_deg": 10, "zoom": 1.15, "perspective_k": 0.10, "side_light": [0.80, 1.15], "gamma": 0.9, "seed": sd,
                                                       "new_clipped_frac": S.new_clipped(im, view_light(im, sd))}, [])),
    "good_closeup": ("ok", None, lambda im, s, sd: (S.crop_around(im, _zone(s, "act"), 0.55), {"crop_around": "act zone", "min_frac": 0.55}, [])),
    "good_act_edit": ("ok", True, lambda im, s, sd: (S.perspective(S.paste_patch(im, _zone(s, "act"), sticker(sd), cover=0.6, seed=sd), 0.05, sd),
                                                    {"paste_into": "act zone", "patch": "sticker (drawn by code)", "cover": 0.6, "perspective_k": 0.05, "seed": sd}, [])),
    "blur_gaussian": ("retake", None, lambda im, s, sd: (S.gaussian_blur(im, 3), {"sigma": 3}, [])),
    "blur_motion": ("retake", None, lambda im, s, sd: (S.motion_blur(im, 21, 30), {"length": 21, "angle_deg": 30}, [])),
    "dark": ("retake", None, lambda im, s, sd: (S.exposure(im, 0.12), {"gain": 0.12}, [])),
    "overexposed": ("retake", None, lambda im, s, sd: (S.exposure(im, 2.8, 50), {"gain": 2.8, "offset": 50}, [])),
    "glare": ("retake", None, lambda im, s, sd: (S.glare(im, 0.06, *_centre(_zone(s, "act"))), {"frac": 0.06, "centre": "act zone"}, [])),
    "zone_cut": ("retake", None, lambda im, s, sd: (S.cut_zone(im, _zone(s, "act"), 0.25), {"cut_zone": "act", "keep_frac": 0.25}, [])),
    "wrong_place_mirror": ("wrong_place", None, lambda im, s, sd: (S.perspective(cv2.flip(im, 1), 0.05, sd),
                                                                  {"flip": "horizontal", "perspective_k": 0.05, "seed": sd,
                                                                   "note": "a mirror twin: the same kind of thing, laid out the other way round"}, [])),
    # expects_change=True: the documented policy (perception/inspect.py, rule 4) counts a
    # resent FIRST photo as a replay only when the step had to change something; for a
    # "confirm" step the first photo may already show what is asked. Widened run 1 had
    # None here, against that policy, and scored 20 policy-conform passes as "missed"
    # (eval/results/opencv-widened-run1-2026-10-21.md).
    "replay_exact": ("replay", True, lambda im, s, sd: (None, {"of": "reference", "bytes": "identical file"}, [])),
    "replay_reference": ("replay", True, lambda im, s, sd: (S.resize(S.jpeg(im, 70), 0.8), {"of": "reference", "jpeg_q": 70, "resize": 0.8}, [])),
    "replay_earlier": ("replay", None, lambda im, s, sd: (
        S.rotate(S.resize(S.sensor_noise(S.perspective(im, 0.10, sd), 3.0, sd), 0.85), 1.5),
        {"of": "an earlier evidence photo (a re-shot)", "resize": 0.85, "rotate_deg": 1.5, "seed": sd},
        [("earlier evidence", S.sensor_noise(S.perspective(im, 0.10, sd), 3.0, sd))])),
    "no_change": ("no_change", True, lambda im, s, sd: (S.sensor_noise(S.perspective(im, 0.10, sd), 3.0, sd),
                                                       {"perspective_k": 0.10, "noise_sigma": 3.0, "seed": sd}, [])),
    "touched_avoid": ("touched_avoid", None, lambda im, s, sd: (S.perspective(S.paste_patch(im, _zone(s, "avoid"), sticker(sd), cover=0.6, seed=sd), 0.05, sd),
                                                               {"paste_into": "avoid zone", "patch": "sticker (drawn by code)", "cover": 0.6, "perspective_k": 0.05, "seed": sd}, [])),
}
#: New classes also run on the six OnQ photos (their old 15 classes stay as they were).
ONQ_EXTRA = ("good_view_light", "wrong_place_mirror", "replay_exact")
#: Each Commons photo gets about half of the synthetic classes, chosen by a hash of
#: (photo, class), so every class sees ~20 photos it was never tuned on, and the set stays
#: small enough for the tests to build it twice.
PUB_SYNTH_SHARE = 2

#: Real pairs among the public sources: (reference, evidence, expected, class, why).
PUB_REAL: list[tuple[str, str, str, str, str]] = [
    ("c22", "c24", "ok", "real_same_place", "the same bottle trap, a wider shot from lower down (same uploader, same day)"),
    ("c24", "c22", "ok", "real_same_place", "the same bottle trap, closer"),
    ("c16", "c17", "ok", "real_same_place", "the same telephone socket, from a slightly different angle"),
    ("c16", "c18", "ok", "real_same_place", "the same telephone socket, straight on"),
    ("c18", "c16", "ok", "real_same_place", "the same telephone socket, from the side"),
    ("c27", "c28", "ok", "real_same_place", "the same tap seconds later: a second capture from a nearly fixed position (the water stream differs)"),
    ("c33", "c34", "ok", "real_same_place", "the same sink, from the left"),
    ("c34", "c35", "ok", "real_same_place", "the same sink, straight on"),
    ("c35", "c33", "ok", "real_same_place", "the same sink, from the right and closer"),
    ("c36", "c37", "ok", "real_same_place", "the same downspout box, portrait and further"),
    ("c37", "c36", "ok", "real_same_place", "the same downspout box, landscape and closer"),
    ("c09", "c10", "ok", "real_same_place", "the same two racks, from the front and then from the side (a large turn)"),
    ("v0659", "v0180", "ok", "real_same_place", "own video: the same trap, a close-up 15 s earlier"),
    ("v0180", "v0557", "ok", "real_same_place", "own video: the same trap elbow, from another side"),
    ("v0659", "v0448", "ok", "real_same_place", "own video: the same tailpiece and valve, another angle"),
    ("v0042", "v0812", "ok", "real_same_place", "own video: the same shut-off valve, closer and from the left"),
    ("v0042", "v0030", "ok", "real_same_place", "own video: the same valve corner 0.4 s earlier, flashlight hot spot on the wall"),
    ("v1106", "v1050", "ok", "real_same_place", "own video: the same disposal elbow, further away"),
    ("v1106", "v0990", "ok", "real_same_place", "own video: the same disposal elbow, further away and lower"),
    ("c22", "c23", "replay", "real_replay_annotated", "the same capture as the reference with a yellow circle drawn on it (uploaded by the same person as a separate file)"),
    ("v0180", "v0195", "retake", "real_blur", "own video: the trap, motion/focus blur (labelled by eye)"),
    ("v0659", "v0240", "retake", "real_blur", "own video: the valve, blurred with flashlight glare (labelled by eye)"),
    ("v0990", "v0900", "retake", "real_blur", "own video: motion blur and a flashlight hot spot (labelled by eye)"),
    ("v1106", "v0870", "retake", "real_blur", "own video: a whip pan, nothing recognisable (labelled by eye)"),
    ("v0557", "v0570", "borderline", "real_borderline", "own video: soft frame, the joint is readable but not its detail — not scored"),
    ("v0659", "v0510", "borderline", "real_borderline", "own video: soft frame — not scored"),
    ("v1106", "v0659", "wrong_place", "real_wrong_place_same_room", "own video: the trap side of the same cabinet, not the disposal elbow"),
    ("v0659", "v1050", "wrong_place", "real_wrong_place_same_room", "own video: the disposal side of the same cabinet, not the trap"),
    ("v0812", "v0990", "wrong_place", "real_wrong_place_same_room", "own video: the disposal side of the cabinet, not the valve"),
]
#: Look-alikes: for each anchor (one per group, plus OnQ 01, 02, 04, 06), up to
#: LOOKALIKES_PER_REF photos of the SAME family from OTHER groups in the SAME half,
#: picked by a hash of (reference, evidence): a similar thing that is not this one.
LOOKALIKES_PER_REF = 2
ONQ_FAMILY = {"01": "panel", "02": "panel", "04": "jack", "06": "jack"}


def _src_img(sid: str) -> np.ndarray:
    return imgio.load(ROOT / SOURCES[sid]["file"])


def _src_step(sid: str) -> dict:
    return dict(PUB["steps"][SOURCES[sid]["step"]])


def _pub_prov(sid: str) -> dict:
    s = SOURCES[sid]
    if s["source_type"] == "commons":
        c = s["commons"]
        return {"source_type": "commons", "title": c["title"], "author": c["author"], "licence": c["licence"],
                "licence_url": c["licence_url"], "page": c["page"]}
    v = s["video"]
    return {"source_type": "own-video", "source": v["source"], "frame": v["frame"], "consent": v["consent"],
            "label": v["label"], "label_note": v["label_note"], "label_by": v["label_by"]}


def _pub_ok(sid: str) -> bool:
    """Usable as a 'good' source: every Commons file; video frames labelled good."""
    s = SOURCES[sid]
    return s["source_type"] == "commons" or s["video"]["label"] == "good"


def _base_case(cid: str, cls: str, kind: str, group: str, scene: str, split: str, expected: str,
               expects_change: bool | None, ref_rel: str, zones_: list[dict], step: dict) -> dict[str, Any]:
    return {"id": cid, "class": cls, "kind": kind, "group": group, "scene": scene, "split": split,
            "expected": expected, "expects_change": expects_change, "reference": ref_rel,
            "reference_sha256": _file_sha(ref_rel), "earlier": [], "zones": zones_, "step": step}


def build_public() -> list[dict[str, Any]]:
    if not SOURCES:
        return []
    for sid, s in SOURCES.items():  # every source file must be the one listed
        if _file_sha(s["file"]) != s["sha256"]:
            raise SystemExit(f"{s['file']} does not match sources.json (sha256)")
    cases: list[dict[str, Any]] = []
    kind_of = lambda exp: "good" if exp == "ok" else ("unscored" if exp == "borderline" else "bad")  # noqa: E731

    def synth(sid_or_pid: str, cls: str, img: np.ndarray, ref_rel: str, zones_: list[dict], step: dict,
              group: str, scene: str, split: str, src_meta: dict, source: str) -> None:
        expected, expects_change, gen = PUB_SYNTH[cls]
        sd = _hseed(sid_or_pid, cls)
        src_for_zone = {"zones": zones_}
        out, params, earlier = gen(img, src_for_zone, sd)
        cid = f"{sid_or_pid}-{cls}"
        if out is None:
            ev_rel, ev_sha = ref_rel, _file_sha(ref_rel)
        else:
            ev_rel, ev_sha = _write(out, f"{cid}.jpg")
        earlier_out = []
        for i, (name, eimg) in enumerate(earlier):
            rel, sha = _write(eimg, f"{cid}-earlier-{i}.jpg")
            earlier_out.append({"name": name, "path": rel, "sha256": sha, "accepted": False})
        c = _base_case(cid, cls, kind_of(expected), group, scene, split, expected, expects_change, ref_rel, zones_, step)
        c.update(evidence=ev_rel, evidence_sha256=ev_sha, earlier=earlier_out, source=source,
                 provenance={"kind": "synthetic", "generator": f"eval/build_set.py PUB_SYNTH ({cls})", "params": params,
                             "rights": "our own photo (scenes.json _rights)" if source == "onq" else "see sources.json / ATTRIBUTION.md",
                             **src_meta})
        cases.append(c)

    # 1. new synthetic classes on the six OnQ photos
    for pid in sorted(PHOTOS):
        meta = PHOTOS[pid]
        for cls in ONQ_EXTRA:
            synth(pid, cls, load(pid), meta["file"], zones(pid), dict(meta["step"]), pid, meta["scene"], split_of(pid),
                  {"source": meta["name"]}, "onq")
    # 2. synthetic classes on the Commons photos (about half each, by hash)
    for sid in sorted(SOURCES):
        s = SOURCES[sid]
        if s["source_type"] != "commons":
            continue
        img = _src_img(sid)
        for cls in PUB_SYNTH:
            if _hseed(sid, cls, "share") % PUB_SYNTH_SHARE:
                continue
            synth(sid, cls, img, s["file"], [dict(z) for z in s["zones"]], _src_step(sid), s["group"], s["group"],
                  group_split(s["group"]), _pub_prov(sid), "commons")
    # 3. real pairs among the public sources
    for ref, ev, expected, cls, why in PUB_REAL:
        r, e = SOURCES[ref], SOURCES[ev]
        split = group_split(r["group"])
        if group_split(e["group"]) != split:
            raise ValueError(f"real pair {ref}->{ev} crosses the split")
        c = _base_case(f"{ref}-{cls}-{ev}", cls, kind_of(expected), r["group"], r["group"], split, expected, None,
                       r["file"], [dict(z) for z in r["zones"]], _src_step(ref))
        c.update(evidence=e["file"], evidence_sha256=e["sha256"], source=r["source_type"],
                 provenance={"kind": "real", "why": why, "reference_source": _pub_prov(ref), "evidence_source": _pub_prov(ev)})
        cases.append(c)
    # 4. look-alikes: a real photo of the same kind of thing, not this one
    anchors: list[tuple[str, str, str, str, str, str, list[dict], dict, str]] = []  # (key, family, group, scene, split, ref, zones, step, source)
    for pid, fam in ONQ_FAMILY.items():
        anchors.append((pid, fam, pid, PHOTOS[pid]["scene"], split_of(pid), PHOTOS[pid]["file"], zones(pid), dict(PHOTOS[pid]["step"]), "onq"))
    seen_groups: set[str] = set()
    for sid in sorted(SOURCES):
        s = SOURCES[sid]
        if s["group"] in seen_groups or not _pub_ok(sid):
            continue
        seen_groups.add(s["group"])
        anchors.append((sid, s["family"], s["group"], s["group"], group_split(s["group"]), s["file"], [dict(z) for z in s["zones"]], _src_step(sid), s["source_type"]))
    for key, fam, group, scene, split, ref_rel, zones_, step, source in anchors:
        pool = [sid for sid, s in SOURCES.items()
                if s["family"] == fam and s["group"] not in (group, scene) and group_split(s["group"]) == split and _pub_ok(sid)]
        pool.sort(key=lambda sid: hashlib.sha256(f"{key}->{sid}".encode()).hexdigest())
        for ev in pool[:LOOKALIKES_PER_REF]:
            e = SOURCES[ev]
            c = _base_case(f"{key}-real_lookalike-{ev}", "real_lookalike", "bad", group, scene, split, "wrong_place", None,
                           ref_rel, zones_, step)
            c.update(evidence=e["file"], evidence_sha256=e["sha256"], source=source,
                     provenance={"kind": "real", "why": f"a real photo of another {fam} ({e['group']}), not this one",
                                 "evidence_source": _pub_prov(ev)})
            cases.append(c)
    return cases


def main() -> int:
    CASES.mkdir(parents=True, exist_ok=True)
    cases = build()
    for c in cases:
        c.setdefault("source", "onq")
    manifest = {
        "_about": __doc__.strip().splitlines()[0],
        "_built_with": {"opencv": cv2.__version__, "numpy": np.__version__, "jpeg_quality": JPEG_Q},
        "_split": SCENES["_split"],
        "_split_public": PUB.get("_split"),
        "counts": {
            "cases": len(cases),
            "by_split": {s: sum(1 for c in cases if c["split"] == s) for s in ("calibration", "test")},
            "by_kind": {k: sum(1 for c in cases if c["kind"] == k) for k in ("good", "bad", "unscored")},
            "by_source": {k: sum(1 for c in cases if c.get("source", "onq") == k) for k in ("onq", "commons", "own-video")},
            "by_provenance": {k: sum(1 for c in cases if c["provenance"]["kind"] == k) for k in ("real", "synthetic")},
        },
        "cases": cases,
    }
    (CASES / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"wrote {len(cases)} cases to {_rel(CASES)}/ "
          f"({manifest['counts']['by_split']}, {manifest['counts']['by_kind']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
