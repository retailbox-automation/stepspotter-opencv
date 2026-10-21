"""The OpenCV 5 perception layer, module by module, on the six real photos in the repo.

Offline and fast: real OpenCV, no network, no model. Damage is generated with the same
deterministic functions the eval set uses (``perception/synthetic.py``), so "catches a
blurred photo" here means the same thing as in eval/results/opencv.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from stepspotter.perception import change, imgio, quality, render, scene, synthetic
from stepspotter.perception import thresholds as T
from stepspotter.perception.inspect import Earlier, inspect_evidence, inspect_full

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]
IDS = sorted(SCENES)


def photo(pid: str) -> np.ndarray:
    return imgio.load(ROOT / SCENES[pid]["file"])


def zones(pid: str) -> list[tuple]:
    return [(z["label"], z["kind"], tuple(z["box"])) for z in SCENES[pid]["zones"]]


def zone_box(pid: str, kind: str) -> tuple:
    return next(tuple(z["box"]) for z in SCENES[pid]["zones"] if z["kind"] == kind)


def reshot(img: np.ndarray, seed: int = 3) -> np.ndarray:
    """A hand-held re-shot of the same place: another angle plus sensor noise."""
    return synthetic.sensor_noise(synthetic.perspective(img, 0.10, seed), 3.0, seed)


@pytest.fixture(scope="module")
def jack_patch() -> np.ndarray:
    """A foreign part to paste in: the yellow keystone from photo 04."""
    img = photo("04")
    h, w = img.shape[:2]
    return img[int(0.38 * h) : int(0.80 * h), int(0.22 * w) : int(0.80 * w)].copy()


# ----------------------------------------------------------------------------- quality


@pytest.mark.parametrize("pid", IDS)
def test_every_real_photo_passes_quality(pid):
    q = quality.assess(photo(pid))
    assert q.ok, (pid, q.issues, q.sharpness_p90)
    assert q.instruction is None


@pytest.mark.parametrize("pid", IDS)
@pytest.mark.parametrize(
    "damage,code",
    [
        (lambda im: synthetic.gaussian_blur(im, 4), "blurry"),
        (lambda im: synthetic.exposure(im, 0.12), "too_dark"),
        (lambda im: synthetic.exposure(im, 3.0, 40), "overexposed"),
        (lambda im: synthetic.resize(im, 0.3), "too_small"),
    ],
    ids=["blur", "dark", "overexposed", "small"],
)
def test_damage_is_named_and_comes_with_one_instruction(pid, damage, code):
    # judged as in a job: against the person's first photo of the place (the original)
    q = quality.assess(damage(photo(pid)), ref_bright=quality.bright_frac(photo(pid)))
    assert not q.ok
    assert q.issues[0] == code, (pid, q.issues)
    assert q.instruction and q.instruction.count(".") <= 2  # one instruction, not a lecture


def test_a_white_scene_is_not_overexposed_when_the_first_photo_is_just_as_white():
    """L2's eval: a white scene (c20) was refused as washed out in every photo of it."""
    white = synthetic.exposure(photo("02"), 2.4, 60)
    first = quality.bright_frac(white)
    assert first > T.BRIGHT_FRAC_MAX  # by the old absolute rule this scene is "washed out"
    again = synthetic.perspective(white, 0.06, 5)
    rep = inspect_evidence(again, white, zones("02"))
    assert "overexposed" not in rep.quality.issues
    against_normal = inspect_evidence(again, photo("02"), zones("02"))
    assert against_normal.decision == "retake" and against_normal.reason_code == "overexposed"


def test_without_a_first_photo_only_a_half_blown_photo_is_overexposed():
    assert "overexposed" in quality.assess(synthetic.exposure(photo("04"), 3.0, 40)).issues
    mild = synthetic.exposure(photo("02"), 2.4, 60)
    assert T.BRIGHT_FRAC_MAX < quality.bright_frac(mild) < T.BRIGHT_FRAC_ABS_MAX
    assert "overexposed" not in quality.assess(mild).issues


