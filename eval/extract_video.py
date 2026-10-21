"""Extract the frames of Mikhail's own under-sink video that the eval uses.

    python eval/extract_video.py /path/to/IMG_2046.MOV

The source is a phone video Mikhail shot under his own kitchen sink while hunting a leak
(2026-10-20). Consent to publish frames: Mikhail, 2026-10-21T11:38:30Z. The .MOV itself
is NOT in this repository and never will be: its QuickTime metadata carries GPS. Only
frames decoded by OpenCV are written (``cv2.imwrite`` writes a bare JFIF: no EXIF, no
GPS, no device data), downscaled to at most 1600 px on the long side, plus one short
clip re-encoded by ``cv2.VideoWriter`` (no audio track, no source metadata) so the
video -> keyframes path (``perception/frames.py``) can be re-run from the repository.

Every frame kept was looked at by a person (the eval lane, 2026-10-21): no people,
faces, reflections of people, addresses or mail; only the cabinet, pipes, a bowl and
cleaning products. Labels (good / blurred / borderline) were set by eye; see
``eval/cases/public/sources.json`` ("label_by").

Without the .MOV this script cannot run; the committed files are checked by sha256
in sources.json instead.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import cv2

OUT = Path(__file__).resolve().parent / "cases" / "public" / "own-sink-video"
#: frame indices (30 fps) chosen on contact sheets: sharp ones by the highest tile-p90
#: Laplacian within +-4 frames of the moment wanted; blurred ones taken as they are.
FRAMES = [30, 42, 180, 195, 240, 448, 510, 557, 570, 659, 812, 870, 900, 990, 1050, 1106]
#: the clip for the keyframe path: 31.0 s - 36.0 s, every 2nd frame (15 fps), 540x960.
CLIP = (930, 1080, 2, (540, 960))
LONG_SIDE = 1600
JPEG_Q = 92


def main(src: str) -> int:
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {src}")
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(FRAMES)
    c0, c1, cstep, csize = CLIP
    writer = cv2.VideoWriter(str(OUT / "clip-31s-36s.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, csize)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i in want:
            h, w = frame.shape[:2]
            s = min(1.0, LONG_SIDE / max(h, w))
            img = cv2.resize(frame, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
            ok2, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
            assert ok2
            (OUT / f"f{i:04d}.jpg").write_bytes(buf.tobytes())
            print(f"f{i:04d}.jpg {img.shape[1]}x{img.shape[0]} sha256 {hashlib.sha256(buf.tobytes()).hexdigest()[:16]}")
        if c0 <= i < c1 and (i - c0) % cstep == 0:
            writer.write(cv2.resize(frame, csize, interpolation=cv2.INTER_AREA))
        i += 1
    writer.release()
    cap.release()
    print(f"read {i} frames; clip -> {OUT / 'clip-31s-36s.mp4'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(sys.argv[1]))
