"""Deterministic degradations and edits of real photos — for the eval set and the tests.

Nothing in here is used to decide anything. It exists so that "the gate catches a
blurred photo" is a measured claim on our own photos with known ground truth, not a
hope. Every function is a pure function of (image, parameters); anything random takes
an explicit seed. The parameters of every generated case are written into the eval
manifest next to it, so a case can be regenerated and checked byte for byte.
"""

from __future__ import annotations

import cv2
import numpy as np

Box = tuple[float, float, float, float]

# ------------------------------------------------------------------ photometric damage


def gaussian_blur(img: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(img, (0, 0), sigma)


def motion_blur(img: np.ndarray, length: int, angle_deg: float) -> np.ndarray:
    """A straight-line shake of ``length`` px at ``angle_deg``."""
    length = max(3, int(length) | 1)
    k = np.zeros((length, length), np.float32)
    k[length // 2, :] = 1.0
    M = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle_deg, 1.0)
    k = cv2.warpAffine(k, M, (length, length))
    k /= max(float(k.sum()), 1e-6)
    return cv2.filter2D(img, -1, k)


def exposure(img: np.ndarray, gain: float, offset: float = 0.0) -> np.ndarray:
    return np.clip(img.astype(np.float32) * gain + offset, 0, 255).astype(np.uint8)


def gamma(img: np.ndarray, g: float) -> np.ndarray:
    lut = np.clip(((np.arange(256) / 255.0) ** g) * 255.0, 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


def glare(img: np.ndarray, frac: float, cx: float, cy: float) -> np.ndarray:
    """A specular blob covering ~``frac`` of the frame, saturated in its core."""
    h, w = img.shape[:2]
    r = np.sqrt(frac * h * w / np.pi)
    yy, xx = np.mgrid[:h, :w]
    a = np.clip(1.4 - np.hypot(xx - cx * w, yy - cy * h) / r, 0, 1)[..., None]
    return np.clip(img.astype(np.float32) * (1 - a) + 255.0 * a, 0, 255).astype(np.uint8)


def sensor_noise(img: np.ndarray, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(img.astype(np.float32) + rng.normal(0, sigma, img.shape), 0, 255).astype(np.uint8)


def jpeg(img: np.ndarray, quality: int) -> np.ndarray:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR) if ok else img


def resize(img: np.ndarray, factor: float) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (max(1, round(w * factor)), max(1, round(h * factor))), interpolation=cv2.INTER_AREA)


# ------------------------------------------------------------------- geometric changes


def rotate(img: np.ndarray, deg: float) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def perspective(img: np.ndarray, k: float, seed: int) -> np.ndarray:
    """A hand-held re-shot: each corner pulled in by up to ``k`` of the frame."""
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jit = rng.uniform(0, k, size=(4, 2))
    dst = np.float32(
        [
            [w * jit[0, 0], h * jit[0, 1]],
            [w * (1 - jit[1, 0]), h * jit[1, 1]],
            [w * (1 - jit[2, 0]), h * (1 - jit[2, 1])],
            [w * jit[3, 0], h * (1 - jit[3, 1])],
        ]
    )
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REFLECT)


def crop_around(img: np.ndarray, box: Box, min_frac: float = 0.55) -> np.ndarray:
    """A close-up of ``box`` at the photo's own resolution (no upscaling — a phone close-up
    is sharp; an upscaled crop is a blurred photo, and would be refused as one)."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    cw = max(x1 - x0, min_frac) / 2
    ch = max(y1 - y0, min_frac) / 2
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X0, X1 = max(0.0, cx - cw), min(1.0, cx + cw)
    Y0, Y1 = max(0.0, cy - ch), min(1.0, cy + ch)
    return img[int(Y0 * h) : int(Y1 * h), int(X0 * w) : int(X1 * w)].copy()


def cut_zone(img: np.ndarray, box: Box, keep_frac: float = 0.25) -> np.ndarray:
    """The person stood too close / aimed off: the frame keeps only ``keep_frac`` of the
    zone's width, on the side away from the frame centre, plus everything beyond it."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    zone_cx = (x0 + x1) / 2
    if zone_cx >= 0.5:  # zone on the right: cut the frame off inside the zone, keep the left
        cut = x0 + (x1 - x0) * keep_frac
        return img[:, : max(int(cut * w), int(0.5 * w))].copy()
    cut = x1 - (x1 - x0) * keep_frac
    return img[:, min(int(cut * w), int(0.5 * w)) :].copy()


# ------------------------------------------------------------------------ content edits


def paste_patch(img: np.ndarray, box: Box, patch: np.ndarray, cover: float = 0.45, seed: int = 0) -> np.ndarray:
    """Put a foreign part into ``box`` — a new object where the work happened.

    The patch is scaled to cover ``cover`` of the box's width, placed at a seeded
    position inside it.
    """
    rng = np.random.default_rng(seed)
    out = img.copy()
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    bw, bh = max(x1 - x0, 4), max(y1 - y0, 4)
    pw = max(4, int(bw * cover))
    ph = max(4, min(int(pw * patch.shape[0] / patch.shape[1]), int(bh * 0.9)))
    p = cv2.resize(patch, (pw, ph), interpolation=cv2.INTER_AREA)
    px = x0 + int(rng.uniform(0, max(bw - pw, 1)))
    py = y0 + int(rng.uniform(0, max(bh - ph, 1)))
    out[py : py + ph, px : px + pw] = p[: max(0, min(ph, h - py)), : max(0, min(pw, w - px))]
    return out
