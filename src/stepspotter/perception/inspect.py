"""``inspect_evidence`` — the first, deterministic layer of the photo-evidence gate.

One call per evidence photo, before any model sees it. It returns a
``PerceptionReport`` whose ``decision`` changes what happens next:

    ok             the photo goes on to the model check, as before
    retake         blocked; the person gets ONE concrete instruction (light, hold still,
                   step back so X is in frame, move the glare)
    place_unconfirmed  NOT a block: OpenCV could not confirm it is the place the step's
                   zones were drawn on, so the model gets both photos and must answer
                   same_place (route llm_two_image); the gate requires same_place=true
    replay         blocked; it is a photo this job already has
    no_change      blocked; the step had to change something and nothing changed there
    touched_avoid  not a block: the gate stops the run for a person (human approval)
    skipped        OpenCV could not read the file; nothing decided here, the model judges

POLICY — the decisions below are the product, so they are written down here, in the
order the code applies them. The first rule that fires decides.

1. **Unreadable evidence** -> ``skipped``. The layer does not get to refuse a photo it
   could not open; the model path raises its own error for a missing file.
2. **Quality on the evidence alone** (size, dark, washed out, blank, blur, glare)
   -> ``retake`` with the instruction for the first failure.
3. **Reference for step k is the photo the step's card was drawn on**, because that is
   where ``state.box_sets[k]`` (the zones) live. Match the evidence to it (whole frame,
   then a crop around the work zone for close-ups).
   - matched: the evidence must not be far blurrier than the reference
     (``blurry_vs_reference``), the work zone must be in frame
     (``zone_out_of_frame``) and not under NEW glare (``glare_on_zone``: at least
     GLARE_ZONE_NEW_FRAC of the zone saturated here but not in the reference) -> else
     ``retake``. Glare anywhere else, or where the photo cannot be lined up, is an
     advisory note: the decision stays as it is.
   - a weak fit (sane homography, fewer inliers than the confirm bar) still gets the
     relative-sharpness check — blur is what removes the matches.
   - not matched AND the step's zones were located on the reference ->
     ``place_unconfirmed``, NOT a block. The step said "work here, on this photo", and
     OpenCV cannot line this photo up with it — but a real re-shot from another angle or
     after the cables moved fails to line up exactly as often as a photo of another room
     does (eval run 2: 4-8 inliers either way), so OpenCV is not confident enough to
     refuse. The photo goes to the model with BOTH photos and a ``same_place`` field it
     must fill; the gate then requires ``same_place=true``. OpenCV only blocks on place
     through ``replay``. (Until 21.10 this was a ``wrong_place`` block, and it refused 3
     of 5 real same-place pairs.)
     Active perception — asking once for a photo "from about where you took the first
     one" — is offered only to the agent, by ``inspect_photo`` before it submits; the
     submit path never asks, so a person who did the step is never sent back for an
     angle alone.
   - not matched AND no zones were located for this step -> scene ``not_applicable``,
     recorded as such: the place the step is about may simply not be in the reference.
4. **Replay**: near-identical (homography ~ identity AND aligned difference ~ 0) to ANY
   photo already submitted in this job -> ``replay``. The reference is included only
   when the step expects a change: for a "confirm" step the reference may legitimately
   already show what is asked, and sending it again is not cheating. Not a byte hash: a
   re-encoded, resized or slightly rotated copy is still caught.
5. **Change** (needs a scene match and zones). Baseline = the last accepted evidence of
   an earlier step that matched this reference, else the reference itself — so step 3
   is not credited with what step 2 changed. A zone counts only against the noise floor
   measured outside all zones (see ``change.py``); an unreliable map decides nothing.
   - avoid zone changed AND (work zone unchanged OR the avoid change is large)
     -> ``touched_avoid``: the gate raises ``interrupt("human_review")``, a request for
     human approval — never a plain cancel, because a cancel lets the chat carry on.
     This applies whatever ``expects_change`` says: a do-not-touch zone is never
     supposed to change.
   - ``expects_change`` is True AND the work zone did not change -> ``no_change``.
   - ``expects_change`` is None (plans written before the field existed, test fakes)
     -> the work-zone result is informational and never blocks.
     ``expects_change`` False (confirm / inspect steps) -> the work zone is not judged.
6. Otherwise ``ok``.

STUCK RULE (``apply_stuck_rule``): after ``STUCK_AFTER`` consecutive OpenCV blocks on the
same step, a further ``retake`` / ``no_change`` is NOT allowed to block
on its own: the photo goes to the model check with OpenCV's findings attached, and the
report is marked ``overridden``. Chosen over interrupting for a human because the person
in front of the panel gets a second, independent look at once instead of waiting for
someone who may not be there; the model's verdict still gates, hazards still stop the
run, and the override is on the trace. ``replay`` is excluded (a new photo always clears
it) and so is ``touched_avoid`` (it already goes to a person). A false positive in this
layer must never trap a person forever.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import cv2
import numpy as np

from stepspotter.perception import change as _change
from stepspotter.perception import imgio, privacy, quality, scene
from stepspotter.perception import thresholds as T
from stepspotter.perception.models import (
    OVERRIDABLE,
    ChangeReport,
    PerceptionReport,
    PrivacyReport,
    QualityReport,
    ReplayReport,
    SceneMatch,
)

Zone = _change.Zone

#: Consecutive OpenCV blocks on one step before the stuck rule lets the model look.
STUCK_AFTER = 3

#: The thresholds a report carries: the ones its decisions can depend on.
_REPORTED = (
    "WORK_PX", "DARK_MEAN", "DARK_FRAC_MAX", "BRIGHT_FRAC_MAX", "BLANK_STD", "SHARP_P90_MIN",
    "SHARP_RATIO_MIN", "WEAK_FIT_INLIERS", "GLARE_BLOB_FRAC", "GLARE_ZONE_NEW_FRAC", "MIN_INLIERS", "MIN_INLIER_RATIO",
    "SCALE_MIN", "SCALE_MAX", "MIN_OVERLAP", "REPLAY_CORNER_SHIFT", "REPLAY_MAD",
    "REPLAY_CHANGED_FRAC", "CHANGE_DELTA", "ACT_CHANGED_MIN", "AVOID_CHANGED_MIN",
    "NOISE_FLOOR_MAX", "AVOID_LARGE", "ZONE_VISIBLE_MIN",
)


@dataclass
class Earlier:
    """A photo this job has already seen.

    ``H_to_ref`` is that photo's own homography to the reference (working px), when it
    matched; ``accepted`` says it passed its step — only then can it be a baseline.
    """

    name: str
    src: imgio.ImageLike
    H_to_ref: list[list[float]] | None = None
    accepted: bool = False


@dataclass
class Detail:
    """What the render needs and the report does not carry: images, masks, the match."""

    evidence: np.ndarray | None = None  # working size, faces blurred
    reference: np.ndarray | None = None  # working size
    match: scene.Match | None = None
    warped: np.ndarray | None = None
    valid: np.ndarray | None = None
    change_mask: np.ndarray | None = None
    baseline: np.ndarray | None = None
    zones: list[Zone] = field(default_factory=list)
    evidence_full: np.ndarray | None = None  # original size, faces blurred


def as_zones(boxes: Iterable[Any]) -> list[Zone]:
    """Accept ``models.Box`` objects (duck-typed) or (label, kind, (x0,y0,x1,y1)) tuples."""
    out: list[Zone] = []
    for b in boxes or []:
        if isinstance(b, tuple) and len(b) == 3:
            label, kind, box = b
        else:
            label, kind = getattr(b, "label", "zone"), getattr(b, "kind", "act")
            x0, x1 = sorted((float(b.x0), float(b.x1)))
            y0, y1 = sorted((float(b.y0), float(b.y1)))
            box = (x0, y0, x1, y1)
        out.append((str(label), str(kind), tuple(float(v) for v in box)))  # type: ignore[arg-type]
    return out


def _work_zone(zones: list[Zone]) -> Zone | None:
    return next((z for z in zones if z[1] == "act"), None)


def _report(decision: str, code: str, reason: str, instruction: str | None, **kw: Any) -> PerceptionReport:
    return PerceptionReport(
        decision=decision,  # type: ignore[arg-type]
        reason_code=code,
        reason=reason,
        instruction=instruction,
        thresholds={k: getattr(T, k) for k in _REPORTED},
        opencv=cv2.__version__,
        **kw,
    )


def _zone_new_glare(
    ev_w: np.ndarray, ref_w: np.ndarray, H: np.ndarray, ref_size: tuple[int, int], zone: Zone
) -> float:
    """Share of the work zone saturated in the evidence but NOT at the same place in the
    reference. A white object is white in both photos; a reflection is new."""
    warped_glare, valid = _change.warp_into(quality.glare_mask(ev_w)[..., None].repeat(3, axis=2), H, ref_size)
    k = np.ones((T.GLARE_REF_DILATE_PX, T.GLARE_REF_DILATE_PX), np.uint8)
    ref_sat = cv2.dilate(quality.glare_mask(ref_w), k) > 0
    zm = _change.zone_mask((ref_size[1], ref_size[0]), zone[2]) & valid
    if not zm.any():
        return 0.0
    return float(((warped_glare[..., 0] > 0) & ~ref_sat)[zm].mean())


def _weak_fit_coverage(raw: "scene.Match | None", ev_w: np.ndarray, ref_w: np.ndarray) -> float | None:
    """Coverage of a sane whole-frame fit with too few inliers to confirm the place."""
    if raw is None or raw.H is None or raw.inliers < T.WEAK_FIT_INLIERS:
        return None
    if raw.inliers / max(raw.good, 1) < T.MIN_INLIER_RATIO:
        return None
    why, geo = scene.sanity(raw.H, (ev_w.shape[1], ev_w.shape[0]), (ref_w.shape[1], ref_w.shape[0]))
    return geo.get("coverage") if why is None else None


def inspect_full(
    evidence: imgio.ImageLike,
    reference: imgio.ImageLike | None = None,
    zones: Iterable[Any] = (),
    *,
    expects_change: bool | None = None,
    earlier: Sequence[Earlier] = (),
    step_id: int | None = None,
    blur_faces: bool = True,
    avoid_approved: bool = False,
) -> tuple[PerceptionReport, Detail]:
    """Run the whole policy (see the module docstring). Returns (report, render detail).

    ``avoid_approved``: a person has already looked at a change in this step's
    do-not-touch zone and said to go on, so that change is reported but no longer stops
    the run (it would otherwise stop it again on every photo).
    """
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    detail = Detail(zones=as_zones(zones))
    zs = detail.zones
    work = _work_zone(zs)
    work_label = work[0] if work else None
    common: dict[str, Any] = {"step_id": step_id, "expects_change": expects_change, "timings_ms": timings}

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round((now - since) * 1000, 2)
        return now

    def done(rep: PerceptionReport) -> tuple[PerceptionReport, Detail]:
        timings["total"] = round((time.perf_counter() - t0) * 1000, 2)
        rep.timings_ms = dict(timings)  # pydantic copied the dict when the report was built
        return rep, detail

    # 1. read --------------------------------------------------------------------
    t = time.perf_counter()
    try:
        ev_full = imgio.load(evidence)
    except imgio.Unreadable as exc:
        lap("load", t)
        return done(_report("skipped", "evidence_unreadable", f"OpenCV could not read the photo: {exc}.", None, **common))
    ev_key = imgio.file_key(evidence, "ev")
    priv = PrivacyReport()
    if blur_faces:
        ev_full, priv = privacy.blur_faces(ev_full)
        if priv.faces_blurred:
            ev_key = None  # the pixels changed; a cached description would be of the old ones
    detail.evidence_full = ev_full
    ev_w = imgio.to_work(ev_full)
    detail.evidence = ev_w
    common["privacy"] = priv
    t = lap("load", t)

    # 2. quality on its own ------------------------------------------------------
    q: QualityReport = quality.assess(ev_full, work_label)
    t = lap("quality", t)
    common["quality"] = q
    if not q.ok:
        code = q.issues[0]
        return done(_report("retake", code, _quality_reason(code, q), q.instruction, **common))

    # 3. scene -------------------------------------------------------------------
    ref_w = ref_full = None
    match_rep: SceneMatch
    if reference is not None:
        try:
            ref_full = imgio.load(reference)
            ref_w = imgio.to_work(ref_full)
        except imgio.Unreadable:
            ref_w = ref_full = None
    if ref_w is None:
        match_rep = SceneMatch(status="no_reference")
    else:
        detail.reference = ref_w
        match_rep, raw = scene.match_scene(
            ref_w, ev_w, work[2] if work else None, imgio.file_key(reference, "ref"), ev_key
        )
        detail.match = raw
    t = lap("scene", t)
    common["scene"] = match_rep
    H = np.array(match_rep.H) if match_rep.H is not None else None
    ref_size = (ref_w.shape[1], ref_w.shape[0]) if ref_w is not None else None

    advisories: list[str] = []
    common["advisories"] = advisories
    if match_rep.status == "not_matched" and ref_w is not None:
        # A weak fit: blur removes matches, so a blurred photo of the same view can fall
        # under the confirm bar. If the fit is sane and covers the same view, the
        # relative-sharpness check still applies (WEAK_FIT_INLIERS).
        cov = _weak_fit_coverage(detail.match, ev_w, ref_w)
        if cov is not None:
            rel = quality.relative_issue(q, quality.sharpness_p90(ref_full), cov)
            if rel:
                return done(_report("retake", rel, _quality_reason(rel, q), quality.instruction_for(rel, work_label), **common))
    if match_rep.status == "matched" and H is not None and ref_w is not None:
        # Both sharpness numbers are read off the full-size images by the same rule, and
        # only for the same view (see quality.relative_issue).
        rel = quality.relative_issue(q, quality.sharpness_p90(ref_full), match_rep.coverage)
        if rel:
            return done(_report("retake", rel, _quality_reason(rel, q), quality.instruction_for(rel, work_label), **common))
        if work is not None:
            _w, valid = _change.warp_into(ev_w, H, ref_size)  # type: ignore[arg-type]
            zm = _change.zone_mask((ref_size[1], ref_size[0]), work[2])  # type: ignore[index]
            visible = float((zm & valid).sum()) / max(float(zm.sum()), 1.0)
            if visible < T.ZONE_VISIBLE_MIN:
                return done(_report(
                    "retake", "zone_out_of_frame",
                    f"Only {visible:.0%} of the {work_label} is inside this photo (needs {T.ZONE_VISIBLE_MIN:.0%}).",
                    f"Step back so the whole {work_label} is in the photo, then take it again.",
                    **common,
                ))
            gz = _zone_new_glare(ev_w, ref_w, H, ref_size, work)  # type: ignore[arg-type]
            q.glare_zone_frac = round(gz, 4)
            if gz >= T.GLARE_ZONE_NEW_FRAC:
                return done(_report(
                    "retake", "glare_on_zone",
                    f"A bright reflection covers {gz:.0%} of the {work_label} (it is not there in your first photo).",
                    quality.instruction_for("glare_on_zone", f"the {work_label}"),
                    **common,
                ))
            if "glare" in q.notes or gz > 0.01:
                advisories.append(
                    f"A bright patch is in the photo ({q.glare_blob_frac:.1%} of it; {gz:.0%} of the "
                    f"{work_label} newly bright). It does not cover the work, so it is not a reason to retake."
                )
    if "glare" in q.notes and not advisories:
        advisories.append(
            f"A bright patch covers {q.glare_blob_frac:.1%} of the photo. It could not be placed on the "
            "work zone, so it is noted, not a reason to retake."
        )
    place_unconfirmed = match_rep.status == "not_matched" and bool(zs)
    t = time.perf_counter()

    # 4. replay ------------------------------------------------------------------
    pool: list[tuple[str, np.ndarray, tuple | None]] = []
    for e in earlier:
        try:
            pool.append((e.name, imgio.to_work(imgio.load(e.src)), imgio.file_key(e.src, "ev")))
        except imgio.Unreadable:
            continue
    if expects_change and ref_w is not None:
        pool.append(("your first photo", ref_w, imgio.file_key(reference, "ref")))
    rp: ReplayReport = scene.check_replay(ev_w, pool, ev_key)
    common["replay"] = rp
    t = lap("replay", t)
    if rp.replay:
        return done(_report(
            "replay", "replay",
            f"This is the same photo as {rp.of} (aligned difference {rp.mad}, corner shift {rp.corner_shift}).",
            "Take a new photo after doing the step — an earlier photo cannot prove it.",
            **common,
        ))

    if place_unconfirmed:
        where = f"the {work_label}" if work_label else "the place this step is about"
        return done(_report(
            "place_unconfirmed", "place_unconfirmed",
            f"OpenCV could not line this photo up with your first photo "
            f"({match_rep.rejected_because}), so it cannot confirm it shows {where}. "
            "The model checks it against your first photo instead.",
            None,
            **common,
        ))

    # 5. change ------------------------------------------------------------------
    ch = ChangeReport(status="not_applicable", note="no scene match" if H is None else "no zones")
    if H is not None and ref_w is not None and zs:
        warped, valid = _change.warp_into(ev_w, H, ref_size)  # type: ignore[arg-type]
        base, base_name, valid_b = ref_w, "reference", valid
        for e in reversed(list(earlier)):
            if not (e.accepted and e.H_to_ref is not None):
                continue
            try:
                bimg = imgio.to_work(imgio.load(e.src))
            except imgio.Unreadable:
                continue
            bw, bvalid = _change.warp_into(bimg, np.array(e.H_to_ref), ref_size)  # type: ignore[arg-type]
            if bvalid.mean() > 0.3:
                base, base_name, valid_b = bw, e.name, valid & bvalid
                break
        ch, mask = _change.measure(base, warped, valid_b, zs, base_name)
        detail.warped, detail.valid, detail.change_mask, detail.baseline = warped, valid_b, mask, base
    t = lap("change", t)
    common["change"] = ch

    if ch.status == "measured":
        avoid_big = any(r.changed_frac >= T.AVOID_LARGE for r in ch.avoid)
        if ch.avoid_touched and (not ch.act_changed or avoid_big) and not avoid_approved:
            worst = max(ch.avoid, key=lambda r: r.changed_frac)
            return done(_report(
                "touched_avoid", "change_in_avoid",
                f"{worst.changed_frac:.0%} of the {worst.label} changed since {_said(ch.baseline)}"
                f" (background {ch.outside_frac:.0%}), and this step said not to touch it.",
                f"Stop. Something changed at the {worst.label}, which this step said to leave alone. "
                "A person needs to check it before you carry on.",
                **common,
            ))
        if expects_change is True and ch.act_changed is False:
            best = max(ch.act, key=lambda r: r.changed_frac)
            return done(_report(
                "no_change", "no_change_in_zone",
                f"Only {best.changed_frac:.0%} of the {best.label} changed since {_said(ch.baseline)}"
                f" (needs {max(T.ACT_CHANGED_MIN, T.NOISE_MULT * (ch.outside_frac or 0) + T.NOISE_ADD):.0%}).",
                f"I cannot see any change at the {best.label} yet. Do the step first, then take the photo "
                "from about the same spot.",
                **common,
            ))

    reason = _ok_reason(match_rep, ch, rp)
    if advisories:
        reason = f"{reason} Note: {' '.join(advisories)}"
    return done(_report("ok", "ok", reason, None, **common))


def inspect_evidence(
    evidence: imgio.ImageLike,
    reference: imgio.ImageLike | None = None,
    zones: Iterable[Any] = (),
    *,
    expects_change: bool | None = None,
    earlier: Sequence[Earlier] = (),
    step_id: int | None = None,
    blur_faces: bool = True,
    avoid_approved: bool = False,
) -> PerceptionReport:
    """The report only. See the module docstring for the policy it applies."""
    rep, _detail = inspect_full(
        evidence,
        reference,
        zones,
        expects_change=expects_change,
        earlier=earlier,
        step_id=step_id,
        blur_faces=blur_faces,
        avoid_approved=avoid_approved,
    )
    return rep


def apply_stuck_rule(report: PerceptionReport, consecutive_blocks: int) -> PerceptionReport:
    """Let a stuck person past an OpenCV block (see STUCK RULE in the module docstring).

    ``consecutive_blocks`` is how many photos in a row OpenCV has already blocked on
    this step. Returns the same report, marked ``overridden`` when the rule applies.
    """
    if (
        consecutive_blocks >= STUCK_AFTER
        and report.decision in OVERRIDABLE
        and not report.overridden
    ):
        report.overridden = True
        report.reason = (
            f"{report.reason} OpenCV has blocked {consecutive_blocks} photos in a row on this "
            "step, so this one goes to the model check with these findings attached instead "
            "of being refused again."
        )
    return report


def findings_for_model(report: PerceptionReport) -> str:
    """OpenCV's findings, as context text for the model. Context, not a verdict."""
    lines = [f"Deterministic checks (OpenCV {report.opencv}) on this photo — context, not a verdict:"]
    q = report.quality
    if q is not None:
        lines.append(
            f"- quality: sharpness p90 {q.sharpness_p90}, mean brightness {q.mean}, "
            f"glare blob {q.glare_blob_frac:.3f}; issues: {', '.join(q.issues) or 'none'}"
        )
    s = report.scene
    if s is not None:
        if s.status == "matched":
            lines.append(f"- it lines up with the person's first photo ({s.inliers} matched points, {s.method}).")
        elif s.status == "not_matched":
            lines.append(
                f"- OpenCV could not line it up with the person's first photo ({s.rejected_because}); "
                "that alone does not mean it is another place."
            )
    c = report.change
    if c is not None and c.status != "not_applicable":
        parts = [f"{z.label}: {z.changed_frac:.0%} changed" for z in c.act + c.avoid]
        lines.append(f"- change since {c.baseline} ({c.status}): " + "; ".join(parts))
    if report.overridden:
        lines.append(
            f"- OpenCV would have refused this photo ({report.decision}: {report.reason_code}) but it "
            "has refused several in a row, so you decide. Be strict."
        )
    return "\n".join(lines)


