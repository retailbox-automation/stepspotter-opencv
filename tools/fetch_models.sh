#!/usr/bin/env bash
# Fetch the YuNet face detector (opencv_zoo, MIT licence) into models/, so the perception
# layer blurs faces in evidence photos before they are kept or sent to a model.
#
# Run by a person or by the deploy step. The tests never run it and never need it:
# without the file every report says faces_checked=false, and the code claims nothing.
#
# The checksum is the Git LFS oid of this exact file in opencv/opencv_zoo, read from its
# LFS pointer on 2026-10-21 (raw.githubusercontent.com/.../face_detection_yunet_2023mar.onnx:
# "oid sha256:8f2383e4...2552fa4", "size 232589"). A file that does not match is deleted
# and the script fails.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${STEPSPOTTER_MODELS:-$HERE/models}"
NAME="face_detection_yunet_2023mar.onnx"
URL="https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/$NAME"
SHA256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SIZE=232589

mkdir -p "$DEST_DIR"
OUT="$DEST_DIR/$NAME"
TMP="$OUT.part"
curl -fsSL --max-time 120 --max-filesize 1048576 -o "$TMP" "$URL"

if command -v sha256sum >/dev/null 2>&1; then
  GOT="$(sha256sum "$TMP" | cut -d' ' -f1)"
else
  GOT="$(shasum -a 256 "$TMP" | cut -d' ' -f1)"
fi
GOT_SIZE="$(wc -c < "$TMP" | tr -d ' ')"
if [ "$GOT" != "$SHA256" ] || [ "$GOT_SIZE" != "$SIZE" ]; then
  rm -f "${TMP:?}"
  echo "checksum mismatch for $NAME: got $GOT ($GOT_SIZE bytes), want $SHA256 ($SIZE bytes)" >&2
  exit 1
fi
mv "$TMP" "$OUT"
echo "ok: $OUT ($SIZE bytes, sha256 $SHA256)"
