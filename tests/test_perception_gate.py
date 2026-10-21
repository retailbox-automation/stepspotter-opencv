"""OpenCV output changes what happens next — through the real tools and a real HookRegistry.

These are the competition-evidence tests: each one shows an OpenCV 5 result changing a
later decision, tool call or action — a photo blocked before any model call, a retake
with one instruction, a stop for a person's approval — and the model NOT being called
when OpenCV already refused. Real photos, real OpenCV, real Strands hook dispatch; only
the model's verdict is faked (and in the blocking cases it must never be reached).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import pytest

from stepspotter import store
from stepspotter.gate import StepGate
from stepspotter.guide import JobService, _InterruptCarrier, build_tools, run_tool_through_gate
from stepspotter.models import Box, Plan, Step, StepVerdict
from stepspotter.perception import imgio, synthetic
from stepspotter.perception.inspect import STUCK_AFTER

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]


@pytest.fixture(autouse=True)
def perception_on(monkeypatch):
    """conftest turns the layer off for the legacy suite; this file is about it."""
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "1")


def photo(pid: str):
    return imgio.load(ROOT / SCENES[pid]["file"])


def boxes(pid: str) -> list[Box]:
    return [
        Box(label=z["label"], kind=z["kind"], x0=z["box"][0], y0=z["box"][1], x1=z["box"][2], y1=z["box"][3])
        for z in SCENES[pid]["zones"]
    ]


def zone(pid: str, kind: str) -> tuple:
    return next(tuple(z["box"]) for z in SCENES[pid]["zones"] if z["kind"] == kind)


class Model:
    """The verifier's stand-in. Records every call; the blocking tests assert it is empty."""

    def __init__(self, passed: bool = True) -> None:
        self.calls: list[dict] = []
        self.passed = passed

    def __call__(self, step: Step, photo_path: str, model_id=None, context=None, zone_crop=None) -> StepVerdict:
        self.calls.append({"photo": photo_path, "context": context, "zone_crop": zone_crop})
        return StepVerdict(step_id=step.id, passed=self.passed, reason="the model looked and agrees")


def plan() -> Plan:
    return Plan(
        job_title="Fit the splitter",
        safety_class="diy_ok",
        steps=[
            Step(id=1, title="Fit the new part", action="Fit it on the splitter.",
                 do_not_touch=["the telecom module"], evidence_required="the new part on the splitter",
                 highlight_targets=["coax splitter", "telecom module"], expects_change=True),
            Step(id=2, title="Check it", action="Look at it.", evidence_required="the panel",
                 expects_change=False),
        ],
    )


@pytest.fixture
def job(tmp_path):
    start = tmp_path / "start.jpg"
    shutil.copy(ROOT / SCENES["02"]["file"], start)
    model = Model()
    service = JobService(
        plan_fn=lambda task, photo, model_id=None: plan(),
        verify_fn=model,
        locate_fn=lambda step, photo, model_id=None: boxes("02"),
    )
    state = service.start("fit the splitter", str(start))
    service.card(state, layout="photo")  # the zones are located on the start photo
    gate = StepGate(state_for=service.get, on_block=lambda r, ti: store.trace(ti["job_id"], "gate_block", reason=r),
                    on_review=service.review)
    return service, state, gate, build_tools(service), model, tmp_path


def save(tmp_path: Path, img, name: str) -> str:
    p = tmp_path / name
    cv2.imwrite(str(p), img)
    return str(p)


def submit(job, path: str) -> dict:
    _s, state, gate, tools, _m, _t = job
    return run_tool_through_gate(gate, tools, "submit_photo", {"job_id": state.job_id, "photo_path": path})


def advance(job, agent=None) -> dict:
    _s, state, gate, tools, _m, _t = job
    return run_tool_through_gate(
        gate, tools, "advance_step", {"job_id": state.job_id, "step_id": state.current + 1}, agent=agent
    )


def perception_rows(state) -> list[dict]:
    return [r for r in store.read_trace(state.job_id) if r["event"] == "perception"]