def _said(baseline: str) -> str:
    """The change baseline as a person says it."""
    return "your first photo" if baseline == "reference" else baseline


def _quality_reason(code: str, q: QualityReport) -> str:
    if code == "too_small":
        return f"The photo is {max(q.width, q.height)} px on its long side (needs {T.MIN_LONG_SIDE})."
    if code == "too_dark":
        return f"Too dark: mean brightness {q.mean:.0f} (needs {T.DARK_MEAN:.0f}), {q.dark_frac:.0%} near-black."
    if code == "overexposed":
        return f"Washed out: {q.bright_frac:.0%} of the photo is near-white (max {T.BRIGHT_FRAC_MAX:.0%})."
    if code == "blank":
        return f"Nothing in the frame: contrast {q.std:.1f} (needs {T.BLANK_STD:.0f})."
    if code == "blurry":
        return f"Blurry: sharpness {q.sharpness_p90:.0f} (needs {T.SHARP_P90_MIN:.0f})."
    if code == "blurry_vs_reference":
        return (
            f"Blurry next to the first photo: {q.sharpness_ratio or 0:.0%} of its sharpness "
            f"(needs {T.SHARP_RATIO_MIN:.0%})."
        )
    if code == "glare":
        return (
            f"Glare: one saturated patch covers {q.glare_blob_frac:.1%} of the photo "
            f"(max {T.GLARE_BLOB_FRAC:.1%})."
        )
    return code


