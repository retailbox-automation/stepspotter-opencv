"""Run the perception eval: OpenCV only, the model only (one or two photos), or OpenCV then the model.

    python eval/build_set.py                                   # once: generate the cases
    python eval/run.py --config opencv                         # B: no model, no network
    python eval/run.py --config llm --max-llm-calls 0          # exits cleanly, calls nothing
    python eval/run.py --config combined --sample --dry-run    # lists what WOULD be called
    python eval/run.py --config llm --sample --max-llm-calls N # A: real Bedrock calls (spend!)

Configurations (the same cases, the same step text, the same verifier code):

* ``opencv``   (B) — OpenCV only: blocked = the report blocks. A photo OpenCV cannot line
  up with the first photo (``place_unconfirmed``) is NOT a block since L1b (21.10): it is
  counted as "routed to the two-photo check", never as caught or missed.
* ``llm``      (A) — the model only, on the evidence photo alone (``verify_step``).
* ``llm2``     (A') — the model only, on BOTH photos for every case (``verify_step(...,
  reference_photo=...)``, the same two-photo mode the gate uses), failing closed exactly
  like the gate: the photo closes the step only if passed AND same_place is true.
* ``combined`` (C) — the gate: OpenCV first; a block ends there (route ``opencv_block``);
  ``place_unconfirmed`` goes to the two-photo check (``llm_two_image``, fail closed);
  everything else to the one-photo check with OpenCV's aligned work-zone crop
  (``llm_single``).

``--sample`` restricts the run to the fixed model sample (``eval/llm_sample.json``, made
by ``--make-sample`` from the manifest alone, by a hash, before any model call); the
model configs are only ever run on it. ``--max-llm-calls`` is a hard stop in code:
after N calls every further case is recorded ``skipped_cap``, not dropped.

Each model call records the token usage Bedrock returned (Strands
``event_loop_metrics.accumulated_usage``) and its wall time. Writes
``eval/results/<config>[-sample][-dry-run].json`` and ``.md``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stepspotter.models import Step  # noqa: E402
from stepspotter.perception.inspect import Earlier, inspect_full, zone_crop_jpeg  # noqa: E402

RESULTS = ROOT / "eval" / "results"
SAMPLE = ROOT / "eval" / "llm_sample.json"
CONFIGS = ("opencv", "llm", "llm2", "combined")
LETTER = {"opencv": "B", "llm": "A", "llm2": "A'", "combined": "C"}


def manifest_path() -> Path:
    """``STEPSPOTTER_EVAL_CASES`` moves the case dir, exactly as in build_set.py."""
    return Path(os.environ.get("STEPSPOTTER_EVAL_CASES") or (ROOT / "eval" / "cases")) / "manifest.json"


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    k = (len(vs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return round(vs[lo] + (vs[hi] - vs[lo]) * (k - lo), 1)


def _git(*args: str, cwd: Path = ROOT) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance only
        return None


def _check(case: dict) -> None:
    """Every file must be the file the manifest was built from."""
    for rel, want in [(case["reference"], case["reference_sha256"]), (case["evidence"], case["evidence_sha256"])] + [
        (e["path"], e["sha256"]) for e in case["earlier"]
    ]:
        p = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        if not p.is_file():
            raise SystemExit(f"missing {rel}: run python eval/build_set.py first")
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f"{rel} does not match the manifest (sha256 {got[:12]} != {want[:12]}); rebuild the set")


def _abs(rel: str) -> str:
    return rel if Path(rel).is_absolute() else str(ROOT / rel)


def _zones(case: dict) -> list[tuple]:
    return [(z["label"], z["kind"], tuple(z["box"])) for z in case["zones"]]


def _opencv(case: dict):
    earlier = [Earlier(name=e["name"], src=_abs(e["path"]), accepted=e["accepted"]) for e in case["earlier"]]
    t = time.perf_counter()
    rep, detail = inspect_full(
        _abs(case["evidence"]),
        _abs(case["reference"]),
        _zones(case),
        expects_change=case["expects_change"],
        earlier=earlier,
        step_id=1,
    )
    wall = (time.perf_counter() - t) * 1000
    return rep, detail, wall


def _step(case: dict) -> Step:
    s = case["step"]
    return Step(id=1, title=s["title"], action=s["action"], evidence_required=s["evidence_required"],
                expects_change=case["expects_change"])


# ------------------------------------------------------------------ the fixed model sample

#: Per class, how many test-half cases go to the model. Real classes first; synthetic
#: classes are drawn from the Commons photos (nobody tuned a threshold on them).
SAMPLE_PER_CLASS = {"real_lookalike": 6, "real_same_place": 5, "real_wrong_place": 2, "real_replay_annotated": 1}
SAMPLE_SYNTH = 2
#: Real own-video cases are all in the calibration half (the hash put the video's one
#: group there); they are the only real blur in the set, so two of each go in, labelled.
SAMPLE_VIDEO = {"real_blur": 2, "real_wrong_place_same_room": 2}


def make_sample(manifest: dict) -> dict[str, Any]:
    def h(c: dict) -> str:
        return hashlib.sha256(("llm-sample:" + c["id"]).encode()).hexdigest()

    ids: list[str] = []
    by_class: dict[str, list[dict]] = {}
    for c in manifest["cases"]:
        by_class.setdefault(c["class"], []).append(c)
    for cls, cs in by_class.items():
        if cls in SAMPLE_VIDEO:
            pick = sorted(cs, key=h)[: SAMPLE_VIDEO[cls]]
        elif cls in SAMPLE_PER_CLASS:
            pick = sorted([c for c in cs if c["split"] == "test"], key=h)[: SAMPLE_PER_CLASS[cls]]
        elif cs[0]["provenance"]["kind"] == "synthetic":
            pool = [c for c in cs if c["split"] == "test" and c.get("source") == "commons"]
            pick = sorted(pool, key=h)[:SAMPLE_SYNTH]
        else:
            pick = []
        ids += [c["id"] for c in pick]
    return {
        "_about": "Cases the model configs run on. Chosen from the manifest alone by sha256('llm-sample:'+id) "
                  "within each class, before any model call; see eval/run.py SAMPLE_*.",
        "rule": {"per_class_real": SAMPLE_PER_CLASS, "synthetic_per_class_commons_test": SAMPLE_SYNTH, "own_video_calibration": SAMPLE_VIDEO},
        "manifest_sha256": hashlib.sha256(manifest_path().read_bytes()).hexdigest(),
        "ids": sorted(ids),
    }


# ------------------------------------------------------------------------- model calls


class _Usage:
    """Capture the Strands agent of the one call in flight, to read Bedrock's token usage."""

    def __init__(self) -> None:
        self.agents: list[Any] = []

    def install(self) -> None:
        from stepspotter import vision

        orig = vision.make_agent

        def make_agent(*a, **k):
            ag = orig(*a, **k)
            self.agents.append(ag)
            return ag

        vision.make_agent = make_agent

    def take(self) -> dict[str, int] | None:
        if not self.agents:
            return None
        ag = self.agents.pop()
        self.agents.clear()
        u = dict(getattr(ag.event_loop_metrics, "accumulated_usage", {}) or {})
        return {k: int(v) for k, v in u.items() if isinstance(v, (int, float))}


