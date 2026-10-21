"""Every number the perception layer decides with, in one place, with where it came from.

Two sources of numbers, and every constant below names one of them:

* **spike 21.10** — ``spike/opencv5/spike.py`` in the hackathon project, run on
  2026-10-21 on the six real OnQ archive photos (the same six that ship in this repo
  under ``fixtures/onq-keystone-smoke/`` and ``src/stepspotter/web/demo_photos/``) plus
  labelled synthetic degradations of them; result in ``spike/opencv5/out/spike-result.json``.
* **exp 21.10** — follow-up measurements made while building this package (same six
  photos, OpenCV 5.0.0): CLAHE before SIFT, real-pair change noise, replay copies,
  glare blobs, motion-blur sharpness. Numbers are quoted inline.

Thresholds were then checked against the eval set (``eval/``): calibration on the
cases built from photos 01/03/05, verification on 02/04/06. The split and the result
live in ``docs/PERCEPTION.md`` and ``eval/results/opencv.json``. If a number here is
moved, rerun ``python eval/run.py --config opencv`` and say why in the commit.

Nothing here is tuned on a single photo. Where the margin is thin, the comment says so.
"""

from __future__ import annotations

# ----------------------------------------------------------------------- working sizes

#: Long side, in pixels, that scene matching and change detection run at.
#: spike 21.10 used 1024. exp 21.10: at the full 1280 px, pairs of DIFFERENT places
#: reached 35 inliers (01->06) with a degenerate homography (scale 0.0), while at
#: 1024 the worst different-place pair had 10. 1024 it is.
WORK_PX = 1024

#: LONG side of the greyscale copy the quality metrics are computed on. spike 21.10
#: scaled the 960x1280 portraits to 512 wide = 683 long; 640 long keeps the same scale
#: within 7 % while making the metric independent of aspect ratio (a landscape photo
#: scaled to 512 WIDE was shrunk 2.5x, a portrait 1.9x, and read sharper for it).
QUALITY_PX = 640

#: Quality tiles per side. Sharpness is the 90th percentile over 4x4 tiles, so a sharp
#: subject on a soft background still passes (spike 21.10).
QUALITY_TILES = 4

# ----------------------------------------------------------------------------- quality

#: A photo shorter than this on its long side is refused as too small to judge.
#: Phones send 3000-4000 px; the web upload caps at 1600 px; the archive is 1280 px.
MIN_LONG_SIDE = 480

#: Mean grey level below which a photo is "too dark". spike 21.10: darkened copies
#: (x0.12) had mean 5.1-18.4; the darkest real original (02-panel-inside, an unlit
#: panel interior) has mean 47.4. 28 sits between them with room on both sides.
DARK_MEAN = 28.0

#: ...or when more than this share of pixels is near-black (< 16). spike 21.10:
#: darkened copies 0.09-1.0 (the 0.09 one is caught by DARK_MEAN); originals <= 0.178.
DARK_FRAC_MAX = 0.6

#: Share of pixels >= 245 above which a photo is "washed out". spike 21.10: over-
#: exposed copies (x3 +40) had 0.23-0.99; originals <= 0.007.
BRIGHT_FRAC_MAX = 0.12

#: Grey-level standard deviation below which there is nothing in the frame (lens
#: covered, blank wall, a flat test image). spike 21.10: originals >= 23.1.
BLANK_STD = 8.0

#: Sharpness floor: p90 of tile Laplacian variance on the greyscale at QUALITY_PX long.
#: exp 21.10, re-measured at this scale on all six photos: originals 73.7-1072.5 (the
#: lowest is 04, a plain jack on a plain wall — the thinnest margin in the set);
#: Gaussian sigma 2 <= 34.2 and sigma 4 <= 11.1 except on 03; motion 15-31 px <= 60.0
#: except on 03. 03 (dense wiring) keeps 68.6 under sigma 2 and 96-353 under motion
#: blur, which is why the ratio below exists. 45 sits under every original with a 1.6x
#: margin; motion blur between 45 and 60 (01, 05, 06) is left to the ratio rule.
SHARP_P90_MIN = 45.0

#: When the evidence matched the reference scene, its sharpness may not fall below
#: this share of the reference's. exp 21.10 at this scale: blurred and motion-blurred
#: copies kept 0.05-0.40 of their original's p90 (03: 0.06-0.33; the 0.40 is 04 under
#: vertical motion, caught by the floor above). Real re-shots of the same place at
#: another distance sit near 1 (spike 21.10, 01 vs 02: 0.66 / 1.5). Applied only after
#: a geometric match, so two different scenes are never compared on texture.
SHARP_RATIO_MIN = 0.22
#: ^ Lowered from 0.35 on 21.10, CALIBRATION half of L2's set only: every blur case that
#: passed the absolute floor had a ratio <= 0.193 (c41 motion), while the real same-place
#: pair c36->c37 — a very sharp photo (p90 2600) next to an even sharper one — scored
#: 0.255 and was wrongly refused at 0.35.

