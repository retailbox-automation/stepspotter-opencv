"""Is the evidence the same place as the reference? And is it a photo we have seen?

Same place: SIFT (2000 features, on CLAHE luminance) + Lowe ratio 0.75 +
``findHomography(USAC_MAGSAC)``, then a sanity check on the homography itself —
because RANSAC always returns *something*, and on cluttered wiring two different
places can produce dozens of "inliers" that fit a sliver (exp 21.10: 01->06 at full
resolution, 35 inliers, scale 0.0). A match must be:

* enough inliers, and a large enough share of the ratio-test matches;
* orientation-preserving (det of the affine part > 0) with a convex projected quad;
* a plausible scale (0.2-5) and not a sliver (side ratio <= 6);
* overlapping the reference frame (containment either way counts).

When the whole frame does not match and the step has a work zone, the reference is
cropped around that zone and matched again — a close-up of the work zone is the most
common legitimate evidence, and in a 1024 px overview the zone may be 150 px wide.

Replay: a photo already seen is near-identical after alignment — H close to identity
AND (almost) nothing different, anywhere: not on average and not in any one patch. Not a
byte hash: a re-encoded, resized or slightly
rotated copy must still be caught (exp 21.10: all three at MAD <= 0.6).

OpenCV: ``SIFT_create``, ``BFMatcher.knnMatch``, ``findHomography(USAC_MAGSAC)``,
``perspectiveTransform``, ``isContourConvex``, ``intersectConvexConvex``.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from stepspotter.perception import change as _change
from stepspotter.perception import imgio
from stepspotter.perception import thresholds as T
from stepspotter.perception.models import ReplayReport, SceneMatch


@dataclass
class Match:
    """A raw match, before it is judged sane: everything the report and render need."""

    good: int
    inliers: int
    H: np.ndarray | None  # evidence -> reference working pixels
    src: np.ndarray | None = None  # evidence points (inliers)
    dst: np.ndarray | None = None  # reference points (inliers)


def raw_match(f_ev: tuple, f_ref: tuple) -> Match:
    (kev, dev), (kref, dref) = f_ev, f_ref
    if dev is None or dref is None or len(kev) < 8 or len(kref) < 8:
        return Match(0, 0, None)
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(dev, dref, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < T.LOWE_RATIO * p[1].distance]
    if len(good) < 8:
        return Match(len(good), 0, None)
    src = np.float32([kev[g.queryIdx].pt for g in good])
    dst = np.float32([kref[g.trainIdx].pt for g in good])
    H, mask = cv2.findHomography(
        src,
        dst,
        cv2.USAC_MAGSAC,
        T.RANSAC_REPROJ_PX,
        maxIters=T.RANSAC_MAX_ITERS,
        confidence=T.RANSAC_CONFIDENCE,
    )
    if H is None or mask is None:
        return Match(len(good), 0, None)
    keep = mask.ravel().astype(bool)
    return Match(len(good), int(keep.sum()), H, src[keep], dst[keep])


def project_quad(H: np.ndarray, w: int, h: int) -> np.ndarray:
    """The evidence frame's four corners, mapped into the reference."""
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(corners, H).reshape(-1, 2)


