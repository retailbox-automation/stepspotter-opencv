"""Put the four configurations side by side on the model sample, with $ and pictures.

    python eval/compare.py     # reads eval/results/{llm,llm2,combined}-sample.json and
                               # eval/results/bedrock-price-sonnet-4-6.json; writes
                               # eval/results/compare.json, compare.md, figures/*.jpg

No model call is made here: it only reads the runs. B (OpenCV only) on the sample is
read from the combined run's OpenCV half (the same code on the same files; the full-set
B run is eval/results/opencv.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"
FIG = RES / "figures"
MANIFEST = ROOT / "eval" / "cases" / "manifest.json"
CONFIGS = [("A", "llm"), ("A'", "llm2"), ("C", "combined")]


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    k = (len(vs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return round(vs[lo] + (vs[hi] - vs[lo]) * (k - lo), 1)


def _price() -> tuple[float, float, dict]:
    p = json.loads((RES / "bedrock-price-sonnet-4-6.json").read_text())
    by = {x["usagetype"]: float(x["usd_per_1M"]) for x in p["prices"]}
    return by["USE1-MP:USE1_InputTokenCount_Global-Units"], by["USE1-MP:USE1_OutputTokenCount_Global-Units"], p


def _usd(llm: dict | None, pin: float, pout: float) -> float:
    if not llm or llm.get("status") != "called" or not llm.get("usage"):
        return 0.0
    u = llm["usage"]
    return u.get("inputTokens", 0) / 1e6 * pin + u.get("outputTokens", 0) / 1e6 * pout


def _b_outcome(r: dict) -> str:
    """B (OpenCV only) from a combined row: a block, or not; place_unconfirmed is routed."""
    if r["route"] == "opencv_block":
        return "caught" if r["kind"] == "bad" else "false_block"
    if r["route"] == "llm_two_image":
        return "routed_two_image"
    return "missed" if r["kind"] == "bad" else "accepted"


def _decision_text(cfg: str, r: dict) -> str:
    if cfg == "combined" and r.get("route") == "opencv_block":
        return f"OpenCV {r['decision']} ({r['reason_code']}), no model call"
    llm = r.get("llm") or {}
    if llm.get("status") != "called":
        return llm.get("status", "-")
    sp = "" if llm.get("same_place") is None else f", same_place={llm['same_place']}"
    pre = f"OpenCV {r['decision']} -> " if cfg == "combined" else ""
    return f"{pre}model passed={llm['passed']}{sp}: {llm.get('reason', '')}"


def _reason(case: dict, c: dict) -> str:
    """Why C blocked: OpenCV for the reason the case was built for, OpenCV for another
    reason (right outcome, wrong reason), or the model."""
    if not c.get("blocked"):
        return "passed"
    if c.get("route") != "opencv_block":
        return "model"
    return "opencv, expected reason" if c.get("decision") == case["expected"] else f"opencv, other reason ({c.get('reason_code')})"


def _figure(case: dict, a: dict, c: dict, name: str) -> str:
    """Reference | evidence, with the two decisions underneath. 1000 px wide JPEG."""
    imgs = []
    for rel in (case["reference"], case["evidence"]):
        im = cv2.imread(str(ROOT / rel))
        h, w = im.shape[:2]
        s = 380 / h
        imgs.append(cv2.resize(im, (max(1, int(w * s)), 380), interpolation=cv2.INTER_AREA))
    gap = np.full((380, 12, 3), 255, np.uint8)
    top = np.hstack([imgs[0], gap, imgs[1]])
    W = max(top.shape[1], 1000)
    canvas_top = np.full((380, W, 3), 255, np.uint8)
    canvas_top[:, : top.shape[1]] = top
    lines = [
        f"{case['id']}  [{case['split']}, {case.get('source', 'onq')}, expected: {case['expected']}]",
        "left: reference (first photo)   right: evidence",
        f"OpenCV: {c.get('decision')} / route {c.get('route')} / inliers {c.get('inliers')} / {c.get('ms_total', 0):.0f} ms",
        f"A (model, 1 photo): {'BLOCK' if a['blocked'] else 'PASS'}",
        f"C (OpenCV -> model): {'BLOCK' if c['blocked'] else 'PASS'}",
    ]
    strip = np.full((22 * len(lines) + 10, W, 3), 255, np.uint8)
    for i, t in enumerate(lines):
        cv2.putText(strip, t[:150], (8, 22 * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    out = np.vstack([canvas_top, strip])
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / f"{name}.jpg"
    cv2.imwrite(str(path), out, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return str(path.relative_to(ROOT))


def main() -> int:
    pin, pout, price = _price()
    man = {c["id"]: c for c in json.loads(MANIFEST.read_text())["cases"]}
    runs = {cfg: json.loads((RES / f"{cfg}-sample.json").read_text()) for _, cfg in CONFIGS}
    rows = {cfg: {r["id"]: r for r in runs[cfg]["rows"]} for cfg in runs}
    ids = sorted(rows["llm"])
    assert all(sorted(rows[c]) == ids for c in rows), "the three runs are not on the same sample"

    def outcome(cfg: str, i: str) -> str:
        return _b_outcome(rows["combined"][i]) if cfg == "opencv" else rows[cfg][i]["outcome"]

    classes = list(dict.fromkeys(rows["llm"][i]["class"] for i in ids))
    table = []
    for cls in classes:
        sel = [i for i in ids if rows["llm"][i]["class"] == cls]
        kind = rows["llm"][sel[0]]["kind"]
        row = {"class": cls, "kind": kind, "n": len(sel), "split": sorted({rows["llm"][i]["split"] for i in sel}),
               "source": sorted({rows["llm"][i]["source"] for i in sel})}
        for letter, cfg in [("A", "llm"), ("A'", "llm2"), ("B", "opencv"), ("C", "combined")]:
            outs = [outcome(cfg, i) for i in sel]
            if kind == "bad":
                row[letter] = {"caught": outs.count("caught"), "missed": outs.count("missed"), "routed": outs.count("routed_two_image")}
            else:
                row[letter] = {"false_blocks": outs.count("false_block"), "accepted": outs.count("accepted"), "routed": outs.count("routed_two_image")}
        table.append(row)

    def totals(cfg: str, sel: list[str]) -> dict:
        outs = [outcome(cfg, i) for i in sel]
        return {"caught": outs.count("caught"), "bad": sum(rows["llm"][i]["kind"] == "bad" for i in sel),
                "false_blocks": outs.count("false_block"), "good": sum(rows["llm"][i]["kind"] == "good" for i in sel),
                "routed": outs.count("routed_two_image")}

    c_reasons: dict[str, int] = {}
    for i in ids:
        if rows["combined"][i]["kind"] == "bad" and rows["combined"][i]["blocked"]:
            k = _reason(man[i], rows["combined"][i])
            k = "opencv, other reason" if k.startswith("opencv, other") else k
            c_reasons[k] = c_reasons.get(k, 0) + 1
    test_ids = [i for i in ids if rows["llm"][i]["split"] == "test"]
    synth = {i for i in ids if rows["llm"][i]["provenance"] == "synthetic"}
    slices = {"sample (all)": ids, "test half": test_ids,
              "test half, real photos only": [i for i in test_ids if i not in synth],
              "test half, synthetic only": [i for i in test_ids if i in synth],
              "own video (calibration half)": [i for i in ids if rows["llm"][i]["source"] == "own-video"]}
    slice_tab = {name: {L: totals(cfg, sel) for L, cfg in [("A", "llm"), ("A'", "llm2"), ("B", "opencv"), ("C", "combined")]}
                 for name, sel in slices.items()}

    # cost, calls, latency
    perf = {}
    for letter, cfg in CONFIGS:
        rs = [rows[cfg][i] for i in ids]
        called = [r["llm"] for r in rs if (r.get("llm") or {}).get("status") == "called"]
        usd = sum(_usd(r.get("llm"), pin, pout) for r in rs)
        e2e = [(r.get("ms_total") or 0.0) + ((r.get("llm") or {}).get("wall_ms") or 0.0 if (r.get("llm") or {}).get("status") == "called" else 0.0) for r in rs]
        perf[letter] = {
            "checks": len(rs), "model_calls": len(called), "model_calls_avoided": len(rs) - len(called),
            "two_image_calls": sum(1 for x in called if x["mode"] == "two_image"),
            "input_tokens": sum((x.get("usage") or {}).get("inputTokens", 0) for x in called),
            "output_tokens": sum((x.get("usage") or {}).get("outputTokens", 0) for x in called),
            "usd": round(usd, 4), "usd_per_100_checks": round(usd / len(rs) * 100, 3),
            "e2e_ms_p50": _pct(e2e, 0.5), "e2e_ms_p95": _pct(e2e, 0.95),
            "model_ms_p50": _pct([x["wall_ms"] for x in called], 0.5), "model_ms_p95": _pct([x["wall_ms"] for x in called], 0.95),
        }
        if cfg == "combined":
            ms = [r["ms_total"] for r in rs]
            perf["B"] = {"checks": len(rs), "model_calls": 0, "usd": 0.0, "usd_per_100_checks": 0.0,
                         "e2e_ms_p50": _pct(ms, 0.5), "e2e_ms_p95": _pct(ms, 0.95)}
    per_mode = {}
    for cfg in ("llm", "llm2", "combined"):
        for r in rows[cfg].values():
            x = r.get("llm") or {}
            if x.get("status") == "called" and x.get("usage"):
                d = per_mode.setdefault(x["mode"], {"calls": 0, "in": 0, "out": 0, "usd": 0.0})
                d["calls"] += 1
                d["in"] += x["usage"].get("inputTokens", 0)
                d["out"] += x["usage"].get("outputTokens", 0)
                d["usd"] += _usd(x, pin, pout)
    for d in per_mode.values():
        d["usd_per_call"] = round(d["usd"] / d["calls"], 5)
        d["usd"] = round(d["usd"], 4)
    total_calls = sum(perf[L]["model_calls"] for L, _ in CONFIGS)
    total_usd = round(sum(perf[L]["usd"] for L, _ in CONFIGS), 4)

    # where C decided differently from A (and from A')
    diffs = []
    for i in ids:
        a, a2, c = rows["llm"][i], rows["llm2"][i], rows["combined"][i]
        if a["blocked"] != c["blocked"]:
            right = (c["blocked"] if a["kind"] == "bad" else not c["blocked"])
            fig = _figure(man[i], a, c, f"c-vs-a-{i}")
            diffs.append({"id": i, "class": a["class"], "kind": a["kind"], "split": a["split"], "source": a["source"],
                          "opencv": {k: c.get(k) for k in ("decision", "reason_code", "route", "inliers", "scene_status", "change", "ms_total")},
                          "A": _decision_text("llm", a), "A_prime": _decision_text("llm2", a2), "C": _decision_text("combined", c),
                          "A_prime_agrees_with_C": a2["blocked"] == c["blocked"],
                          "C_right": right, "C_reason": _reason(man[i], c), "figure": fig})
    res = {"price": {"input_usd_per_1M": pin, "output_usd_per_1M": pout, "source": price["how"],
                     "publicationDate": price["prices"][0]["publicationDate"], "retrieved_at": price["retrieved_at"],
                     "human_page": price["human_page"]},
           "runs": {cfg: {k: runs[cfg][k] for k in ("ran_at", "code", "model_id", "llm_calls_made", "max_llm_calls", "manifest_sha256")} for cfg in runs},
           "by_class": table, "slices": slice_tab, "perf": perf, "per_mode": per_mode,
           "total_model_calls": total_calls, "total_usd": total_usd, "c_caught_by": c_reasons, "c_differs_from_a": diffs}
    (RES / "compare.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")

    L = ["# A vs A' vs B vs C on the model sample", "",
         f"Sample: {len(ids)} cases (`eval/llm_sample.json`). Model calls made: {total_calls} (A {perf['A']['model_calls']}, "
         f"A' {perf[chr(65) + chr(39)]['model_calls']}, C {perf['C']['model_calls']}); ${total_usd} at ${pin}/M input, ${pout}/M output.", "",
         "| class | kind | n | A | A' | B | C |", "|---|---|---:|---|---|---|---|"]

    def fmt(d: dict, kind: str) -> str:
        if kind == "bad":
            return f"{d['caught']}/{d['caught'] + d['missed'] + d['routed']} caught" + (f" ({d['routed']} routed)" if d["routed"] else "")
        return f"{d['false_blocks']} false block" + ("s" if d["false_blocks"] != 1 else "") + (f" ({d['routed']} routed)" if d["routed"] else "")

    for t in table:
        L.append(f"| {t['class']} | {t['kind']} | {t['n']} | {fmt(t['A'], t['kind'])} | {fmt(t[chr(65) + chr(39)], t['kind'])} | "
                 f"{fmt(t['B'], t['kind'])} | {fmt(t['C'], t['kind'])} |")
    L += ["", "| slice | A caught / bad | A' | B | C | A false blocks / good | A' | B | C |", "|---|---|---|---|---|---|---|---|---|"]
    for name, s in slice_tab.items():
        L.append(f"| {name} | " + " | ".join(f"{s[x]['caught']}/{s[x]['bad']}" + (f" (+{s[x]['routed']} routed)" if x == "B" and s[x]["routed"] else "") for x in ("A", "A'", "B", "C"))
                 + " | " + " | ".join(f"{s[x]['false_blocks']}/{s[x]['good']}" for x in ("A", "A'", "B", "C")) + " |")
    L += ["", "| config | checks | model calls | avoided | 2-photo calls | p50 ms | p95 ms | $ | $ / 100 checks |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in ("A", "A'", "B", "C"):
        p = perf[x]
        L.append(f"| {x} | {p['checks']} | {p['model_calls']} | {p.get('model_calls_avoided', p['checks'])} | {p.get('two_image_calls', 0)} | "
                 f"{p['e2e_ms_p50']} | {p['e2e_ms_p95']} | {p['usd']} | {p['usd_per_100_checks']} |")
    L += ["", "| call mode | calls | input tokens | output tokens | $ | $ per call |", "|---|---:|---:|---:|---:|---:|"]
    for m, d in per_mode.items():
        L.append(f"| {m} | {d['calls']} | {d['in']} | {d['out']} | {d['usd']} | {d['usd_per_call']} |")
    L += ["", f"C's catches on bad cases, by who caught them and why: {c_reasons}", ""]
    L += ["", f"## C decided differently from A: {len(diffs)} cases", ""]
    for d in diffs:
        L += [f"### {d['id']} ({d['kind']}, {d['split']}, {d['source']}) — C {'right' if d['C_right'] else 'WRONG'}; A' agrees with C: {d['A_prime_agrees_with_C']}",
              f"![{d['id']}](../../{d['figure']})", "",
              f"- OpenCV: `{d['opencv']}`", f"- A: {d['A']}", f"- A': {d['A_prime']}", f"- C: {d['C']}", f"- C blocked by: {d['C_reason']}", ""]
    (RES / "compare.md").write_text("\n".join(L) + "\n")
    print(json.dumps({k: res[k] for k in ("total_model_calls", "total_usd", "c_caught_by")}), "diffs", len(diffs))
    for name, s in slice_tab.items():
        print(name, s)
    print(json.dumps(perf, indent=0))
    print(per_mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
