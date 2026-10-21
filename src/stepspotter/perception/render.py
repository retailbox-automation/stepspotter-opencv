"""Pictures of what OpenCV saw, for the person and for a judge. Never used to decide.

Three images per inspected photo:

* ``match``   — reference | evidence side by side, the geometric inliers as lines, the
                evidence frame's outline projected onto the reference;
* ``heatmap`` — the evidence aligned onto the reference, changed pixels in red-yellow,
                work zones in green and do-not-touch zones in red, each with its
                changed share;
* ``quality`` — one bar per quality metric against its threshold.

Colours match the step card: green = work here, red = do not touch.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from stepspotter.perception import thresholds as T
from stepspotter.perception.inspect import Detail
from stepspotter.perception.models import PerceptionReport

GREEN = (60, 160, 0)  # BGR
RED = (48, 30, 200)
ORANGE = (0, 125, 225)
INK = (30, 24, 21)
GREY = (150, 150, 150)
PAPER = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _fit_h(img: np.ndarray, h: int) -> np.ndarray:
    s = h / img.shape[0]
    return cv2.resize(img, (max(1, round(img.shape[1] * s)), h), interpolation=cv2.INTER_AREA)


def _wrap(text: str, width_px: int, scale: float) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if cv2.getTextSize(trial, FONT, scale, 1)[0][0] <= width_px or not line:
            line = trial
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines[:3]


def _caption(img: np.ndarray, text: str, color=INK) -> np.ndarray:
    """A white band above the image with the text wrapped to its width (3 lines max)."""
    scale = 0.5
    lines = _wrap(text, img.shape[1] - 16, scale)
    bar = np.full((10 + 20 * len(lines), img.shape[1], 3), 255, np.uint8)
    for i, ln in enumerate(lines):
        cv2.putText(bar, ln, (8, 22 + 20 * i), FONT, scale, color, 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def match_image(rep: PerceptionReport, d: Detail, height: int = 420) -> np.ndarray | None:
    if d.reference is None or d.evidence is None:
        return None
    ref, ev = d.reference, d.evidence
    sr, se = height / ref.shape[0], height / ev.shape[0]
    a, b = _fit_h(ref, height).copy(), _fit_h(ev, height).copy()
    gap = 8
    canvas = np.full((height, a.shape[1] + gap + b.shape[1], 3), 255, np.uint8)
    canvas[:, : a.shape[1]] = a
    canvas[:, a.shape[1] + gap :] = b
    off = a.shape[1] + gap
    matched = rep.scene is not None and rep.scene.status == "matched"
    color = GREEN if matched else RED
    m = d.match
    if m is not None and m.src is not None and m.dst is not None and len(m.src):
        idx = np.linspace(0, len(m.src) - 1, num=min(60, len(m.src))).astype(int)
        for i in idx:
            p_ev = (int(m.src[i][0] * se) + off, int(m.src[i][1] * se))
            p_ref = (int(m.dst[i][0] * sr), int(m.dst[i][1] * sr))
            cv2.line(canvas, p_ref, p_ev, color, 1, cv2.LINE_AA)
            cv2.circle(canvas, p_ref, 3, color, -1, cv2.LINE_AA)
            cv2.circle(canvas, p_ev, 3, color, -1, cv2.LINE_AA)
    if matched and rep.scene and rep.scene.H is not None:
        eh, ew = ev.shape[:2]
        corners = np.float32([[0, 0], [ew, 0], [ew, eh], [0, eh]]).reshape(-1, 1, 2)
        quad = cv2.perspectiveTransform(corners, np.array(rep.scene.H)).reshape(-1, 2) * sr
        cv2.polylines(canvas, [quad.astype(np.int32)], True, GREEN, 2, cv2.LINE_AA)
    s = rep.scene
    if s is None or s.status == "no_reference":
        text = "no reference photo to compare with"
    elif matched:
        text = f"same place: {s.inliers} inliers of {s.good} matches ({s.method}), scale {s.scale}"
    else:
        text = f"no match: {s.rejected_because}"
    return _caption(canvas, "first photo  |  this photo   -   " + text, color)


def heatmap_image(rep: PerceptionReport, d: Detail, height: int = 420) -> np.ndarray | None:
    if d.warped is None or d.change_mask is None or d.valid is None:
        return None
    base = d.warped.copy()
    base[~d.valid] = (base[~d.valid] * 0.25).astype(np.uint8)
    heat = cv2.GaussianBlur(d.change_mask.astype(np.float32), (0, 0), 4)
    heat = np.clip(heat / max(float(heat.max()), 1e-6), 0, 1)
    colour = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_HOT)
    alpha = (heat * 0.75)[..., None]
    out = (base * (1 - alpha) + colour * alpha).astype(np.uint8)
    h, w = out.shape[:2]
    rows = {z.label: z for z in (rep.change.act + rep.change.avoid)} if rep.change else {}
    for label, kind, (x0, y0, x1, y1) in d.zones:
        c = GREEN if kind == "act" else (RED if kind == "avoid" else ORANGE)
        p0, p1 = (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h))
        cv2.rectangle(out, p0, p1, c, 3, cv2.LINE_AA)
        z = rows.get(label)
        tag = f"{label}: {z.changed_frac:.0%} changed" if z else label
        cv2.putText(out, tag[:40], (p0[0] + 4, max(18, p0[1] - 6)), FONT, 0.6, PAPER, 3, cv2.LINE_AA)
        cv2.putText(out, tag[:40], (p0[0] + 4, max(18, p0[1] - 6)), FONT, 0.6, c, 1, cv2.LINE_AA)
    out = _fit_h(out, height)
    ch = rep.change
    if ch is None:
        text = "change: not measured"
    elif ch.status == "measured":
        text = f"change since {ch.baseline}; background {ch.outside_frac:.0%} (noise floor)"
    else:
        text = f"change map {ch.status}: {ch.note or ''}"
    return _caption(out, text, RED if rep.decision == "touched_avoid" else INK)


def quality_image(rep: PerceptionReport, width: int = 560) -> np.ndarray | None:
    q = rep.quality
    if q is None:
        return None
    # (name, value, threshold, lower-is-bad, display max)
    bars = [
        ("sharpness", q.sharpness_p90, T.SHARP_P90_MIN, True, max(200.0, T.SHARP_P90_MIN * 4)),
        ("brightness", q.mean, T.DARK_MEAN, True, 255.0),
        ("washed-out share", q.bright_frac, T.BRIGHT_FRAC_MAX, False, 0.5),
        ("largest glare patch", q.glare_blob_frac, T.GLARE_BLOB_FRAC, False, 0.03),
    ]
    row_h, label_w = 30, 170
    img = np.full((row_h * len(bars) + 14, width, 3), 255, np.uint8)
    for i, (name, val, thr, low_bad, top) in enumerate(bars):
        y = 10 + i * row_h
        bad = val < thr if low_bad else val > thr
        x0, x1 = label_w, width - 70
        frac = min(max(val / top, 0.0), 1.0)
        cv2.putText(img, name, (8, y + 17), FONT, 0.5, INK, 1, cv2.LINE_AA)
        cv2.rectangle(img, (x0, y + 4), (x1, y + 22), (235, 235, 235), -1)
        cv2.rectangle(img, (x0, y + 4), (x0 + int(frac * (x1 - x0)), y + 22), RED if bad else GREEN, -1)
        tx = x0 + int(min(thr / top, 1.0) * (x1 - x0))
        cv2.line(img, (tx, y), (tx, y + 26), INK, 2)
        shown = f"{val:.0f}" if top > 1 else f"{val:.3f}"
        cv2.putText(img, shown, (x1 + 6, y + 18), FONT, 0.5, RED if bad else INK, 1, cv2.LINE_AA)
    return _caption(img, f"quality ({'ok' if q.ok else ', '.join(q.issues)})  - black tick = threshold")


def render_all(rep: PerceptionReport, d: Detail, dest_dir: str | Path, stem: str) -> dict[str, str]:
    """Write whichever of the three images apply; return {kind: path}. Never raises."""
    out: dict[str, str] = {}
    dest = Path(dest_dir)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        return out
    for kind, img in (
        ("match", match_image(rep, d)),
        ("heatmap", heatmap_image(rep, d)),
        ("quality", quality_image(rep)),
    ):
        if img is None:
            continue
        p = dest / f"{stem}-{kind}.jpg"
        try:
            if cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 85]):
                out[kind] = str(p)
        except cv2.error:
            continue
    return out
