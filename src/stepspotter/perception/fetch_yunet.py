"""Fetch and verify the YuNet face detector — for the container build and for people.

    python -m stepspotter.perception.fetch_yunet --dest /app/models

The image is built from ``git archive HEAD`` (infra/buildspec.yml), and the ONNX file is
kept out of git, so the Dockerfile runs this at build time: download from opencv_zoo,
check the size and the SHA256 against the values pinned below, write the MIT notice
beside it, and fail the build on any mismatch. ``tools/fetch_models.sh`` does the same
for a checkout (a test keeps the two pinned values identical).

The pins are the Git LFS oid and size of this exact file in opencv/opencv_zoo, read from
its LFS pointer on 2026-10-21. Licence: MIT, Copyright (c) 2020 Shiqi Yu
(opencv_zoo/models/face_detection_yunet/LICENSE, read the same day).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from stepspotter.perception import thresholds as T

NAME = T.YUNET_FILE
URL = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/{NAME}"
SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SIZE = 232589
LICENSE_NAME = "LICENSE-face_detection_yunet.txt"
LICENSE_TEXT = """YuNet face detector (face_detection_yunet_2023mar.onnx), from
https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet

MIT License

Copyright (c) 2020 Shiqi Yu <shiqi.yu@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def verify(data: bytes) -> str | None:
    """None when the bytes are the pinned file, else what is wrong with them."""
    if len(data) != SIZE:
        return f"size {len(data)} != {SIZE}"
    got = hashlib.sha256(data).hexdigest()
    if got != SHA256:
        return f"sha256 {got} != {SHA256}"
    return None


def fetch(dest: Path, timeout: float = 120.0) -> Path:
    """Download, verify, write. Raises RuntimeError on any mismatch; writes nothing then."""
    req = urllib.request.Request(URL, headers={"User-Agent": "stepspotter-build"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - pinned https URL
        data = resp.read(SIZE + 1)
    problem = verify(data)
    if problem:
        raise RuntimeError(f"{NAME} from {URL} failed verification: {problem}")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / NAME
    out.write_bytes(data)
    (dest / LICENSE_NAME).write_text(LICENSE_TEXT)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, help="directory to write the model and its licence into")
    args = ap.parse_args(argv)
    try:
        out = fetch(Path(args.dest))
    except Exception as exc:  # noqa: BLE001 - a build step: say why and fail
        print(f"fetch_yunet: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {out} ({SIZE} bytes, sha256 {SHA256})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
