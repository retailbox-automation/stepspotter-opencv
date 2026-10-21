"""Pictures of every OpenCV failure in the full B run (eval/results/opencv.json).

    python eval/failures.py   # writes eval/results/figures/opencv-failures-*.jpg

A failure is: a good photo OpenCV refused (false block), a bad photo it let through to
the one-photo model check (missed), or a bad photo it refused for a reason other than the
one the case was built for (right outcome, wrong reason). Each tile: reference | evidence,
the case id, OpenCV's decision and reason. 12 tiles per sheet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"


def tile(case: dict, row: dict, kind: str) -> np.ndarray:
    ims = []
    for rel in (case["reference"], case["evidence"]):
        im = cv2.imread(str(ROOT / rel))
        h, w = im.shape[:2]
        s = min(300 / w, 240 / h)
        im = cv2.resize(im, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        pad = np.full((240, 300, 3), 255, np.uint8)
        pad[: im.shape[0], : im.shape[1]] = im
        ims.append(pad)
    top = np.hstack([ims[0], np.full((240, 8, 3), 255, np.uint8), ims[1]])
    txt = np.full((54, top.shape[1], 3), 255, np.uint8)
    cv2.putText(txt, f"{kind}: {case['id']}"[:80], (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 160), 1, cv2.LINE_AA)
    cv2.putText(txt, f"expected {case['expected']} | OpenCV {row['decision']} ({row['reason_code']}) | inliers {row.get('inliers')}"[:90],
                (4, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    out = np.vstack([top, txt])
    return cv2.copyMakeBorder(out, 6, 6, 6, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def main() -> int:
    man = {c["id"]: c for c in json.loads((ROOT / "eval" / "cases" / "manifest.json").read_text())["cases"]}
    rows = json.loads((RES / "opencv.json").read_text())["rows"]
    picked = []
    for r in rows:
        if r["outcome"] == "false_block":
            picked.append((r, "FALSE BLOCK"))
        elif r["outcome"] == "missed":
            picked.append((r, "MISSED"))
        elif r["outcome"] == "caught" and r["decision"] != r["expected"]:
            picked.append((r, "WRONG REASON"))
    tiles = [tile(man[r["id"]], r, k) for r, k in picked]
    out = RES / "figures"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("opencv-failures-*.jpg"):
        old.unlink()
    for n, i in enumerate(range(0, len(tiles), 12)):
        group = tiles[i:i + 12]
        while len(group) % 3:
            group.append(np.full_like(tiles[0], 255))
        sheet = np.vstack([np.hstack(group[j:j + 3]) for j in range(0, len(group), 3)])
        cv2.imwrite(str(out / f"opencv-failures-{n + 1:02d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 75])
    counts: dict[str, int] = {}
    for _, k in picked:
        counts[k] = counts.get(k, 0) + 1
    print(counts, f"{(len(tiles) + 11) // 12} sheets")
    (RES / "opencv-failures.json").write_text(json.dumps(
        {"counts": counts, "cases": [{"id": r["id"], "what": k, "split": r["split"], "source": r["source"], "expected": r["expected"],
                                      "decision": r["decision"], "reason_code": r["reason_code"], "inliers": r.get("inliers")}
                                     for r, k in picked]}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