def sanity(H: np.ndarray, ev_size: tuple[int, int], ref_size: tuple[int, int]) -> tuple[str | None, dict]:
    """Return (why it is NOT sane or None, the measured geometry)."""
    ew, eh = ev_size
    rw, rh = ref_size
    geo: dict[str, float | None] = {"scale": None, "overlap": None, "coverage": None, "side_ratio": None}
    if not np.all(np.isfinite(H)) or abs(H[2, 2]) < 1e-12:
        return "the homography is not finite", geo
    det = float(np.linalg.det(H[:2, :2] / H[2, 2]))
    if det <= 0:
        return "the fit mirrors the image", geo
    quad = project_quad(H, ew, eh)
    if not np.all(np.isfinite(quad)):
        return "the fit sends a corner to infinity", geo
    if not cv2.isContourConvex(quad.astype(np.float32).reshape(-1, 1, 2)):
        return "the projected frame is not convex", geo
    area = float(cv2.contourArea(quad.astype(np.float32)))
    scale = float(np.sqrt(max(area, 0.0) / float(ew * eh)))
    sides = [float(np.linalg.norm(quad[i] - quad[(i + 1) % 4])) for i in range(4)]
    side_ratio = max(sides) / max(min(sides), 1e-6)
    ref_quad = np.float32([[0, 0], [rw, 0], [rw, rh], [0, rh]])
    inter, _poly = cv2.intersectConvexConvex(quad.astype(np.float32), ref_quad)
    overlap = float(inter) / max(min(area, float(rw * rh)), 1e-6)
    coverage = float(inter) / float(rw * rh)
    geo = {
        "scale": round(scale, 3),
        "overlap": round(overlap, 3),
        "coverage": round(coverage, 3),
        "side_ratio": round(side_ratio, 2),
    }
    if not (T.SCALE_MIN <= scale <= T.SCALE_MAX):
        return f"implausible scale {scale:.2f}", geo
    if side_ratio > T.MAX_SIDE_RATIO:
        return f"the projected frame is a sliver (sides {side_ratio:.1f}:1)", geo
    if overlap < T.MIN_OVERLAP:
        return f"it barely overlaps the reference ({overlap:.2f})", geo
    return None, geo


def _judge(m: Match, ev_size, ref_size) -> tuple[str | None, dict]:
    if m.H is None:
        return f"too few matches ({m.good})", {}
    if m.inliers < T.MIN_INLIERS:
        return f"only {m.inliers} geometric inliers (need {T.MIN_INLIERS})", {}
    ratio = m.inliers / max(m.good, 1)
    if ratio < T.MIN_INLIER_RATIO:
        return f"inlier share {ratio:.2f} is too low", {}
    return sanity(m.H, ev_size, ref_size)