def test_a_blank_frame_is_not_called_blurry():
    q = quality.assess(np.full((960, 1280, 3), (90, 110, 140), np.uint8))
    assert q.issues[0] == "blank"
    assert "Point the camera" in q.instruction


def test_the_dark_photo_is_told_about_light_not_about_holding_still():
    """An unlit photo is also 'blurry' by the numbers; the advice must be the light."""
    q = quality.assess(synthetic.exposure(photo("02"), 0.12))
    assert q.issues == ["too_dark"]
    assert "light" in q.instruction.lower()


# ------------------------------------------------------------------------------- scene


@pytest.mark.parametrize("pid", IDS)
@pytest.mark.parametrize(
    "variant",
    [
        lambda im: synthetic.rotate(im, 8),
        lambda im: reshot(im),
        lambda im: synthetic.gamma(synthetic.exposure(im, 1.15, 10), 0.8),
    ],
    ids=["rot8", "reshot", "light"],
)
def test_the_same_place_matches(pid, variant):
    ref = imgio.to_work(photo(pid))
    rep, _m = scene.match_scene(ref, imgio.to_work(variant(photo(pid))))
    assert rep.status == "matched", (pid, rep.rejected_because, rep.inliers)
    assert rep.inliers >= T.MIN_INLIERS


@pytest.mark.parametrize("pid", IDS)
def test_a_close_up_of_the_work_zone_finds_its_place(pid):
    """A native-resolution close-up of the work zone (the commonest real evidence)."""
    ref = imgio.to_work(photo(pid))
    close = synthetic.crop_around(photo(pid), zone_box(pid, "act"))
    rep, _m = scene.match_scene(ref, imgio.to_work(close), zone_box(pid, "act"))
    assert rep.status == "matched", (pid, rep.rejected_because)


@pytest.mark.parametrize(
    "a,b", [("01", "04"), ("01", "06"), ("02", "04"), ("02", "06"), ("03", "05"), ("04", "06"), ("05", "06")]
)
def test_different_places_do_not_match(a, b):
    rep, _m = scene.match_scene(imgio.to_work(photo(a)), imgio.to_work(photo(b)))
    assert rep.status == "not_matched", (a, b, rep.inliers, rep.scale)
    assert rep.H is None


def test_the_real_pair_of_one_panel_matches_both_ways():
    """01 and 02 are the same panel from two distances — real, not synthetic."""
    for a, b in (("01", "02"), ("02", "01")):
        rep, _m = scene.match_scene(imgio.to_work(photo(a)), imgio.to_work(photo(b)))
        assert rep.status == "matched", (a, b, rep.rejected_because)


def test_sanity_rejects_a_mirror_and_a_sliver():
    mirror = np.array([[-1.0, 0, 1000], [0, 1, 0], [0, 0, 1]])
    assert scene.sanity(mirror, (1000, 800), (1000, 800))[0] == "the fit mirrors the image"
    sliver = np.array([[0.05, 0, 10], [0, 1.0, 0], [0, 0, 1]])
    why, _geo = scene.sanity(sliver, (1000, 800), (1000, 800))
    assert why is not None


# ------------------------------------------------------------------------------ replay


@pytest.mark.parametrize("pid", IDS)
@pytest.mark.parametrize(
    "copy",
    [
        lambda im: synthetic.jpeg(im, 60),
        lambda im: synthetic.resize(im, 0.7),
        lambda im: synthetic.rotate(im, 2),
        lambda im: synthetic.exposure(im, 1.0, 15),
    ],
    ids=["jpeg60", "resized", "rot2", "brighter"],
)
def test_a_copy_of_an_earlier_photo_is_a_replay(pid, copy):
    earlier = imgio.to_work(photo(pid))
    hit, info = scene.is_replay(earlier, imgio.to_work(copy(photo(pid))))
    assert hit, (pid, info)


@pytest.mark.parametrize("pid", IDS)
def test_a_reshot_of_the_same_place_is_not_a_replay(pid):
    hit, info = scene.is_replay(imgio.to_work(photo(pid)), imgio.to_work(reshot(photo(pid))))
    assert not hit, (pid, info)


# ------------------------------------------------------------------------------ change