#: The ratio is also read on a WEAK fit — a whole-frame homography that passes every
#: sanity check but has fewer inliers than MIN_INLIERS — because blur is exactly what
#: removes matches. Calibration: the blurred trap frame v0180 kept 16 inliers (sane,
#: coverage 0.82, ratio 0.12) and went to the model with sharpness 55; no good
#: calibration photo has a sane weak fit with coverage >= 0.6. 12 sits above the
#: different-place maximum seen anywhere (10, spike 21.10).
WEAK_FIT_INLIERS = 12

#: ...and only when the evidence covers at least this share of the reference frame, i.e.
#: frames roughly the same view. Eval run 1: close-ups (coverage ~0.3) were refused by the
#: ratio because magnification lowers texture per pixel (02, 06 good_closeup).
REL_SHARP_MIN_COVERAGE = 0.6

#: Largest connected blob of saturated pixels (grey >= 250), as a share of the frame,
#: above which the photo carries a glare NOTE. Advisory only since 21.10 (L1 glare fix):
#: on L2's eval set a frame-wide blob rule refused 14 of 111 good calibration photos
#: (white basins, a white wall, a flashlight hot spot) — good photos had blobs of
#: 0.005-0.035, synthetic glare 0.011-0.025, so blob size cannot tell glare from a
#: white object. exp 21.10: originals <= 0.002; a 5 % glare disc 0.009-0.011.
GLARE_BLOB_FRAC = 0.005
SATURATED_LEVEL = 250

#: Glare BLOCKS only when it newly covers the work zone: the share of the work zone
#: (after alignment) that is saturated in the evidence but not at the same place in the
#: reference (reference mask dilated by GLARE_REF_DILATE_PX). A white basin is white in
#: both photos and does not count; a hot spot on the part being worked on does.
#: Calibrated on the CALIBRATION half of L2's set only (308 cases, 21.10): good photos
#: reached 0.086 (c25 side-lit), 0.067, 0.056, then <= 0.012; the 12 synthetic glare
#: cases 0.060-0.569. 0.10 refuses no good calibration photo (was 14) and still blocks
#: 5 of the 12; the other 7 go on to the model check, which has to pass them itself.
GLARE_ZONE_NEW_FRAC = 0.10
GLARE_REF_DILATE_PX = 15

# ------------------------------------------------------------------------------- scene

#: SIFT features per image and Lowe's ratio (spike 21.10).
SIFT_FEATURES = 2000
LOWE_RATIO = 0.75

#: USAC_MAGSAC reprojection threshold in working pixels, iterations, confidence
#: (spike 21.10).
RANSAC_REPROJ_PX = 4.0
RANSAC_MAX_ITERS = 5000
RANSAC_CONFIDENCE = 0.999

#: Inliers needed to CONFIRM two photos show the same place. Below it OpenCV does not
#: refuse the photo: it routes it to the model with both photos (place_unconfirmed), so
#: the cost of a high bar is a dearer check, never a refused person.
#: spike 21.10 (no CLAHE): different places <= 10. eval run 2 (CLAHE): every pair that
#: did not line up had <= 8 — different rooms (5-8) AND real re-shots of the same place
#: from another view (4-8), so no bar separates those two; every confirmed match had
#: >= 52 (real 01<->02: 52, 79; synthetic >= 118). 25 = 3x the worst unmatched, half the
#: weakest real match. Raised from 20 when a miss stopped being a block (L1b, 21.10).
MIN_INLIERS = 25

#: Inliers / ratio-test matches. Different places that scrape past MIN_INLIERS do it
#: with a low ratio (exp 21.10: 01->06 at 1280 px, 35/57 but a degenerate H).
MIN_INLIER_RATIO = 0.2

#: Homography sanity. Scale = sqrt(area of the evidence frame projected into the
#: reference / area of the evidence frame). DESIGN.md §2: 0.2-5.
SCALE_MIN = 0.2
SCALE_MAX = 5.0

#: The projected evidence quad must overlap the reference frame by at least this
#: share of the smaller of the two areas (containment either way counts as 1.0).
MIN_OVERLAP = 0.35

#: Longest / shortest side of the projected quad. A real hand-held re-shot is a mild
#: trapezoid; a degenerate RANSAC fit is a sliver.
MAX_SIDE_RATIO = 6.0

#: When the whole-frame match fails and a work zone is known, the reference is cropped
#: around the zone (this much padding on each side, as a share of the zone) and
#: matched again at WORK_PX, so a close-up of the work zone still finds its place.
ZONE_CROP_PAD = 0.35

