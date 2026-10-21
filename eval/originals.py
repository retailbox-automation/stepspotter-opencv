"""The quality check alone on every UNMODIFIED real photo in the set.

    python eval/originals.py      # writes eval/results/originals.json and .md

Synthetic damage tells whether a check fires on what it was built for; it says nothing
about how often a real, ordinary photo is refused. This runs OpenCV's policy with no
reference (so only the quality rules can decide) on each original: the six OnQ photos,
every Commons file, and every kept frame of the own video, and compares with the label
a person gave it by eye (OnQ and Commons: all "good" as published; video: good /
blurred / borderline, sources.json).
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stepspotter.perception.inspect import inspect_full  # noqa: E402

RESULTS = ROOT / "eval" / "results"


def main() -> int:
    scenes = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())
    sources = json.loads((ROOT / "eval" / "cases" / "public" / "sources.json").read_text())["sources"]
    items = [(pid, "onq", m["file"], "good") for pid, m in sorted(scenes["photos"].items())]
    for sid, s in sorted(sources.items()):
        label = s["video"]["label"] if s["source_type"] == "own-video" else "good"
        items.append((sid, s["source_type"], s["file"], label))
    rows = []
    for sid, src, rel, label in items:
        rep, _ = inspect_full(str(ROOT / rel), None, ())
        q = rep.quality
        rows.append({"id": sid, "source": src, "file": rel, "label": label, "decision": rep.decision,
                     "reason_code": rep.reason_code, "ms_total": rep.ms_total,
                     "sharpness_p90": getattr(q, "sharpness_p90", None) if q else None,
                     "glare_blob_frac": getattr(q, "glare_blob_frac", None) if q else None,
                     "bright_frac": getattr(q, "bright_frac", None) if q else None})
    summ: dict[str, dict] = {}
    for r in rows:
        k = f"{r['source']} / {r['label']}"
        d = summ.setdefault(k, {"n": 0, "refused": 0, "reasons": {}})
        d["n"] += 1
        if r["decision"] != "ok":
            d["refused"] += 1
            d["reasons"][r["reason_code"]] = d["reasons"].get(r["reason_code"], 0) + 1
    res = {"ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "summary": summ, "rows": rows}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "originals.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["# Quality check on unmodified real photos", "", f"Ran {res['ran_at']}. Command: `python eval/originals.py`.", "",
             "| source / label by eye | n | refused by OpenCV | reasons |", "|---|---:|---:|---|"]
    for k, d in summ.items():
        lines.append(f"| {k} | {d['n']} | {d['refused']} | {d['reasons'] or '—'} |")
    lines += ["", "| photo | source | label | OpenCV | reason | sharpness p90 | glare blob | bright frac |", "|---|---|---|---|---|---:|---:|---:|"]
    for r in rows:
        f = lambda v: "—" if v is None else (f"{v:.4f}" if isinstance(v, float) and v < 1 else (f"{v:.1f}" if isinstance(v, float) else str(v)))  # noqa: E731
        lines.append(f"| {r['id']} | {r['source']} | {r['label']} | {r['decision']} | {r['reason_code']} | "
                     f"{f(r['sharpness_p90'])} | {f(r['glare_blob_frac'])} | {f(r['bright_frac'])} |")
    (RESULTS / "originals.md").write_text("\n".join(lines) + "\n")
    for k, d in summ.items():
        print(k, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