@pytest.mark.parametrize("pid", IDS)
def test_change_lands_in_the_zone_that_was_edited(pid, jack_patch):
    ref = imgio.to_work(photo(pid))
    for kind, other in (("act", "avoid"), ("avoid", "act")):
        # cover=0.7: this test is about WHERE the change lands, not about the smallest
        # change that counts — that is the eval's question, at a pre-set cover.
        edited = synthetic.paste_patch(photo(pid), zone_box(pid, kind), jack_patch, cover=0.7, seed=1)
        ev = imgio.to_work(synthetic.perspective(edited, 0.05, 7))
        rep, _m = scene.match_scene(ref, ev)
        assert rep.status == "matched"
        warped, valid = change.warp_into(ev, np.array(rep.H), (ref.shape[1], ref.shape[0]))
        ch, _mask = change.measure(ref, warped, valid, zones(pid))
        assert ch.status == "measured", (pid, ch.note, ch.outside_frac)
        if kind == "act":
            assert ch.act_changed and not ch.avoid_touched, (pid, ch)
        else:
            assert ch.avoid_touched and not ch.act_changed, (pid, ch)


def test_a_reshot_from_another_angle_is_unreliable_not_a_change():
    """The real pair: parallax changes the whole frame, so no zone can be blamed."""
    ref = imgio.to_work(photo("02"))
    ev = imgio.to_work(photo("01"))
    rep, _m = scene.match_scene(ref, ev)
    warped, valid = change.warp_into(ev, np.array(rep.H), (ref.shape[1], ref.shape[0]))
    ch, _mask = change.measure(ref, warped, valid, zones("02"))
    assert ch.status == "unreliable"
    assert ch.outside_frac > T.NOISE_FLOOR_MAX


# --------------------------------------------------------------------- the whole policy


def test_a_photo_opencv_cannot_line_up_is_routed_to_two_photos_not_refused():
    """OpenCV only blocks on place when it is confident; it is not, below the bar."""
    ref, ev = photo("02"), photo("04")
    with_zones = inspect_evidence(ev, ref, zones("02"))
    assert with_zones.decision == "place_unconfirmed"
    assert not with_zones.blocks and with_zones.route == "llm_two_image"
    assert with_zones.instruction is None  # nobody is sent back for an angle
    assert "coax splitter" in with_zones.reason
    without = inspect_evidence(ev, ref, [])  # the step's place may not be in the reference
    assert without.decision == "ok" and without.route == "llm_single"
    assert without.scene.status == "not_matched" and without.change.status == "not_applicable"


@pytest.mark.parametrize("ref,ev", [("02", "03"), ("01", "03"), ("04", "05")])
def test_real_re_shots_of_the_same_place_are_never_refused(ref, ev):
    """The three real same-place pairs eval run 2 refused as wrong_place (4-8 inliers)."""
    rep = inspect_evidence(photo(ev), photo(ref), zones(ref))
    assert rep.decision == "place_unconfirmed" and rep.route == "llm_two_image", (rep.reason_code, rep.reason)
    assert not rep.blocks


@pytest.mark.parametrize("ref,ev", [("04", "06"), ("05", "06"), ("06", "04"), ("06", "05")])
def test_a_photo_of_another_room_never_passes_on_opencv_alone(ref, ev):
    rep = inspect_evidence(photo(ev), photo(ref), zones(ref))
    assert rep.decision == "place_unconfirmed" and rep.route == "llm_two_image"


def test_a_confirmed_place_takes_the_cheap_single_photo_route():
    rep = inspect_evidence(photo("01"), photo("02"), zones("02"))  # the real pair that lines up
    assert rep.scene.status == "matched" and rep.scene.inliers >= T.MIN_INLIERS
    assert rep.route == "llm_single"


def test_the_reference_counts_as_a_replay_only_when_the_step_expects_change():
    ref = photo("02")
    copy = synthetic.jpeg(ref, 70)
    assert inspect_evidence(copy, ref, zones("02"), expects_change=True).decision == "replay"
    assert inspect_evidence(copy, ref, zones("02"), expects_change=False).decision == "ok"