@pytest.fixture(scope="module")
def part():
    img = photo("04")
    h, w = img.shape[:2]
    return img[int(0.38 * h) : int(0.80 * h), int(0.22 * w) : int(0.80 * w)].copy()


# ------------------------------------------------------------------------- the switch


def test_the_layer_is_on_unless_switched_off(monkeypatch):
    monkeypatch.delenv("STEPSPOTTER_PERCEPTION", raising=False)
    assert JobService(plan_fn=lambda *a: plan()).use_perception is True
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "0")
    assert JobService(plan_fn=lambda *a: plan()).use_perception is False


# ------------------------------------------------------------------ blocks before a model


def test_a_blurred_photo_is_refused_without_calling_the_model(job):
    service, state, _gate, _tools, model, tmp = job
    out = submit(job, save(tmp, synthetic.gaussian_blur(photo("02"), 4), "blur.jpg"))
    assert model.calls == []  # the model was never asked
    assert "OpenCV, no model call" in out["content"]
    assert "Hold the phone still" in out["content"]  # one concrete instruction
    v = state.verdicts[0]
    assert v.passed is False and v.source == "opencv"
    row = perception_rows(state)[-1]
    assert row["decision"] == "retake" and row["reason_code"] == "blurry"
    assert row["llm_called"] is False and row["llm_calls_saved"] == 1
    assert isinstance(row["ms_total"], (int, float)) and row["ms_total"] > 0
    verdict_row = [r for r in store.read_trace(state.job_id) if r["event"] == "verdict"][-1]
    assert verdict_row["source"] == "opencv"
    res = advance(job)
    assert res["cancelled"] and res["status"] == "error"
    assert state.current == 0


class TwoPhotoModel(Model):
    """A verifier that also takes the person's first photo, and answers same_place."""

    def __init__(self, passed: bool = True, same_place: bool = True) -> None:
        super().__init__(passed)
        self.same_place = same_place

    def __call__(self, step, photo_path, model_id=None, context=None, zone_crop=None, reference_photo=None):
        self.calls.append({"photo": photo_path, "context": context, "zone_crop": zone_crop,
                           "reference_photo": reference_photo})
        v = StepVerdict(step_id=step.id, passed=self.passed and self.same_place, reason="compared both photos")
        if reference_photo is not None:
            v.same_place = self.same_place
        return v


def _job_with(tmp_path, model):
    start = tmp_path / "start.jpg"
    shutil.copy(ROOT / SCENES["02"]["file"], start)
    service = JobService(
        plan_fn=lambda task, photo, model_id=None: plan(),
        verify_fn=model,
        locate_fn=lambda step, photo, model_id=None: boxes("02"),
    )
    state = service.start("fit the splitter", str(start))
    service.card(state, layout="photo")
    gate = StepGate(state_for=service.get, on_review=service.review)
    return service, state, gate, build_tools(service), model, tmp_path


@pytest.mark.parametrize("same_place", [True, False])
def test_a_photo_opencv_cannot_line_up_goes_to_the_two_photo_check(tmp_path, same_place):
    """Not refused by OpenCV: routed. The model gets BOTH photos; the gate needs same_place."""
    model = TwoPhotoModel(passed=True, same_place=same_place)
    job = _job_with(tmp_path, model)
    _service, state, _gate, _tools, _m, tmp = job
    submit(job, save(tmp, photo("03"), "closeup-another-day.jpg"))  # real photo, same panel
    assert state.perception[0].decision == "place_unconfirmed"
    assert len(model.calls) == 1
    assert model.calls[0]["reference_photo"] == state.start_photo  # the two-photo call
    assert model.calls[0]["zone_crop"] is None  # nothing lined up to crop
    row = perception_rows(state)[-1]
    assert row["route"] == "llm_two_image" and row["llm_called"] is True
    v = state.verdicts[0]
    assert v.route == "llm_two_image" and v.same_place is same_place
    res = advance(job)
    assert res["cancelled"] is (not same_place)
    assert state.current == (1 if same_place else 0)


