"""What changed, and where: inside the work zone, inside a do-not-touch zone, or everywhere.

The evidence is warped onto the reference grid with the scene homography, both images
are equalised (CLAHE on L in Lab, so a lamp switched on is not a "change"), blurred
(sigma 3) and differenced; a pixel changed when any Lab channel moved more than 28
levels, then a 5x5 opening removes speckle (spike 21.10).

The one rule that makes this usable on real photos: **a zone's change is only read
against the change outside every zone.** A homography aligns a plane; a panel full of
cables is not one, so a re-shot from another angle "changes" everywhere (exp 21.10:
0.37 of the frame on the real pair 01<->02). When that outside share — the noise
floor — is high, the map says nothing about the zones and is reported as
``unreliable``: informational, never a block.

OpenCV: ``warpPerspective``, ``cvtColor(LAB)``, ``createCLAHE``, ``GaussianBlur``,
``absdiff``, ``morphologyEx``, ``erode``.
"""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from stepspotter.perception import imgio
from stepspotter.perception import thresholds as T
from stepspotter.perception.models import ChangeReport, ZoneChange

Zone = tuple[str, str, tuple[float, float, float, float]]  # (label, kind, (x0,y0,x1,y1) normalised)


def warp_into(ev: np.ndarray, H: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Evidence on the reference grid, plus the mask of pixels it actually covers.

    The mask is eroded by a few pixels: interpolation at the warped border invents a
    thin frame of "change" that is nobody's work.
    """
    w, h = size
    warped = cv2.warpPerspective(ev, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    cover = cv2.warpPerspective(np.full(ev.shape[:2], 255, np.uint8), H, (w, h), flags=cv2.INTER_NEAREST)
    cover = cv2.erode(cover, np.ones((7, 7), np.uint8))
    return warped, cover > 0


def _lab(img: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(
        cv2.cvtColor(imgio.clahe_bgr(img), cv2.COLOR_BGR2LAB), (0, 0), T.CHANGE_BLUR_SIGMA
    ).astype(np.int16)


def change_mask(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Boolean map of changed pixels between two aligned images of the same size."""
    d = cv2.absdiff(_lab(a), _lab(b)).max(axis=2) > T.CHANGE_DELTA
    k = np.ones((T.CHANGE_OPEN_PX, T.CHANGE_OPEN_PX), np.uint8)
    d = cv2.morphologyEx(d.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)
    return d & valid


def normalised_mad(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> float:
    """Mean absolute grey difference after matching b's mean and contrast to a's.

    So a copy with the brightness nudged is still the same photo (exp 21.10: +15
    levels gave MAD 15 raw, ~0 normalised), while a different moment is not.
    """
    if not valid.any():
        return 255.0
    ga = cv2.GaussianBlur(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), (0, 0), 1.5).astype(np.float32)[valid]
    gb = cv2.GaussianBlur(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), (0, 0), 1.5).astype(np.float32)[valid]
    sa, sb = float(ga.std()), float(gb.std())
    gb = (gb - gb.mean()) * (sa / sb if sb > 1e-6 else 1.0) + ga.mean()
    return float(np.abs(ga - gb).mean())


def zone_mask(shape: tuple[int, int], box: tuple[float, float, float, float], grow: float = 0.0) -> np.ndarray:
    h, w = shape
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = max(0.0, x0 - grow), max(0.0, y0 - grow), min(1.0, x1 + grow), min(1.0, y1 + grow)
    m = np.zeros((h, w), bool)
    m[int(y0 * h) : max(int(y1 * h), int(y0 * h) + 1), int(x0 * w) : max(int(x1 * w), int(x0 * w) + 1)] = True
    return m


def measure(
    baseline: np.ndarray,
    warped_ev: np.ndarray,
    valid: np.ndarray,
    zones: Iterable[Zone],
    baseline_name: str = "reference",
) -> tuple[ChangeReport, np.ndarray]:
    """Per-zone change between a baseline and the aligned evidence (same grid).

    Returns the report and the changed-pixel mask (for the heatmap).
    """
    zones = list(zones)
    mask = change_mask(baseline, warped_ev, valid)
    shape = mask.shape
    acts = [z for z in zones if z[1] == "act"]
    avoids = [z for z in zones if z[1] in ("avoid", "stop")]
    if not acts and not avoids:
        return ChangeReport(status="not_applicable", baseline=baseline_name, note="no zones to measure"), mask

    def one(z: Zone) -> ZoneChange:
        zm = zone_mask(shape, z[2])
        vis = zm & valid
        frac = float(mask[vis].mean()) if vis.any() else 0.0
        return ZoneChange(
            label=z[0],
            kind=z[1],
            changed_frac=round(frac, 4),
            visible_frac=round(float(vis.sum()) / max(float(zm.sum()), 1.0), 3),
        )

    act_rows = [one(z) for z in acts]
    avoid_rows = [one(z) for z in avoids]

    grown = np.zeros(shape, bool)
    for z in zones:
        grown |= zone_mask(shape, z[2], T.ZONE_MARGIN)
    outside = valid & ~grown
    if outside.sum() < 0.05 * mask.size:
        return (
            ChangeReport(
                status="unreliable",
                baseline=baseline_name,
                act=act_rows,
                avoid=avoid_rows,
                note="the zones cover almost the whole photo, so there is no background to measure noise on",
            ),
            mask,
        )
    floor = float(mask[outside].mean())
    bar = T.NOISE_MULT * floor + T.NOISE_ADD
    # Only zones the photo actually shows are judged (ZONE_JUDGE_MIN_VISIBLE).
    act_seen = [r for r in act_rows if r.visible_frac >= T.ZONE_JUDGE_MIN_VISIBLE]
    avoid_seen = [r for r in avoid_rows if r.visible_frac >= T.ZONE_JUDGE_MIN_VISIBLE]
    act_changed = any(r.changed_frac >= max(T.ACT_CHANGED_MIN, bar) for r in act_seen) if act_seen else None
    avoid_touched = (
        any(r.changed_frac >= max(T.AVOID_CHANGED_MIN, bar) for r in avoid_seen) if avoid_seen else None
    )
    if floor > T.NOISE_FLOOR_MAX:
        return (
            ChangeReport(
                status="unreliable",
                baseline=baseline_name,
                act=act_rows,
                avoid=avoid_rows,
                outside_frac=round(floor, 4),
                act_changed=act_changed,
                avoid_touched=avoid_touched,
                note=f"{floor:.0%} of the background changed too (another angle, light or a moved cable), "
                "so a change in a zone proves nothing on its own",
            ),
            mask,
        )
    return (
        ChangeReport(
            status="measured",
            baseline=baseline_name,
            act=act_rows,
            avoid=avoid_rows,
            outside_frac=round(floor, 4),
            act_changed=act_changed,
            avoid_touched=avoid_touched,
        ),
        mask,
    )