def test_an_earlier_evidence_photo_sent_again_is_a_replay(tmp_path):
    ref = photo("02")
    first = reshot(ref, 5)
    p = tmp_path / "evidence-01.jpg"
    cv2.imwrite(str(p), first)
    rep = inspect_evidence(
        synthetic.rotate(synthetic.resize(first, 0.8), 1.5),
        ref,
        zones("02"),
        earlier=[Earlier(name="your photo for step 1", src=p)],
    )
    assert rep.decision == "replay" and rep.replay.of == "your photo for step 1"


def test_touched_avoid_is_not_a_block_but_needs_a_person(jack_patch):
    ref = photo("02")
    ev = synthetic.perspective(synthetic.paste_patch(ref, zone_box("02", "avoid"), jack_patch, seed=2), 0.05, 1)
    rep = inspect_evidence(ev, ref, zones("02"))
    assert rep.decision == "touched_avoid"
    assert rep.needs_human and rep.blocks
    assert "telecom module" in rep.instruction


def test_no_change_blocks_only_when_the_step_said_something_must_change():
    ref = photo("05")
    ev = reshot(ref, 9)
    assert inspect_evidence(ev, ref, zones("05"), expects_change=True).decision == "no_change"
    informational = inspect_evidence(ev, ref, zones("05"), expects_change=None)
    assert informational.decision == "ok" and informational.change.act_changed is False


def test_a_change_made_by_an_earlier_step_is_not_credited_to_this_one(tmp_path, jack_patch):
    """Baseline = the last accepted evidence that lines up with the reference."""
    ref = photo("02")
    after_step_1 = synthetic.paste_patch(ref, zone_box("02", "act"), jack_patch, seed=4)
    p1 = tmp_path / "step1.jpg"
    cv2.imwrite(str(p1), after_step_1)
    first = inspect_evidence(p1, ref, zones("02"), expects_change=True)
    assert first.decision == "ok" and first.change.act_changed
    # step 2 sends a re-shot of the step-1 state: nothing new happened at the zone
    ev2 = reshot(after_step_1, 11)
    vs_ref = inspect_evidence(ev2, ref, zones("02"), expects_change=True)
    assert vs_ref.decision == "ok"  # against the reference it looks changed...
    vs_step1 = inspect_evidence(
        ev2,
        ref,
        zones("02"),
        expects_change=True,
        earlier=[Earlier(name="your photo for step 1", src=p1, H_to_ref=first.scene.H, accepted=True)],
    )
    assert vs_step1.decision == "no_change"  # ...but not against what step 1 left behind
    assert vs_step1.change.baseline == "your photo for step 1"


def test_a_close_up_is_not_called_blurry_for_being_magnified():
    """Eval run 1 refused this as 'blurry next to the first photo': a close-up has less
    texture per pixel than the overview it was taken from. It is not blur."""
    ref = photo("02")
    close = synthetic.crop_around(ref, zone_box("02", "act"), 0.55)
    rep = inspect_evidence(close, ref, zones("02"))
    assert rep.decision == "ok", (rep.reason_code, rep.reason)
    assert rep.scene.coverage < T.REL_SHARP_MIN_COVERAGE and rep.quality.sharpness_ratio is None


def test_a_zone_cut_off_by_the_frame_asks_the_person_to_step_back():
    ref = photo("02")
    ev = synthetic.cut_zone(ref, zone_box("02", "act"), keep_frac=0.25)
    rep = inspect_evidence(ev, ref, zones("02"))
    assert rep.decision == "retake" and rep.reason_code == "zone_out_of_frame"
    assert rep.instruction.startswith("Step back")


@pytest.mark.parametrize("pid", IDS)
def test_glare_on_its_own_is_a_note_not_a_refusal(pid):
    """L2's eval: a frame-wide glare rule refused white basins and white walls."""
    q = quality.assess(synthetic.glare(photo(pid), 0.10, 0.5, 0.45))
    assert q.ok and q.issues == [] and q.notes == ["glare"]