def _zone_crop(ref: np.ndarray, zone: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Crop the reference around one zone (normalised x0,y0,x1,y1), upscale to WORK_PX.

    Returns (crop, C) where C maps crop pixels back to reference working pixels.
    """
    h, w = ref.shape[:2]
    x0, y0, x1, y1 = zone
    bw, bh = max(x1 - x0, 1e-3), max(y1 - y0, 1e-3)
    X0 = max(0.0, x0 - T.ZONE_CROP_PAD * bw)
    Y0 = max(0.0, y0 - T.ZONE_CROP_PAD * bh)
    X1 = min(1.0, x1 + T.ZONE_CROP_PAD * bw)
    Y1 = min(1.0, y1 + T.ZONE_CROP_PAD * bh)
    px0, py0, px1, py1 = int(X0 * w), int(Y0 * h), max(int(X1 * w), int(X0 * w) + 2), max(int(Y1 * h), int(Y0 * h) + 2)
    crop = ref[py0:py1, px0:px1]
    s = T.WORK_PX / max(crop.shape[:2])
    crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    C = np.array([[1 / s, 0, px0], [0, 1 / s, py0], [0, 0, 1]], dtype=np.float64)
    return crop, C


def match_scene(
    ref: np.ndarray,
    ev: np.ndarray,
    zone: tuple[float, float, float, float] | None = None,
    ref_key: tuple | None = None,
    ev_key: tuple | None = None,
) -> tuple[SceneMatch, Match | None]:
    """Match WORKING-size evidence to a WORKING-size reference.

    Returns the report and the raw match that was accepted (or the best rejected one,
    for the render), with H always expressed evidence -> reference working pixels.
    """
    rh, rw = ref.shape[:2]
    eh, ew = ev.shape[:2]
    f_ref = imgio.features(ref, ref_key)
    f_ev = imgio.features(ev, ev_key)
    m = raw_match(f_ev, f_ref)
    why, geo = _judge(m, (ew, eh), (rw, rh))
    method = "whole_frame"
    best = m
    if why is not None and zone is not None:
        crop, C = _zone_crop(ref, zone)
        mz = raw_match(f_ev, imgio.features(crop))
        if mz.H is not None:
            mz = Match(mz.good, mz.inliers, C @ mz.H, mz.src, cv2.perspectiveTransform(mz.dst.reshape(-1, 1, 2), C).reshape(-1, 2) if mz.dst is not None and len(mz.dst) else mz.dst)
        why_z, geo_z = _judge(mz, (ew, eh), (rw, rh))
        if why_z is None:
            m, why, geo, method, best = mz, None, geo_z, "zone_crop", mz
        elif mz.inliers > m.inliers:
            best = mz
    report = SceneMatch(
        status="matched" if why is None else "not_matched",
        method=method if why is None else "none",
        good=best.good,
        inliers=best.inliers,
        inlier_ratio=round(best.inliers / max(best.good, 1), 3),
        scale=geo.get("scale"),
        overlap=geo.get("overlap"),
        coverage=geo.get("coverage"),
        side_ratio=geo.get("side_ratio"),
        rejected_because=why,
        H=m.H.tolist() if (why is None and m.H is not None) else None,
        ref_size=(rw, rh),
        ev_size=(ew, eh),
    )
    return report, best


# ----------------------------------------------------------------------------- replay


def identity_distance(H: np.ndarray, w: int, h: int) -> tuple[float, float]:
    """(largest corner displacement / diagonal, scale) of H against the identity."""
    quad = project_quad(H, w, h)
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    shift = float(np.linalg.norm(quad - corners, axis=1).max()) / float(np.hypot(w, h))
    area = float(cv2.contourArea(quad.astype(np.float32)))
    return shift, float(np.sqrt(max(area, 0.0) / float(w * h)))


def is_replay(
    earlier: np.ndarray,
    ev: np.ndarray,
    earlier_key: tuple | None = None,
    ev_key: tuple | None = None,
) -> tuple[bool, dict]:
    """Near-identical after alignment? Both images WORKING size.

    Different sizes are fine (a resized copy is the same photo); the comparison is
    made after resizing the evidence onto the earlier photo's grid.
    """
    eh, ew = earlier.shape[:2]
    ev_r = ev if ev.shape[:2] == earlier.shape[:2] else cv2.resize(ev, (ew, eh), interpolation=cv2.INTER_AREA)
    m = raw_match(imgio.features(ev_r, ev_key if ev_r is ev else None), imgio.features(earlier, earlier_key))
    if m.H is None or m.inliers < T.MIN_INLIERS:
        return False, {"inliers": m.inliers}
    shift, scale = identity_distance(m.H, ew, eh)
    out = {"corner_shift": round(shift, 4), "scale": round(scale, 4), "inliers": m.inliers}
    if shift > T.REPLAY_CORNER_SHIFT or abs(scale - 1.0) > T.REPLAY_SCALE_TOL:
        return False, out
    warped, valid = _change.warp_into(ev_r, m.H, (ew, eh))
    # Clipped pixels (crushed black or blown white in either photo) carry no evidence.
    ga = cv2.cvtColor(earlier, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    valid = valid & (ga > 5) & (ga < 250) & (gb > 5) & (gb < 250)
    if not valid.any():
        return False, out
    mad = _change.normalised_mad(earlier, warped, valid)
    mask = _change.change_mask(earlier, warped, valid)
    changed = float(mask[valid].mean())
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    blob = float(stats[1:, cv2.CC_STAT_AREA].max()) / float(mask.size) if n > 1 else 0.0
    out.update(mad=round(mad, 3), changed_frac=round(changed, 4), blob=round(blob, 5))
    hit = mad <= T.REPLAY_MAD and changed <= T.REPLAY_CHANGED_FRAC and blob <= T.REPLAY_BLOB_FRAC
    return hit, out


def check_replay(
    ev: np.ndarray,
    earlier: list[tuple[str, np.ndarray, tuple | None]],
    ev_key: tuple | None = None,
) -> ReplayReport:
    """Compare against every earlier photo in the job. The first near-identical wins."""
    for name, img, key in earlier:
        hit, info = is_replay(img, ev, key, ev_key)
        if hit:
            return ReplayReport(
                replay=True,
                of=name,
                corner_shift=info.get("corner_shift"),
                scale=info.get("scale"),
                mad=info.get("mad"),
                changed_frac=info.get("changed_frac"),
                compared=len(earlier),
            )
    return ReplayReport(replay=False, compared=len(earlier))
