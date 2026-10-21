"""Faces in an evidence photo are blurred before the photo is kept or sent to a model.

The detector is YuNet from opencv_zoo (MIT), run through ``cv2.FaceDetectorYN``. The
ONNX file is NOT shipped in this repository and is never downloaded by the code or the
tests. ``tools/fetch_models.sh`` fetches it (a person or the deploy step runs that,
with the checksum check in the script); until the file is present, every report says
``faces_checked=False`` — the layer never claims a check it did not run.

Where the file is looked for: ``$STEPSPOTTER_MODELS`` if set, otherwise ``models/`` at
the repository root (the container copies the same directory).

OpenCV: ``FaceDetectorYN``, ``GaussianBlur``.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

from stepspotter.perception import thresholds as T
from stepspotter.perception.models import PrivacyReport

MODELS_ENV = "STEPSPOTTER_MODELS"

_DETECTOR = None
_DETECTOR_PATH: Path | None = None


def models_dir() -> Path:
    env = os.environ.get(MODELS_ENV)
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[3] / "models"


def model_path() -> Path | None:
    p = models_dir() / T.YUNET_FILE
    return p if p.is_file() else None


def _detector(path: Path):
    global _DETECTOR, _DETECTOR_PATH
    if _DETECTOR is None or _DETECTOR_PATH != path:
        _DETECTOR = cv2.FaceDetectorYN.create(str(path), "", (320, 320), T.YUNET_SCORE, 0.3, 5000)
        _DETECTOR_PATH = path
    return _DETECTOR


def blur_faces(img: np.ndarray) -> tuple[np.ndarray, PrivacyReport]:
    """Return (image with faces blurred, report). Without the model: unchanged + honest flag."""
    path = model_path()
    if path is None:
        return img, PrivacyReport(
            faces_checked=False,
            note=f"face detector not installed ({T.YUNET_FILE} not in {models_dir().name}/); "
            "faces were not checked",
        )
    try:
        det = _detector(path)
        h, w = img.shape[:2]
        det.setInputSize((w, h))
        _n, faces = det.detect(img)
    except cv2.error as exc:  # a corrupt or mismatched model file is not a face check
        return img, PrivacyReport(faces_checked=False, model=path.name, note=f"detector failed: {exc}")
    out = img.copy()
    count = 0
    for f in faces if faces is not None else []:
        x, y, fw, fh = (int(round(v)) for v in f[:4])
        pad = int(0.25 * max(fw, fh))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + fw + pad), min(h, y + fh + pad)
        if x1 <= x0 or y1 <= y0:
            continue
        out[y0:y1, x0:x1] = cv2.GaussianBlur(out[y0:y1, x0:x1], (0, 0), T.FACE_BLUR_SIGMA)
        count += 1
    return out, PrivacyReport(faces_checked=True, faces_blurred=count, model=path.name)
