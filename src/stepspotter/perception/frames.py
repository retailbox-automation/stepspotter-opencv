"""A short video instead of a photo: pick the frames worth judging.

A person filming the work with a shaking phone produces a few sharp frames among many
smeared ones. Sample the video evenly, score each sample — sharpness, exposure, and
(when a reference is given) how well it matches the reference scene — drop
near-duplicates, and return the best few. The best one goes down the normal photo
path; the video itself never reaches a model.

OpenCV: ``VideoCapture``, plus the quality and scene checks.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from stepspotter.perception import imgio, quality, scene
from stepspotter.perception import thresholds as T
from stepspotter.perception.models import Keyframe


class VideoUnreadable(ValueError):
    """OpenCV could not open or decode the video."""


def sample_frames(path: str | Path, n: int = T.VIDEO_SAMPLES) -> list[tuple[int, float, np.ndarray]]:
    """Up to ``n`` evenly spaced frames: (index, time in seconds, BGR array)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoUnreadable(f"cannot open {Path(path).name}")
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        out: list[tuple[int, float, np.ndarray]] = []
        if total > 0:
            idxs = sorted({int(round(i * (total - 1) / max(n - 1, 1))) for i in range(n)})
            for i in idxs:
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ok, frame = cap.read()
                if ok and frame is not None:
                    out.append((i, i / fps, frame))
        if not out:  # some containers report no frame count: read straight through
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frames = []
            i = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames.append((i, i / fps, frame))
                i += 1
            step = max(1, len(frames) // n)
            out = frames[::step][:n]
    finally:
        cap.release()
    if not out:
        raise VideoUnreadable(f"no frames could be decoded from {Path(path).name}")
    return out


def _thumb(img: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)


def pick_keyframes(
    path: str | Path,
    reference: np.ndarray | None = None,
    k: int = T.VIDEO_KEYFRAMES,
) -> list[tuple[Keyframe, np.ndarray]]:
    """The ``k`` best frames, best first, with the frame arrays.

    Score = sharpness p90, zeroed for a frame that fails exposure, multiplied by
    (1 + inliers / 100) when a reference is given — a frame that shows the right place
    beats an equally sharp frame of the floor.
    """
    ref_w = imgio.to_work(reference) if reference is not None else None
    scored: list[tuple[Keyframe, np.ndarray, np.ndarray]] = []
    for idx, t, frame in sample_frames(path):
        q = quality.assess(frame)
        exposure_ok = not ({"too_dark", "overexposed", "blank"} & set(q.issues))
        score = q.sharpness_p90 if exposure_ok else 0.0
        inliers = None
        if ref_w is not None and exposure_ok:
            rep, _m = scene.match_scene(ref_w, imgio.to_work(frame))
            inliers = rep.inliers if rep.status == "matched" else 0
            score *= 1.0 + inliers / 100.0
        kf = Keyframe(
            index=idx,
            time_s=round(t, 3),
            score=round(score, 2),
            sharpness_p90=q.sharpness_p90,
            exposure_ok=exposure_ok,
            inliers=inliers,
        )
        scored.append((kf, frame, _thumb(frame)))
    scored.sort(key=lambda s: -s[0].score)
    kept: list[tuple[Keyframe, np.ndarray, np.ndarray]] = []
    for kf, frame, th in scored:
        if any(float(np.abs(th - other).mean()) < T.VIDEO_DUP_MAD for _k, _f, other in kept):
            continue  # a near-duplicate of a better frame already kept
        kept.append((kf, frame, th))
        if len(kept) == k:
            break
    return [(kf, frame) for kf, frame, _t in kept]