def test_new_glare_on_the_work_zone_is_a_retake_that_names_the_zone():
    ref = photo("02")
    x0, y0, x1, y1 = zone_box("02", "act")
    rep = inspect_evidence(synthetic.glare(ref, 0.10, (x0 + x1) / 2, (y0 + y1) / 2), ref, zones("02"))
    assert rep.decision == "retake" and rep.reason_code == "glare_on_zone"
    assert rep.quality.glare_zone_frac >= T.GLARE_ZONE_NEW_FRAC
    assert "coax splitter" in rep.instruction


def test_glare_away_from_the_work_zone_is_said_but_does_not_block():
    ref = photo("02")
    rep = inspect_evidence(synthetic.glare(ref, 0.10, 0.25, 0.85), ref, zones("02"))
    assert rep.decision == "ok", (rep.reason_code, rep.reason)
    assert rep.advisories and "not a reason to retake" in rep.advisories[0]
    assert "Note:" in rep.reason


def test_a_white_object_in_both_photos_is_not_glare():
    """A basin that is white in the first photo is not a reflection in the second."""
    x0, y0, x1, y1 = zone_box("02", "act")
    ref = photo("02").copy()
    h, w = ref.shape[:2]
    ref[int((y0 + 0.02) * h) : int((y1 - 0.02) * h), int((x0 + 0.03) * w) : int((x1 - 0.03) * w)] = 255
    ev = synthetic.perspective(ref, 0.05, 3)
    rep = inspect_evidence(ev, ref, zones("02"))
    assert rep.decision == "ok", (rep.reason_code, rep.reason)
    assert rep.quality.glare_zone_frac < T.GLARE_ZONE_NEW_FRAC


def test_a_shaken_photo_that_only_weakly_lines_up_is_still_called_blurry():
    """Blur removes matches: the fit falls under the confirm bar but stays sane, and the
    relative-sharpness check still runs (the sink-video frame v0180 in L2's set)."""
    ref = photo("03")
    rep = inspect_evidence(synthetic.motion_blur(ref, 61, 0), ref, zones("03"))
    assert rep.scene.status == "not_matched" and rep.scene.inliers >= T.WEAK_FIT_INLIERS
    assert rep.quality.sharpness_p90 >= T.SHARP_P90_MIN  # the absolute floor alone lets it through
    assert rep.decision == "retake" and rep.reason_code == "blurry_vs_reference"


def test_a_slightly_softer_photo_of_the_same_view_is_not_refused():
    """A ratio of 0.30 was refused at the old bar of 0.35 (L2's real pair c36->c37: 0.255)."""
    ref = photo("01")
    rep = inspect_evidence(synthetic.rotate(synthetic.gaussian_blur(ref, 0.8), 3), ref, zones("01"))
    assert rep.decision == "ok"
    assert T.SHARP_RATIO_MIN < rep.quality.sharpness_ratio < 0.35


def test_an_unreadable_file_is_skipped_not_refused(tmp_path):
    bad = tmp_path / "not-a-photo.jpg"
    bad.write_bytes(b"definitely not a jpeg")
    rep = inspect_evidence(bad, photo("02"), zones("02"))
    assert rep.decision == "skipped" and not rep.blocks
    missing = inspect_evidence(tmp_path / "nope.jpg")
    assert missing.decision == "skipped"


def test_every_report_carries_its_numbers_its_thresholds_and_its_time():
    rep = inspect_evidence(synthetic.rotate(photo("01"), 5), photo("01"), zones("01"))
    assert rep.decision == "ok"
    assert rep.opencv.startswith("5.")
    assert rep.thresholds["MIN_INLIERS"] == T.MIN_INLIERS
    assert {"load", "quality", "scene", "replay", "change", "total"} <= set(rep.timings_ms)
    assert rep.ms_total > 0
    assert rep.quality.sharpness_p90 > T.SHARP_P90_MIN
    assert rep.scene.inliers >= T.MIN_INLIERS
    # the report survives a JSON round trip (it is stored on the job)
    from stepspotter.perception.models import PerceptionReport

    assert PerceptionReport.model_validate_json(rep.model_dump_json()).decision == "ok"


# ------------------------------------------------------------------------------ render