def _call(verify, usage: _Usage, case: dict, **kwargs) -> dict[str, Any]:
    t = time.perf_counter()
    try:
        v = verify(_step(case), _abs(case["evidence"]), **kwargs)
        out: dict[str, Any] = {"status": "called", "passed": v.passed, "stop": v.stop, "reason": v.reason,
                               "same_place": getattr(v, "same_place", None)}
    except Exception as exc:  # noqa: BLE001 - one failed call is a recorded failure
        out = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    out["wall_ms"] = round((time.perf_counter() - t) * 1000, 1)
    out["mode"] = "two_image" if kwargs.get("reference_photo") else "single"
    out["usage"] = usage.take()
    return out


def _blocked_by(llm: dict[str, Any]) -> bool:
    """What the gate does with a model answer: fail closed on a two-photo answer."""
    if llm["mode"] == "two_image":
        return (not llm["passed"]) or bool(llm["stop"]) or llm.get("same_place") is not True
    return (not llm["passed"]) or bool(llm["stop"])


def run(config: str, max_llm_calls: int, dry_run: bool, split: str, only: list[str] | None = None) -> dict[str, Any]:
    mpath = manifest_path()
    if not mpath.is_file():
        raise SystemExit(f"no manifest at {mpath}: run python eval/build_set.py first")
    manifest = json.loads(mpath.read_text())
    cases = [c for c in manifest["cases"] if split == "all" or c["split"] == split]
    if only is not None:
        keep = set(only)
        cases = [c for c in cases if c["id"] in keep]
    for c in cases:
        _check(c)
    verify = None
    usage = _Usage()
    if config in ("llm", "llm2", "combined") and not dry_run and max_llm_calls > 0:
        from stepspotter.verifier import verify_step as verify  # imported only when it may be called

        usage.install()
    calls = 0
    errors_in_row = 0  # three failed calls in a row stop the spending (credentials, quota)
    rows: list[dict[str, Any]] = []
    would_call: list[dict] = []
    for c in cases:
        row: dict[str, Any] = {k: c.get(k) for k in ("id", "class", "kind", "group", "scene", "split", "expected", "source")}
        row["source"] = row["source"] or "onq"
        row["provenance"] = c["provenance"]["kind"]
        rep = detail = None
        if config in ("opencv", "combined"):
            rep, detail, wall = _opencv(c)
            row.update(
                decision=rep.decision,
                reason_code=rep.reason_code,
                route=rep.route,
                opencv_blocks=rep.blocks,
                ms_total=rep.ms_total,
                wall_ms=round(wall, 1),
                inliers=rep.scene.inliers if rep.scene else None,
                scene_status=rep.scene.status if rep.scene else None,
                change=rep.change.status if rep.change else None,
                faces_checked=rep.privacy.faces_checked if rep.privacy else None,
            )
        # which model call (if any) this config makes for this case
        call_kwargs: dict[str, Any] | None = None
        if config == "llm":
            call_kwargs = {}
        elif config == "llm2":
            call_kwargs = {"reference_photo": _abs(c["reference"])}
        elif config == "combined" and rep is not None and not rep.blocks:
            call_kwargs = {}
            crop = zone_crop_jpeg(rep, detail) if detail is not None else None
            if crop is not None:
                call_kwargs["zone_crop"] = crop
            if rep.route == "llm_two_image":
                call_kwargs["reference_photo"] = _abs(c["reference"])
        llm: dict[str, Any] | None = None
        if call_kwargs is not None:
            mode = "two_image" if "reference_photo" in call_kwargs else "single"
            if dry_run:
                would_call.append({"id": c["id"], "evidence": c["evidence"], "step": c["step"]["title"], "mode": mode})
                llm = {"status": "dry_run", "mode": mode}
            elif calls >= max_llm_calls or errors_in_row >= 3:
                llm = {"status": "skipped_cap" if calls >= max_llm_calls else "skipped_after_errors", "mode": mode}
            else:
                llm = _call(verify, usage, c, **call_kwargs)
                calls += 1
                errors_in_row = errors_in_row + 1 if llm["status"] == "error" else 0
            row["llm"] = llm
        # what the gate would do with this case under this config
        blocked: bool | None
        if config == "opencv":
            blocked = True if rep.blocks else (None if rep.route == "llm_two_image" else False)
        elif config in ("llm", "llm2"):
            blocked = None if llm is None or llm.get("status") != "called" else _blocked_by(llm)
        else:
            if rep is not None and rep.blocks:
                blocked = True
            elif llm is not None and llm.get("status") == "called":
                blocked = _blocked_by(llm)
            else:
                blocked = None
        row["blocked"] = blocked
        if c["kind"] == "unscored":
            row["outcome"] = "unscored"
        elif blocked is None:
            row["outcome"] = "routed_two_image" if (config == "opencv" and rep is not None and rep.route == "llm_two_image") else "not_run"
        elif c["kind"] == "bad":
            row["outcome"] = "caught" if blocked else "missed"
        else:
            row["outcome"] = "false_block" if blocked else "accepted"
        if config == "opencv":
            row["decision_correct"] = rep.decision == c["expected"] or (
                c["expected"] == "wrong_place" and rep.decision == "place_unconfirmed")
        rows.append(row)
    faces = {r.get("faces_checked") for r in rows if "faces_checked" in r}
    return {
        "config": config,
        "letter": LETTER[config],
        "split": split,
        "max_llm_calls": max_llm_calls,
        "llm_calls_made": calls,
        "dry_run": dry_run,
        "would_call": would_call,
        "built_with": manifest.get("_built_with"),
        "manifest_sha256": hashlib.sha256(mpath.read_bytes()).hexdigest(),
        "code": {
            "eval_worktree_head": _git("rev-parse", "HEAD"),
            "main_head": _git("rev-parse", "main"),
            "l1_checkout_head": _git("rev-parse", "HEAD", cwd=ROOT.parent / "stepspotter-opencv"),
            "stepspotter_imported_from": ("this checkout's src/" if Path(sys.modules["stepspotter.models"].__file__).resolve().parents[2] == ROOT.resolve()
                                          else "another checkout's src/ (see l1_checkout_head)"),
        },
        "model_id": os.environ.get("STEPSPOTTER_MODEL") or "Strands/Bedrock default (global.anthropic.claude-sonnet-4-6)",
        "faces_checked": sorted(str(f) for f in faces),
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
        "summary": summarize(rows),
    }


