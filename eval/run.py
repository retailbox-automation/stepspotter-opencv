"""Run the perception eval: OpenCV only, the model only, or OpenCV then the model.

    python eval/build_set.py                                  # once: generate the cases
    python eval/run.py --config opencv                        # no model, no network
    python eval/run.py --config llm --max-llm-calls 0         # exits cleanly, calls nothing
    python eval/run.py --config combined --dry-run            # lists what WOULD be called
    python eval/run.py --config llm --max-llm-calls 120       # real Bedrock calls (spend!)

Writes ``eval/results/<config>.json`` and ``eval/results/<config>.md``.

What is measured, per class of case:

* bad evidence  — caught (the gate would not let the step close on it) vs missed;
* good evidence — false blocks (the gate refused a photo it should have accepted);
* decision correct — OpenCV's exact decision equals the expected one (opencv config);
* latency p50 / p95 — OpenCV ``ms_total`` (its own clock), and wall time per case;
* model calls made, and skipped because of the cap.

"Caught" for the model config means the verifier answered ``passed=false`` (or stop);
for the combined config it means either OpenCV blocked or the model said no — exactly
what the gate would do. The cap is a hard stop in code: once ``--max-llm-calls`` calls
have been made, every further case is recorded as ``skipped_cap``, not silently dropped.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stepspotter.models import Step  # noqa: E402
from stepspotter.perception.inspect import Earlier, inspect_full, zone_crop_jpeg  # noqa: E402

RESULTS = ROOT / "eval" / "results"


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


def run(config: str, max_llm_calls: int, dry_run: bool, split: str, only: list[str] | None = None) -> dict[str, Any]:
    mpath = manifest_path()
    if not mpath.is_file():
        raise SystemExit(f"no manifest at {mpath}: run python eval/build_set.py first")
    manifest = json.loads(mpath.read_text())
    cases = [c for c in manifest["cases"] if split == "all" or c["split"] == split]
    if only:
        cases = [c for c in cases if c["id"] in set(only)]
    for c in cases:
        _check(c)
    verify = None
    if config in ("llm", "combined") and not dry_run and max_llm_calls > 0:
        from stepspotter.verifier import verify_step as verify  # imported only when it may be called
    calls = 0
    rows: list[dict[str, Any]] = []
    would_call: list[dict] = []
    for c in cases:
        row: dict[str, Any] = {k: c[k] for k in ("id", "class", "kind", "group", "scene", "split", "expected")}
        rep = detail = None
        if config in ("opencv", "combined"):
            rep, detail, wall = _opencv(c)
            row.update(
                decision=rep.decision,
                reason_code=rep.reason_code,
                opencv_blocks=rep.blocks,
                ms_total=rep.ms_total,
                wall_ms=round(wall, 1),
                inliers=rep.scene.inliers if rep.scene else None,
                scene=rep.scene.status if rep.scene else None,
                change=rep.change.status if rep.change else None,
            )
        needs_model = config == "llm" or (config == "combined" and rep is not None and not rep.blocks)
        llm: dict[str, Any] | None = None
        if needs_model:
            if dry_run:
                would_call.append({"id": c["id"], "evidence": c["evidence"], "step": c["step"]["title"]})
                llm = {"status": "dry_run"}
            elif calls >= max_llm_calls:
                llm = {"status": "skipped_cap"}
            else:
                kwargs: dict[str, Any] = {}
                if config == "combined" and detail is not None:
                    crop = zone_crop_jpeg(rep, detail)
                    if crop is not None:
                        kwargs["zone_crop"] = crop
                t = time.perf_counter()
                try:
                    v = verify(_step(c), _abs(c["evidence"]), **kwargs)  # type: ignore[misc]
                    llm = {"status": "called", "passed": v.passed, "stop": v.stop, "reason": v.reason}
                except Exception as exc:  # noqa: BLE001 - one failed call is a recorded failure
                    llm = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                llm["wall_ms"] = round((time.perf_counter() - t) * 1000, 1)
                calls += 1
            row["llm"] = llm
        # What the gate would do with this case under this config.
        if config == "opencv":
            blocked: bool | None = bool(rep.blocks)
        elif config == "llm":
            blocked = None if llm is None or llm.get("status") != "called" else (not llm["passed"] or llm["stop"])
        else:
            if rep is not None and rep.blocks:
                blocked = True
            elif llm is not None and llm.get("status") == "called":
                blocked = (not llm["passed"]) or llm["stop"]
            else:
                blocked = None
        row["blocked"] = blocked
        if blocked is None:
            row["outcome"] = "not_run"
        elif c["kind"] == "bad":
            row["outcome"] = "caught" if blocked else "missed"
        else:
            row["outcome"] = "false_block" if blocked else "accepted"
        if config == "opencv":
            row["decision_correct"] = rep.decision == c["expected"]
        rows.append(row)
    return {
        "config": config,
        "split": split,
        "max_llm_calls": max_llm_calls,
        "llm_calls_made": calls,
        "dry_run": dry_run,
        "would_call": would_call,
        "built_with": manifest.get("_built_with"),
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
        "summary": summarize(rows),
    }


def summarize(rows: list[dict]) -> dict[str, Any]:
    def block(sel: list[dict]) -> dict[str, Any]:
        ran = [r for r in sel if r["outcome"] != "not_run"]
        out = {
            "n": len(sel),
            "ran": len(ran),
            "caught": sum(r["outcome"] == "caught" for r in ran),
            "missed": sum(r["outcome"] == "missed" for r in ran),
            "accepted": sum(r["outcome"] == "accepted" for r in ran),
            "false_blocks": sum(r["outcome"] == "false_block" for r in ran),
            "llm_calls": sum(1 for r in sel if (r.get("llm") or {}).get("status") == "called"),
        }
        ms = [r["ms_total"] for r in sel if r.get("ms_total") is not None]
        if ms:
            out["opencv_ms_p50"], out["opencv_ms_p95"] = _pct(ms, 0.5), _pct(ms, 0.95)
        llm_ms = [r["llm"]["wall_ms"] for r in sel if (r.get("llm") or {}).get("status") == "called"]
        if llm_ms:
            out["llm_ms_p50"], out["llm_ms_p95"] = _pct(llm_ms, 0.5), _pct(llm_ms, 0.95)
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
        "by_class": by_class,
    }


def markdown(res: dict[str, Any]) -> str:
    s = res["summary"]
    lines = [
        f"# Perception eval — `--config {res['config']}`",
        "",
        f"Ran {res['ran_at']} on {s['all']['n']} cases (split: {res['split']}); "
        f"OpenCV {(res.get('built_with') or {}).get('opencv')}; model calls made: {res['llm_calls_made']} "
        f"(cap {res['max_llm_calls']}){'; DRY RUN' if res['dry_run'] else ''}.",
        "",
        "| class | kind | n | caught | missed | false blocks | decision = expected | p50 ms | p95 ms | model calls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def cell(v: Any) -> str:
        return "—" if v is None else str(v)

    for cls, b in s["by_class"].items():
        bad = b["kind"] == "bad"
        lines.append(
            f"| {cls} | {b['kind']} | {b['n']} | {cell(b['caught'] if bad else None)} | "
            f"{cell(b['missed'] if bad else None)} | {cell(None if bad else b['false_blocks'])} | "
            f"{cell(b.get('decision_correct'))} | {cell(b.get('opencv_ms_p50'))} | {cell(b.get('opencv_ms_p95'))} | {b['llm_calls']} |"
        )
    lines += ["", "| slice | n | ran | caught / bad | false blocks / good | decision = expected | p50 ms | p95 ms |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, b in [("all", s["all"])] + [(f"split: {k}", v) for k, v in s["by_split"].items()]:
        bad_n = b["caught"] + b["missed"]
        good_n = b["accepted"] + b["false_blocks"]
        lines.append(
            f"| {name} | {b['n']} | {b['ran']} | {b['caught']} / {bad_n} | {b['false_blocks']} / {good_n} | "
            f"{cell(b.get('decision_correct'))} | {cell(b.get('opencv_ms_p50'))} | {cell(b.get('opencv_ms_p95'))} |"
        )
    wrong = [r for r in res["rows"] if r["outcome"] in ("missed", "false_block") or r.get("decision_correct") is False]
    if wrong:
        lines += ["", "## Failures, every one (published, not averaged away)", "",
                  "| case | split | expected | got | outcome | reason code |", "|---|---|---|---|---|---|"]
        for r in wrong:
            lines.append(f"| {r['id']} | {r['split']} | {r['expected']} | {r.get('decision', (r.get('llm') or {}).get('status'))} | "
                         f"{r['outcome']} | {r.get('reason_code', '')} |")
    if res["would_call"]:
        lines += ["", f"## Dry run: {len(res['would_call'])} model calls would be made", ""]
        lines += [f"- {w['id']}: {w['evidence']} — step \"{w['step']}\"" for w in res["would_call"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", choices=("opencv", "llm", "combined"), required=True)
    ap.add_argument("--max-llm-calls", type=int, default=120, help="hard cap on Bedrock calls (default 120)")
    ap.add_argument("--dry-run", action="store_true", help="list the model calls that would be made; make none")
    ap.add_argument("--split", choices=("all", "calibration", "test"), default="all")
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args(argv)
    if args.max_llm_calls < 0:
        ap.error("--max-llm-calls must be >= 0")
    res = run(args.config, args.max_llm_calls, args.dry_run, args.split)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = args.config + ("-dry-run" if args.dry_run else "") + ("" if args.split == "all" else f"-{args.split}")
    (out / f"{stem}.json").write_text(json.dumps(res, indent=1) + "\n")
    (out / f"{stem}.md").write_text(markdown(res))
    s = res["summary"]["all"]
    print(f"{args.config}: {s['n']} cases, caught {s['caught']}/{s['caught'] + s['missed']} bad, "
          f"false blocks {s['false_blocks']}/{s['accepted'] + s['false_blocks']} good, "
          f"model calls {res['llm_calls_made']}, not run {s['n'] - s['ran']} -> {out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