def test_render_writes_the_three_pictures_for_a_matched_photo(tmp_path, jack_patch):
    ref = photo("02")
    ev = synthetic.perspective(synthetic.paste_patch(ref, zone_box("02", "avoid"), jack_patch, seed=2), 0.05, 1)
    rep, detail = inspect_full(ev, ref, zones("02"))
    out = render.render_all(rep, detail, tmp_path, "case")
    assert set(out) == {"match", "heatmap", "quality"}
    for p in out.values():
        img = cv2.imread(p)
        assert img is not None and img.shape[0] > 100 and img.shape[1] > 300


def test_render_of_a_retake_is_only_the_quality_strip(tmp_path):
    rep, detail = inspect_full(synthetic.gaussian_blur(photo("02"), 4), photo("02"), zones("02"))
    out = render.render_all(rep, detail, tmp_path, "blur")
    assert set(out) == {"quality"}


# ------------------------------------------------------------------------------- video


def _write_video(path: Path, frames: list[np.ndarray]) -> bool:
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (w, h))
    if not vw.isOpened():
        return False
    for f in frames:
        vw.write(f)
    vw.release()
    return path.is_file() and path.stat().st_size > 0


def test_the_sharp_frame_is_picked_out_of_a_shaky_video(tmp_path):
    from stepspotter.perception import frames

    ref = imgio.to_work(photo("02"))
    small = synthetic.resize(photo("02"), 0.5)
    shaky = [synthetic.motion_blur(small, 25, a) for a in (0, 30, 60, 90, 120, 150)]
    seq = shaky[:3] + [small] + shaky[3:]
    video = tmp_path / "work.avi"
    if not _write_video(video, seq):
        pytest.skip("this OpenCV build cannot write MJPG video")
    picked = frames.pick_keyframes(video, reference=ref, k=2)
    assert picked, "no frames came back"
    best, _frame = picked[0]
    assert best.index == 3, [(k.index, k.score) for k, _f in picked]
    assert best.inliers and best.inliers >= T.MIN_INLIERS


def test_an_unreadable_video_says_so(tmp_path):
    from stepspotter.perception import frames

    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(frames.VideoUnreadable):
        frames.pick_keyframes(bad)


# ----------------------------------------------------------------------------- privacy


def test_without_the_detector_faces_are_reported_unchecked(monkeypatch, tmp_path):
    from stepspotter.perception import privacy

    monkeypatch.setenv(privacy.MODELS_ENV, str(tmp_path / "no-models"))
    img = photo("06")
    out, rep = privacy.blur_faces(img)
    assert rep.faces_checked is False and rep.faces_blurred == 0
    assert "not installed" in rep.note
    assert out is img  # nothing was touched


def test_a_broken_detector_file_is_not_a_face_check(monkeypatch, tmp_path):
    from stepspotter.perception import privacy

    (tmp_path / T.YUNET_FILE).write_bytes(b"not an onnx model")
    monkeypatch.setenv(privacy.MODELS_ENV, str(tmp_path))
    _out, rep = privacy.blur_faces(photo("06"))
    assert rep.faces_checked is False


# --------------------------------------------------------------------------- synthetic


def test_the_generators_are_deterministic():
    a = synthetic.perspective(synthetic.sensor_noise(photo("03"), 4, 1), 0.1, 2)
    b = synthetic.perspective(synthetic.sensor_noise(photo("03"), 4, 1), 0.1, 2)
    assert np.array_equal(a, b)


@pytest.mark.skipif(
    __import__("stepspotter.perception.privacy", fromlist=["model_path"]).model_path() is None,
    reason="YuNet is not installed (tools/fetch_models.sh); faces are reported unchecked instead",
)
@pytest.mark.parametrize("pid", IDS)
def test_with_the_detector_installed_the_six_photos_have_no_faces_to_blur(pid):
    """Runs only where the model file is present. None of the six photos shows a face
    (two show a hand), so the detector must find none and leave the pixels alone. A
    positive test needs a photo of a face we have the right to use; the repo has none."""
    from stepspotter.perception import privacy

    out, rep = privacy.blur_faces(photo(pid))
    assert rep.faces_checked is True and rep.faces_blurred == 0, (pid, rep)
    assert np.array_equal(out, photo(pid))