def summarize(rows: list[dict]) -> dict[str, Any]:
    def block(sel: list[dict]) -> dict[str, Any]:
        ran = [r for r in sel if r["outcome"] not in ("not_run", "unscored", "routed_two_image")]
        calls = [r["llm"] for r in sel if (r.get("llm") or {}).get("status") == "called"]
        out = {
            "n": len(sel),
            "ran": len(ran),
            "caught": sum(r["outcome"] == "caught" for r in ran),
            "missed": sum(r["outcome"] == "missed" for r in ran),
            "accepted": sum(r["outcome"] == "accepted" for r in ran),
            "false_blocks": sum(r["outcome"] == "false_block" for r in ran),
            "routed_two_image": sum(r["outcome"] == "routed_two_image" for r in sel),
            "unscored": sum(r["outcome"] == "unscored" for r in sel),
            "llm_calls": len(calls),
            "llm_errors": sum(1 for r in sel if (r.get("llm") or {}).get("status") == "error"),
        }
        routes: dict[str, int] = {}
        for r in sel:
            if r.get("route"):
                routes[r["route"]] = routes.get(r["route"], 0) + 1
        if routes:
            out["routes"] = routes
        ms = [r["ms_total"] for r in sel if r.get("ms_total") is not None]
        if ms:
            out["opencv_ms_p50"], out["opencv_ms_p95"] = _pct(ms, 0.5), _pct(ms, 0.95)
        if calls:
            out["llm_ms_p50"], out["llm_ms_p95"] = _pct([x["wall_ms"] for x in calls], 0.5), _pct([x["wall_ms"] for x in calls], 0.95)
            tok_in = [x["usage"].get("inputTokens", 0) for x in calls if x.get("usage")]
            tok_out = [x["usage"].get("outputTokens", 0) for x in calls if x.get("usage")]
            out["input_tokens"], out["output_tokens"] = sum(tok_in), sum(tok_out)
        # end-to-end time of the check per case: OpenCV (if run) + the model call (if made)
        e2e = []
        for r in sel:
            if r["outcome"] in ("not_run",):
                continue
            t = (r.get("ms_total") or 0.0) + (((r.get("llm") or {}).get("wall_ms") or 0.0) if (r.get("llm") or {}).get("status") == "called" else 0.0)
            e2e.append(t)
        if e2e:
            out["e2e_ms_p50"], out["e2e_ms_p95"] = _pct(e2e, 0.5), _pct(e2e, 0.95)
        if any("decision_correct" in r for r in sel):
            out["decision_correct"] = sum(bool(r.get("decision_correct")) for r in sel)
            decs: dict[str, int] = {}
            for r in sel:
                decs[r["decision"]] = decs.get(r["decision"], 0) + 1
            out["decisions"] = decs
        return out

    by_class: dict[str, Any] = {}
    for cls in dict.fromkeys(r["class"] for r in rows):
        by_class[cls] = {"kind": next(r["kind"] for r in rows if r["class"] == cls)} | block(
            [r for r in rows if r["class"] == cls]
        )
    return {
        "all": block(rows),
        "by_split": {s: block([r for r in rows if r["split"] == s]) for s in ("calibration", "test")},
        "by_kind": {k: block([r for r in rows if r["kind"] == k]) for k in ("good", "bad")},
        "by_source": {s: block([r for r in rows if r["source"] == s]) for s in ("onq", "commons", "own-video")},
        "by_class": by_class,
        "by_class_test": {cls: block([r for r in rows if r["class"] == cls and r["split"] == "test"])
                          for cls in dict.fromkeys(r["class"] for r in rows if r["split"] == "test")},
    }