def test_without_a_two_photo_verifier_the_unconfirmed_place_fails_closed(tmp_path):
    """A verifier that cannot take the first photo cannot confirm the place: no pass."""
    model = Model(passed=True)  # single-photo signature only
    job = _job_with(tmp_path, model)
    _service, state, _gate, _tools, _m, tmp = job
    submit(job, save(tmp, photo("04"), "elsewhere.jpg"))
    assert len(model.calls) == 1
    v = state.verdicts[0]
    assert v.passed is False and "same place" in v.reason
    assert advance(job)["cancelled"]


def test_the_gate_wants_same_place_even_if_a_pass_was_written_in(tmp_path):
    model = TwoPhotoModel(passed=True, same_place=True)
    job = _job_with(tmp_path, model)
    _service, state, _gate, _tools, _m, tmp = job
    submit(job, save(tmp, photo("04"), "elsewhere.jpg"))
    state.verdicts[0] = StepVerdict(step_id=1, passed=True, reason="written in")  # same_place None
    res = advance(job)
    assert res["cancelled"] and "did not confirm it is the same place" in res["content"]


def test_a_confirmed_place_is_checked_on_one_photo(job, part):
    _service, state, _gate, _tools, model, tmp = job
    done = synthetic.perspective(synthetic.paste_patch(photo("02"), zone("02", "act"), part, cover=0.6, seed=1), 0.05, 2)
    submit(job, save(tmp, done, "done.jpg"))
    assert perception_rows(state)[-1]["route"] == "llm_single"
    assert state.verdicts[0].route == "llm_single"
    assert "reference_photo" not in model.calls[0] or model.calls[0].get("reference_photo") is None


def test_sending_the_start_photo_again_is_a_replay(job):
    _service, state, _gate, _tools, model, tmp = job
    submit(job, save(tmp, synthetic.jpeg(photo("02"), 70), "same-again.jpg"))
    assert model.calls == []
    assert state.perception[0].decision == "replay"


def test_no_change_at_the_work_zone_is_refused_when_the_step_must_change_something(job):
    _service, state, _gate, _tools, model, tmp = job
    reshot = synthetic.sensor_noise(synthetic.perspective(photo("02"), 0.10, 3), 3.0, 3)
    submit(job, save(tmp, reshot, "nothing-done.jpg"))
    assert model.calls == []
    assert state.perception[0].decision == "no_change"


# ---------------------------------------------------------------------- reaches the model


def test_a_good_photo_goes_to_the_model_with_the_aligned_work_zone(job, part):
    _service, state, _gate, _tools, model, tmp = job
    done = synthetic.perspective(synthetic.paste_patch(photo("02"), zone("02", "act"), part, cover=0.6, seed=1), 0.05, 2)
    out = submit(job, save(tmp, done, "done.jpg"))
    assert len(model.calls) == 1
    assert model.calls[0]["zone_crop"] and model.calls[0]["zone_crop"][:2] == b"\xff\xd8"  # a JPEG
    assert model.calls[0]["context"] is None  # findings only go along on a stuck override
    assert "That looks done" in out["content"]
    assert state.verdicts[0].source == "llm"
    assert perception_rows(state)[-1]["llm_called"] is True
    res = advance(job)
    assert res["cancelled"] is False and state.current == 1
    rep = state.perception[0]
    assert set(rep.artifacts) == {"match", "heatmap", "quality"}
    assert all(Path(p).is_file() for p in rep.artifacts.values())


# ------------------------------------------------------------------ a person's approval


