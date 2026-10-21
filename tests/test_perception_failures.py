"""When the OpenCV layer is wrong, a person must not be trapped by it.

The stuck rule (perception/inspect.py, STUCK RULE): after STUCK_AFTER consecutive OpenCV
blocks on one step, the next photo that OpenCV would refuse for quality, place or "no
change" goes to the model check WITH OpenCV's findings attached, marked ``overridden`` on
the report and the trace. A replay never is (a new photo always clears it).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import pytest

from stepspotter import store
from stepspotter.gate import StepGate
from stepspotter.guide import JobService, build_tools, run_tool_through_gate
from stepspotter.models import Box, Plan, Step, StepVerdict
from stepspotter.perception import imgio, synthetic
from stepspotter.perception.inspect import STUCK_AFTER

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]


@pytest.fixture(autouse=True)
def perception_on(monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "1")


class Model:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, step, photo_path, model_id=None, context=None, zone_crop=None) -> StepVerdict:
        self.calls.append({"photo": photo_path, "context": context})
        return StepVerdict(step_id=step.id, passed=False, reason="the model is not convinced either")


@pytest.fixture
def job(tmp_path):
    start = tmp_path / "start.jpg"
    shutil.copy(ROOT / SCENES["05"]["file"], start)
    zones = [
        Box(label=z["label"], kind=z["kind"], x0=z["box"][0], y0=z["box"][1], x1=z["box"][2], y1=z["box"][3])
        for z in SCENES["05"]["zones"]
    ]
    model = Model()
    service = JobService(
        plan_fn=lambda *a, **k: Plan(
            job_title="j",
            safety_class="diy_ok",
            steps=[Step(id=1, title="Seat the pairs", action="a", evidence_required="e", expects_change=True)],
        ),
        verify_fn=model,
        locate_fn=lambda *a, **k: zones,
    )
    state = service.start("seat the pairs", str(start))
    service.card(state, layout="photo")
    gate = StepGate(state_for=service.get)
    return service, state, gate, build_tools(service), model, tmp_path


def send(job, img, name):
    _s, state, gate, tools, _m, tmp = job
    p = tmp / name
    cv2.imwrite(str(p), img)
    return run_tool_through_gate(gate, tools, "submit_photo", {"job_id": state.job_id, "photo_path": str(p)})


def test_after_k_blocks_the_next_photo_reaches_the_model_with_the_findings(job):
    _service, state, _gate, _tools, model, _tmp = job
    blurry = synthetic.gaussian_blur(imgio.load(ROOT / SCENES["05"]["file"]), 4)
    for i in range(STUCK_AFTER):
        send(job, synthetic.sensor_noise(blurry, 1.0, i), f"blurry-{i}.jpg")
        assert model.calls == [], f"photo {i + 1} should still be refused by OpenCV"
        assert state.perception_streak[0] == i + 1
    send(job, synthetic.sensor_noise(blurry, 1.0, 99), "blurry-again.jpg")
    assert len(model.calls) == 1, "a person stuck on OpenCV blocks must get the model's look"
    ctx = model.calls[0]["context"]
    assert ctx and "OpenCV would have refused this photo (retake: blurry)" in ctx
    rep = state.perception[0]
    assert rep.overridden and not rep.blocks
    row = [r for r in store.read_trace(state.job_id) if r["event"] == "perception"][-1]
    assert row["overridden"] is True and row["llm_called"] is True
    assert state.perception_streak[0] == 0  # reaching the model resets the streak
    assert state.verdicts[0].source == "llm"


def test_a_replay_is_never_let_through(job):
    _service, state, _gate, _tools, model, _tmp = job
    start = imgio.load(state.start_photo)
    for i in range(STUCK_AFTER + 2):
        send(job, synthetic.jpeg(start, 60 + i), f"again-{i}.jpg")
    assert model.calls == []
    assert state.perception[0].decision == "replay" and not state.perception[0].overridden


def test_the_override_does_not_leak_into_the_next_step_or_survive_a_model_look(job):
    service, state, _gate, _tools, model, _tmp = job
    blurry = synthetic.gaussian_blur(imgio.load(ROOT / SCENES["05"]["file"]), 4)
    for i in range(STUCK_AFTER + 1):
        send(job, synthetic.sensor_noise(blurry, 1.0, 10 + i), f"b{i}.jpg")
    assert len(model.calls) == 1
    send(job, synthetic.sensor_noise(blurry, 1.0, 50), "b-next.jpg")
    assert len(model.calls) == 1, "after the model looked, OpenCV blocks again from a fresh streak"
    assert state.perception_streak[0] == 1
