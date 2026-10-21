"""OpenCV's pictures: a caption is never cut off, however narrow the picture."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from stepspotter.perception import render

# the caption that run 2's heatmap cut off after its third line (portrait photo, ~315 px wide)
NOTE = (
    "change map unreliable: 34% of the background changed too (another angle, light or a moved "
    "cable), so a change in a zone proves nothing on its own"
)


def _ink(band: np.ndarray) -> np.ndarray:
    return np.any(band < 200, axis=2)


@pytest.mark.parametrize("width", [180, 236, 315, 640, 1280])
def test_a_long_caption_keeps_every_word_inside_its_band(width):
    lay = render._caption_layout(NOTE, width)
    assert " ".join(lay.lines).split() == NOTE.split()  # nothing dropped, nothing reordered
    for ln in lay.lines:
        assert cv2.getTextSize(ln, render.FONT, lay.scale, 1)[0][0] <= width - 2 * render.PAD, ln

    img = np.zeros((420, width, 3), np.uint8)
    out = render._caption(img, NOTE)
    band = out[: out.shape[0] - img.shape[0]]
    assert band.shape[0] == lay.band_h
    ink = _ink(band)
    rows, cols = np.where(ink.any(axis=1))[0], np.where(ink.any(axis=0))[0]
    # the rendered text's bounding box sits inside the band, clear of every edge
    assert rows.min() >= 2 and rows.max() <= band.shape[0] - 3, (rows.min(), rows.max(), band.shape)
    assert cols.min() >= 2 and cols.max() <= width - 3, (cols.min(), cols.max(), width)
    # and every line was drawn: ink just above each baseline
    for y in lay.baselines:
        assert ink[y - lay.line_h // 2 : y].any(), y


def test_a_word_wider_than_the_picture_is_broken_not_clipped():
    word = "x" * 200
    lay = render._caption_layout(word, 120)
    assert "".join(lay.lines) == word
    out = render._caption(np.zeros((50, 120, 3), np.uint8), word)
    band = out[: out.shape[0] - 50]
    cols = np.where(_ink(band).any(axis=0))[0]
    assert cols.max() <= 120 - 3


def test_a_short_caption_keeps_the_usual_size():
    lay = render._caption_layout("first photo  |  this photo   -   same place", 640)
    assert lay.scale == 0.5 and len(lay.lines) == 1