# ------------------------------------------------------------------------------ replay

#: A replay is a photo already sent, sent again. Near-identical means ALL of:
#: the homography moves no corner by more than this share of the diagonal
#: (exp 21.10: a 2 degree rotation moves corners by 1.7 %),
REPLAY_CORNER_SHIFT = 0.04
#: scales by no more than this (exp 21.10: re-encoded / resized copies 0.999-1.001),
REPLAY_SCALE_TOL = 0.05
#: and leaves almost nothing different after alignment: mean absolute grey difference
#: (sigma 1.5 blur) and changed-pixel share. exp 21.10: JPEG q60 / 70 % resize / 2 deg
#: rotation copies had MAD 0.25-0.59 and changed share <= 0.0066. A brightness-shifted
#: copy (+15) has MAD 15 but changed share 0 after CLAHE, hence the normalised MAD.
REPLAY_MAD = 2.5
REPLAY_CHANGED_FRAC = 0.012
#: ...and no changed region of any size: the largest connected changed blob, as a share
#: of the frame. Whole-frame averages hide a small local edit (a part pasted into an
#: otherwise identical frame averaged MAD <= 2.5 and changed <= 0.012). exp 21.10: the
#: copies above left a largest blob <= 0.00003; a pasted part 20 % of a zone wide left
#: >= 0.0003 (0.00033 on a plain wall, 0.001-0.01 elsewhere). Pixels clipped (<= 5 or
#: >= 250) in either photo are ignored: they carry no evidence either way, and a
#: brightened copy clips a lamp-lit wall into a 0.0019 "blob".
REPLAY_BLOB_FRAC = 0.0005

# ------------------------------------------------------------------------------ change

#: Per-pixel change: max over the three Lab channels (after CLAHE on L and a sigma 3
#: blur) above this many levels, then a 5x5 opening (spike 21.10).
CHANGE_DELTA = 28
CHANGE_BLUR_SIGMA = 3.0
CHANGE_OPEN_PX = 5

#: Zones are grown by this share of the frame before "outside" is measured, so a
#: rough box (marker.py: the model's boxes drift and run oversized) does not leak the
#: work itself into the noise floor.
ZONE_MARGIN = 0.04

#: The change outside every zone is the noise floor: parallax, a moved cable, light.
#: exp 21.10: the real pair 01<->02 (another angle, another day) changed 0.37 of the
#: frame after alignment — a homography cannot align 3-D clutter. Above this floor the
#: change map is not trusted to block anything: change becomes informational.
NOISE_FLOOR_MAX = 0.12

#: A zone counts as changed when its changed share is at least this much AND clears
#: the floor by NOISE_MULT x floor + NOISE_ADD. spike 21.10: an edit covering 28 % of a
#: box measured 0.29-0.31 inside it and 0.0 outside; no edit measured 0.0.
ACT_CHANGED_MIN = 0.04
AVOID_CHANGED_MIN = 0.06
NOISE_MULT = 2.5
NOISE_ADD = 0.02

#: A change in an avoid zone this large stops the job for a person even when the work
#: zone changed as well (a hand reaching across the work is fine; rewiring the thing
#: you were told to leave alone is not).
AVOID_LARGE = 0.25

#: A zone is only judged for change when at least this share of it is inside the
#: evidence frame. Eval run 1: a close-up held 1.2 % of a do-not-touch zone, and 7 % of
#: that sliver "changed" (resampling at the edge) — a stop for a person over a zone the
#: photo does not show (05-good_closeup).
ZONE_JUDGE_MIN_VISIBLE = 0.3

#: Share of the work zone that must land inside the evidence frame. Below it the
#: person is asked to step back (DESIGN.md §2: "отойдите — панель целиком").
ZONE_VISIBLE_MIN = 0.6

# ------------------------------------------------------------------------------ video

#: Frames sampled from a video before scoring, and how many keyframes are returned.
VIDEO_SAMPLES = 24
VIDEO_KEYFRAMES = 3
#: Two sampled frames whose 32x32 greyscale thumbnails differ by less than this mean
#: absolute level are near-duplicates; only the sharper one is kept.
VIDEO_DUP_MAD = 4.0

# ----------------------------------------------------------------------------- privacy

#: YuNet face detector (opencv_zoo, MIT). Used only if the file is present.
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
YUNET_SCORE = 0.8
FACE_BLUR_SIGMA = 25.0


def as_dict() -> dict[str, float | int | str]:
    """Every threshold by name, for the report: a decision always says what it used."""
    return {
        k: v
        for k, v in globals().items()
        if k.isupper() and isinstance(v, (int, float, str))
    }
