"""Can this photo be judged at all? Sharpness, exposure, glare, size — before any model.

Each failure comes back with ONE instruction a person can act on with the phone in
their hand. Checks run in a fixed order and the first failure names the instruction:
an unlit photo is also "blurry" by the numbers, and telling someone in the dark to hold
still is the wrong advice.

OpenCV: ``Laplacian`` (sharpness), ``calcHist`` (exposure), ``threshold`` +
``connectedComponentsWithStats`` (glare blobs).
"""

from __future__ import annotations

import cv2
import numpy as np

from stepspotter.perception import thresholds as T
from stepspotter.perception.models import QualityReport

#: What to tell a person, per failure. ``{zone}`` is the work zone's label when one is
#: known, otherwise a plain "the thing you worked on".
INSTRUCTIONS: dict[str, str] = {
    "too_small": "This photo is too small to check. Send the full-size photo straight from the camera.",
    "too_dark": "It is too dark to see. Turn on a light or the phone's flashlight, then take the photo again.",
    "overexposed": "The photo is washed out by light. Move out of the direct light or turn the flash off, then take it again.",
    "blank": "I cannot make out anything in this photo. Point the camera at {zone} and take it again.",
    "blurry": "The photo is blurry. Hold the phone still with both hands, or rest it on something, and take it again.",
    "blurry_vs_reference": "This photo is much blurrier than your first one. Hold the phone still and take it again from about the same spot.",
    "glare": "A bright reflection covers part of the photo. Tilt the phone a little or move the light, then take it again.",
    "glare_on_zone": "A bright reflection covers {zone}. Tilt the phone a little or move the light so it is off {zone}, then take it again.",
}


def instruction_for(code: str, zone: str | None = None) -> str:
    return INSTRUCTIONS[code].format(zone=zone or "the thing you worked on")


def _grey_small(img: np.ndarray) -> np.ndarray:
    """Greyscale with the LONG side scaled to QUALITY_PX, or to half its own size if
    that is smaller (never upscaled).

    The long side, not the width: Laplacian energy depends on how much the photo was
    shrunk, and scaling by width made a narrower framing of the very same photo read as
    blurrier (found while testing a frame cropped to half its width).
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    # At least a 2x downscale, which is the scale every threshold was measured at (the
    # 1280 px originals -> 640). Laplacian energy depends on the scale it is read at: a
    # 700 px crop read at 640 (0.9x) looks half as sharp as the same pixels read at 0.5x,
    # and was refused as blurry in eval run 1 (04-good_closeup).
    target = min(T.QUALITY_PX, max(h, w) / 2.0)
    s = target / max(h, w)
    if s < 1.0:
        g = cv2.resize(g, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    return g


def sharpness_p90(img: np.ndarray) -> float:
    """p90 of the Laplacian variance over 4x4 tiles (spike 21.10).

    The best tiles, not the mean: a sharp jack on a soft wall is a sharp photo.
    """
    g = _grey_small(img)
    lap = cv2.Laplacian(g, cv2.CV_64F)
    h, w = g.shape
    n = T.QUALITY_TILES
    th, tw = max(1, h // n), max(1, w // n)
    tiles = [
        float(lap[y : y + th, x : x + tw].var())
        for y in range(0, h - th + 1, th)
        for x in range(0, w - tw + 1, tw)
    ]
    return float(np.percentile(tiles, 90)) if tiles else 0.0


def glare_mask(img: np.ndarray) -> np.ndarray:
    """Saturated pixels (grey >= SATURATED_LEVEL) at the image's own size, as uint8 0/255."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(g, T.SATURATED_LEVEL - 1, 255, cv2.THRESH_BINARY)
    return m


def largest_blob_frac(mask: np.ndarray) -> float:
    n, _labels, stats, _c = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    if n <= 1:
        return 0.0
    return float(stats[1:, cv2.CC_STAT_AREA].max()) / float(mask.size)


def assess(img: np.ndarray, zone: str | None = None) -> QualityReport:
    """Quality of one photo on its own. ``img`` is BGR at any size (original preferred:
    the size check needs it; everything else runs on a 512 px copy)."""
    h, w = img.shape[:2]
    g = _grey_small(img)
    hist = cv2.calcHist([g], [0], None, [256], [0, 256]).ravel() / float(g.size)
    mean = float(g.mean())
    std = float(g.std())
    dark = float(hist[:16].sum())
    bright = float(hist[245:].sum())
    sharp = sharpness_p90(img)
    small = cv2.resize(img, (g.shape[1], g.shape[0]), interpolation=cv2.INTER_AREA)
    blob = largest_blob_frac(glare_mask(small))

    issues: list[str] = []
    if max(h, w) < T.MIN_LONG_SIDE:
        issues.append("too_small")
    if mean < T.DARK_MEAN or dark > T.DARK_FRAC_MAX:
        issues.append("too_dark")
    if bright > T.BRIGHT_FRAC_MAX:
        issues.append("overexposed")
    if std < T.BLANK_STD and "too_dark" not in issues and "overexposed" not in issues:
        issues.append("blank")
    if sharp < T.SHARP_P90_MIN and not ({"too_dark", "overexposed", "blank"} & set(issues)):
        issues.append("blurry")
    if blob > T.GLARE_BLOB_FRAC and "overexposed" not in issues:
        issues.append("glare")

    return QualityReport(
        ok=not issues,
        issues=issues,
        instruction=instruction_for(issues[0], zone) if issues else None,
        width=w,
        height=h,
        sharpness_p90=round(sharp, 2),
        mean=round(mean, 2),
        std=round(std, 2),
        dark_frac=round(dark, 4),
        bright_frac=round(bright, 4),
        glare_blob_frac=round(blob, 5),
    )


def relative_issue(report: QualityReport, ref_sharpness: float, coverage: float | None) -> str | None:
    """After a scene match only: is the evidence far blurrier than its own reference?

    Applied only when the evidence frames roughly the same view as the reference
    (``coverage`` >= REL_SHARP_MIN_COVERAGE). Two photos of the same view carry the same
    texture, so a big drop is blur (exp 21.10: motion-blurred 03 kept 0.08-0.32). A
    close-up shows the work zone magnified — less texture per pixel, not blur — and was
    refused for it in eval run 1 (02, 06 good_closeup: 0.29, 0.26), so it is left to the
    absolute floor. (Comparing the evidence warped onto the reference was tried and
    dropped: the warp's interpolation and a blur-bent fit made that ratio swing from
    0.37 on a sharp re-shot to 5.5 on a blurred copy.)
    """
    if ref_sharpness <= 0 or coverage is None or coverage < T.REL_SHARP_MIN_COVERAGE:
        return None
    ratio = report.sharpness_p90 / ref_sharpness
    report.sharpness_ratio = round(ratio, 3)
    return "blurry_vs_reference" if ratio < T.SHARP_RATIO_MIN else None