def _ok_reason(s: SceneMatch, c: ChangeReport, r: ReplayReport) -> str:
    bits = ["Sharp, lit and in frame."]
    if s.status == "matched":
        bits.append(f"Same place as the first photo ({s.inliers} matched points).")
    elif s.status == "not_matched":
        bits.append("Not lined up with the first photo, but no zone was drawn there for this step.")
    if c.status == "measured":
        act = ", ".join(f"{z.label} {z.changed_frac:.0%}" for z in c.act)
        if act:
            bits.append(f"Changed: {act}.")
    elif c.status == "unreliable":
        bits.append("The change map is too noisy to read (another angle or light).")
    if r.compared:
        bits.append(f"Not a repeat of {r.compared} earlier photo(s).")
    return " ".join(bits)


def zone_crop_jpeg(rep: PerceptionReport, detail: Detail, max_px: int = 512) -> bytes | None:
    """This photo, warped onto the reference and cropped around the work zone, as JPEG.

    Only when the scene matched and a work zone exists — otherwise there is nothing
    lined up to crop. Handed to the model as labelled context, never as the evidence.
    """
    if detail.warped is None or detail.valid is None or rep.scene is None or rep.scene.status != "matched":
        return None
    work = _work_zone(detail.zones)
    if work is None:
        return None
    h, w = detail.warped.shape[:2]
    x0, y0, x1, y1 = work[2]
    pad_x, pad_y = 0.25 * (x1 - x0), 0.25 * (y1 - y0)
    X0, Y0 = int(max(0.0, x0 - pad_x) * w), int(max(0.0, y0 - pad_y) * h)
    X1, Y1 = int(min(1.0, x1 + pad_x) * w), int(min(1.0, y1 + pad_y) * h)
    if X1 - X0 < 16 or Y1 - Y0 < 16:
        return None
    crop = detail.warped[Y0:Y1, X0:X1]
    s = min(1.0, max_px / max(crop.shape[:2]))
    if s < 1.0:
        crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None