def test_a_change_in_the_do_not_touch_zone_stops_the_run_for_a_person(job, part):
    service, state, _gate, _tools, model, tmp = job
    touched = synthetic.perspective(synthetic.paste_patch(photo("02"), zone("02", "avoid"), part, cover=0.6, seed=2), 0.05, 4)
    out = submit(job, save(tmp, touched, "touched.jpg"))
    assert model.calls == []
    assert "STOP touching it" in out["content"]
    assert state.perception[0].decision == "touched_avoid"

    carrier = _InterruptCarrier()
    res = advance(job, agent=carrier)
    assert res["status"] == "interrupt"  # not a cancel: the run waits for a person
    assert res["interrupt"].name == "human_review"
    assert "telecom module" in res["content"]["message"]
    assert state.current == 0

    # The person looks and approves; the run resumes with their answer.
    for interrupt in carrier._interrupt_state.interrupts.values():
        interrupt.response = {"approved": True, "answer": "checked it, the module is fine"}
    resumed = advance(job, agent=carrier)
    assert resumed["status"] == "error" and "A person approved" in resumed["content"]
    assert state.approvals == {0: "checked it, the module is fine"}
    assert state.current == 0  # approval is not a pass: the step still needs its photo
    rows = [r for r in store.read_trace(state.job_id) if r["event"] == "human_review"]
    assert rows and rows[-1]["approved"] is True

    # The same do-not-touch change no longer stops the run; the model judges the step.
    done = synthetic.paste_patch(
        synthetic.paste_patch(photo("02"), zone("02", "avoid"), part, cover=0.6, seed=2), zone("02", "act"), part, cover=0.6, seed=5
    )
    submit(job, save(tmp, synthetic.perspective(done, 0.05, 6), "done-after-review.jpg"))
    assert len(model.calls) == 1
    assert advance(job)["cancelled"] is False


# ---------------------------------------------------------------------- defence in depth


def test_the_gate_refuses_on_a_blocking_report_even_beside_a_passing_verdict(job):
    service, state, _gate, _tools, _model, tmp = job
    submit(job, save(tmp, synthetic.gaussian_blur(photo("02"), 4), "blur.jpg"))
    state.verdicts[0] = StepVerdict(step_id=1, passed=True, reason="somebody wrote a pass in")
    res = advance(job)
    assert res["cancelled"] and "Blocked by the photo check (OpenCV, retake)" in res["content"]
    assert state.current == 0


# ------------------------------------------------------------------------- agent tools


def test_inspect_photo_offers_one_ask_for_the_first_angle_and_never_refuses(job):
    _service, state, gate, tools, model, tmp = job
    res = run_tool_through_gate(gate, tools, "inspect_photo",
                                {"job_id": state.job_id, "photo_path": save(tmp, photo("04"), "x.jpg")})
    assert "place not confirmed" in res["content"] and "ONCE" in res["content"]
    assert "submit this one" in res["content"]
    assert model.calls == [] and state.evidence == []
    assert perception_rows(state)[-1]["route"] == "llm_two_image"


def test_inspect_photo_tells_the_agent_what_to_ask_for_and_stores_nothing(job):
    _service, state, gate, tools, model, tmp = job
    dark = save(tmp, synthetic.exposure(photo("02"), 0.12), "dark.jpg")
    res = run_tool_through_gate(gate, tools, "inspect_photo", {"job_id": state.job_id, "photo_path": dark})
    assert "Do not submit this one" in res["content"] and "light" in res["content"]
    assert model.calls == [] and 0 not in state.verdicts and state.evidence == []
    assert perception_rows(state)[-1]["mode"] == "probe"


def test_submit_video_picks_the_sharp_frame_and_checks_it(job, part):
    _service, state, gate, tools, model, tmp = job
    done = synthetic.perspective(synthetic.paste_patch(photo("02"), zone("02", "act"), part, cover=0.6, seed=1), 0.05, 2)
    small = synthetic.resize(done, 0.75)
    frames = [synthetic.motion_blur(small, 25, a) for a in (0, 45)] + [small] + [synthetic.motion_blur(small, 25, 90)]
    video = tmp / "clip.avi"
    h, w = small.shape[:2]
    vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 8, (w, h))
    if not vw.isOpened():
        pytest.skip("this OpenCV build cannot write MJPG video")
    for f in frames:
        vw.write(f)
    vw.release()
    res = run_tool_through_gate(gate, tools, "submit_video", {"job_id": state.job_id, "video_path": str(video)})
    assert "picked frame 2" in res["content"], res["content"]
    assert len(model.calls) == 1 and "video-01-01.jpg" in model.calls[0]["photo"]
    assert any(r["event"] == "keyframes" for r in store.read_trace(state.job_id))