def markdown(res: dict[str, Any]) -> str:
    s = res["summary"]
    lines = [
        f"# Perception eval — `--config {res['config']}` ({res['letter']})",
        "",
        f"Ran {res['ran_at']} on {s['all']['n']} cases (split: {res['split']}); "
        f"OpenCV {(res.get('built_with') or {}).get('opencv')}; model calls made: {res['llm_calls_made']} "
        f"(cap {res['max_llm_calls']}){'; DRY RUN' if res['dry_run'] else ''}. "
        f"Code: main `{(res['code'].get('main_head') or '')[:7]}`, eval `{(res['code'].get('eval_worktree_head') or '')[:7]}`; "
        f"faces checked: {', '.join(res['faces_checked']) or '—'}.",
        "",
        "| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def cell(v: Any) -> str:
        return "—" if v is None else str(v)

    for cls, b in s["by_class"].items():
        bad = b["kind"] == "bad"
        good = b["kind"] == "good"
        lines.append(
            f"| {cls} | {b['kind']} | {b['n']} | {cell(b['caught'] if bad else None)} | "
            f"{cell(b['missed'] if bad else None)} | {cell(b['false_blocks'] if good else None)} | {b['routed_two_image'] or '—'} | "
            f"{cell(b.get('decision_correct'))} | {cell(b.get('opencv_ms_p50', b.get('llm_ms_p50')))} | "
            f"{cell(b.get('opencv_ms_p95', b.get('llm_ms_p95')))} | {b['llm_calls']} |"
        )
    lines += ["", "| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |",
              "|---|---:|---:|---:|---:|---:|---|---:|---:|"]
    for name, b in ([("all", s["all"])] + [(f"split: {k}", v) for k, v in s["by_split"].items()]
                    + [(f"source: {k}", v) for k, v in s["by_source"].items() if v["n"]]):
        bad_n = b["caught"] + b["missed"]
        good_n = b["accepted"] + b["false_blocks"]
        lines.append(
            f"| {name} | {b['n']} | {b['ran']} | {b['caught']} / {bad_n} | {b['false_blocks']} / {good_n} | "
            f"{b['routed_two_image']} | {cell(b.get('routes'))} | {cell(b.get('e2e_ms_p50'))} | {cell(b.get('e2e_ms_p95'))} |"
        )
    wrong = [r for r in res["rows"] if r["outcome"] in ("missed", "false_block") or r.get("decision_correct") is False]
    if wrong:
        lines += ["", "## Failures, every one (published, not averaged away)", "",
                  "| case | split | source | expected | got | outcome | reason code | inliers |", "|---|---|---|---|---|---|---|---:|"]
        for r in wrong:
            got = r.get("decision") or (r.get("llm") or {}).get("status")
            if r.get("llm", {}).get("status") == "called":
                got = f"{got} -> model passed={r['llm']['passed']}" + (f", same_place={r['llm'].get('same_place')}" if r["llm"]["mode"] == "two_image" else "")
            lines.append(f"| {r['id']} | {r['split']} | {r['source']} | {r['expected']} | {got} | "
                         f"{r['outcome']} | {r.get('reason_code', '')} | {cell(r.get('inliers'))} |")
    if res["would_call"]:
        lines += ["", f"## Dry run: {len(res['would_call'])} model calls would be made", ""]
        lines += [f"- {w['id']} ({w['mode']}): {w['evidence']} — step \"{w['step']}\"" for w in res["would_call"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", choices=CONFIGS)
    ap.add_argument("--max-llm-calls", type=int, default=0, help="hard cap on Bedrock calls in this run (default 0)")
    ap.add_argument("--dry-run", action="store_true", help="list the model calls that would be made; make none")
    ap.add_argument("--split", choices=("all", "calibration", "test"), default="all")
    ap.add_argument("--sample", action="store_true", help=f"run only the fixed model sample ({SAMPLE.name})")
    ap.add_argument("--make-sample", action="store_true", help=f"write {SAMPLE.name} from the manifest and exit")
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args(argv)
    if args.make_sample:
        sample = make_sample(json.loads(manifest_path().read_text()))
        SAMPLE.write_text(json.dumps(sample, indent=1) + "\n")
        print(f"wrote {len(sample['ids'])} ids to {SAMPLE}")
        return 0
    if not args.config:
        ap.error("--config is required")
    if args.max_llm_calls < 0:
        ap.error("--max-llm-calls must be >= 0")
    only = None
    if args.sample:
        sample = json.loads(SAMPLE.read_text())
        if sample["manifest_sha256"] != hashlib.sha256(manifest_path().read_bytes()).hexdigest():
            raise SystemExit("the manifest changed since the sample was drawn: rebuild the sample on purpose (--make-sample)")
        only = sample["ids"]
    res = run(args.config, args.max_llm_calls, args.dry_run, args.split, only=only)
    res["sample"] = bool(args.sample)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = (args.config + ("-sample" if args.sample else "") + ("-dry-run" if args.dry_run else "")
            + ("" if args.split == "all" else f"-{args.split}"))
    (out / f"{stem}.json").write_text(json.dumps(res, indent=1) + "\n")
    (out / f"{stem}.md").write_text(markdown(res))
    s = res["summary"]["all"]
    print(f"{args.config}: {s['n']} cases, caught {s['caught']}/{s['caught'] + s['missed']} bad, "
          f"false blocks {s['false_blocks']}/{s['accepted'] + s['false_blocks']} good, routed to 2-photo {s['routed_two_image']}, "
          f"model calls {res['llm_calls_made']}, errors {s['llm_errors']}, not run {s['n'] - s['ran'] - s['routed_two_image'] - s['unscored']} "
          f"-> {out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
