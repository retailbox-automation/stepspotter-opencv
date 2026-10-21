"""Loading and preparing images for the perception checks. Pure functions over numpy.

Every check works on BGR uint8 arrays. Paths are accepted at the edge and turned into
arrays here, once; nothing below this module touches the filesystem except ``render``.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Union

import cv2
import numpy as np

from stepspotter.perception import thresholds as T

ImageLike = Union[str, Path, np.ndarray]


class Unreadable(ValueError):
    """The bytes are not an image OpenCV can decode (or the file is not there)."""


def load(src: ImageLike) -> np.ndarray:
    """A BGR uint8 array from a path or an array. Raises ``Unreadable``.

    Orientation: phone uploads are turned upright (EXIF applied, tag dropped) by
    ``web/photos.save_upload`` before they are written, so the file on disk is already
    the way the person and the model see it.
    """
    if isinstance(src, np.ndarray):
        img = src
    else:
        p = Path(src)
        if not p.is_file():
            raise Unreadable(f"no file at {p.name}")
        data = np.fromfile(str(p), dtype=np.uint8)  # imread chokes on some unicode paths
        img = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
        if img is None:
            raise Unreadable(f"{p.name} is not an image OpenCV can read")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    return img


def to_work(img: np.ndarray, max_px: int = T.WORK_PX) -> np.ndarray:
    """Downscale so the long side is at most ``max_px``. Never upscales."""
    h, w = img.shape[:2]
    s = max_px / max(h, w)
    if s >= 1.0:
        return img
    return cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)


_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def clahe_bgr(img: np.ndarray) -> np.ndarray:
    """Equalise luminance locally (CLAHE on L in Lab), keep colour.

    exp 21.10: doubles SIFT inliers on the real panel pair (33 -> 62) and lets a
    brightness-shifted copy align with zero changed pixels.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = _CLAHE.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def clahe_gray(img: np.ndarray) -> np.ndarray:
    return _CLAHE.apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))


# ---------------------------------------------------------------------- feature cache

_SIFT = None
_FEATS: "OrderedDict[tuple, tuple]" = OrderedDict()
_FEATS_MAX = 64


def sift():
    global _SIFT
    if _SIFT is None:
        _SIFT = cv2.SIFT_create(nfeatures=T.SIFT_FEATURES)
    return _SIFT


def features(img: np.ndarray, key: tuple | None = None) -> tuple[list, np.ndarray | None]:
    """SIFT keypoints + descriptors on the CLAHE greyscale of a WORKING-size image.

    ``key`` (e.g. path + mtime + size) lets the reference and earlier evidence of a
    job be described once per process instead of once per photo submitted.
    """
    if key is not None and key in _FEATS:
        _FEATS.move_to_end(key)
        return _FEATS[key]
    kp, des = sift().detectAndCompute(clahe_gray(img), None)
    out = (list(kp), des)
    if key is not None:
        _FEATS[key] = out
        while len(_FEATS) > _FEATS_MAX:
            _FEATS.popitem(last=False)
    return out


def file_key(src: ImageLike, tag: str = "") -> tuple | None:
    """A cache key for a file on disk: path, size, mtime. None for arrays."""
    if isinstance(src, np.ndarray):
        return None
    try:
        st = Path(src).stat()
    except OSError:
        return None
    return (str(src), st.st_size, st.st_mtime_ns, tag)
