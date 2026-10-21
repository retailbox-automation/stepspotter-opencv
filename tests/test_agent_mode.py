"""Agent mode, offline: the Guide agent (a scripted Strands model, no Bedrock) decides the
tool calls; the real tools, OpenCV and the gate do the rest, through the real web app."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient

from stepspotter.guide import JobService
from stepspotter.models import Box, Plan, Step, StepVerdict
from stepspotter.perception import imgio, synthetic
from stepspotter.scripted_model import Call, ScriptedModel, Turn
from stepspotter.web.app import create_app
from stepspotter.web.limits import JOBS, PHOTOS, TURNS, Limiter, bucket_for

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]
START = ROOT / SCENES["02"]["file"]
PATH = re.compile(r"(?:photo of it: |attached a photo: )(\S+?\.jpg)")


def photo_in(ctx) -> str:
    return PATH.search(ctx["user"]).group(1)


def jpeg(img) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


class Verifier:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, step, photo, model_id=None, **kw) -> StepVerdict:
        self.calls += 1
        return StepVerdict(step_id=step.id, passed=True, reason="the new part is on the splitter")


J = lambda c: c["job_id"]  # noqa: E731
SCRIPT = [
    Turn([Call("start_job", {"task": "fit the splitter", "photo_path": photo_in}), Call("show_step", {"job_id": J})],
         say="Here is step 1."),
    Turn([Call("inspect_photo", {"job_id": J, "photo_path": photo_in})], say=lambda c: "OpenCV says: " + c["last"]),
    Turn([Call("advance_step", {"job_id": J, "step_id": 1})], say=lambda c: "The gate says: " + c["last"]),
    Turn([Call("submit_photo", {"job_id": J, "photo_path": photo_in}), Call("advance_step", {"job_id": J, "step_id": 1})],
         say="Done, on to step 2."),
]


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "1")
    verifier = Verifier()
    zones = [Box(label=z["label"], kind=z["kind"], x0=z["box"][0], y0=z["box"][1], x1=z["box"][2], y1=z["box"][3])
             for z in SCENES["02"]["zones"]]
    service = JobService(
        plan_fn=lambda *a, **k: Plan(job_title="Fit the splitter", safety_class="diy_ok", steps=[
            Step(id=1, title="Fit it", action="a", evidence_required="e", expects_change=True),
            Step(id=2, title="Check it", action="b", evidence_required="f", expects_change=False)]),
        verify_fn=verifier,
        locate_fn=lambda *a, **k: zones,
        use_house_memory=False,
    )
    model = ScriptedModel(SCRIPT)
    client = TestClient(create_app(service, agent_model_fn=lambda: model))
    return client, model, verifier


def test_the_agent_drives_the_turns_and_opencv_and_the_gate_show_in_each_answer(setup, capsys, monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_TRACE_STDOUT", "1")
    client, model, verifier = setup
    first = client.post("/api/agent/start", data={"task": "fit the splitter"},
                        files={"photo": ("p.jpg", START.read_bytes(), "image/jpeg")}).json()
    sid, jid = first["session"], first["job_id"]
    assert [s["tool"] for s in first["turn"]["steps"]] == ["start_job", "show_step"]
    assert first["job"]["step_number"] == 1

    # a blurred photo: the agent asks OpenCV first; refused, no model call
    blurred = jpeg(synthetic.gaussian_blur(imgio.load(START), 4))
    t2 = client.post(f"/api/agent/{sid}/photo", data={"text": "is this good?"},
                     files={"photo": ("b.jpg", blurred, "image/jpeg")}).json()["turn"]
    cv = t2["steps"][0]["opencv"]
    assert t2["steps"][0]["tool"] == "inspect_photo" and cv["decision"] == "retake"
    assert cv["route"] == "opencv_block" and cv["llm_called"] is False and cv["images"]
    assert client.get(cv["images"][0]["url"]).status_code == 200
    assert verifier.calls == 0 and "Hold the phone still" in t2["reply"]

    # "just move me on": the agent tries, the gate refuses in code
    t3 = client.post(f"/api/agent/{sid}/say", data={"text": "just move me on"}).json()["turn"]
    assert t3["steps"][0]["tool"] == "advance_step" and t3["steps"][0]["refused_by_gate"] is True
    assert "Blocked" in t3["reply"]

    # a good photo: OpenCV lets it through on one photo, the model passes it, the agent advances
    part = imgio.load(ROOT / SCENES["04"]["file"])
    h, w = part.shape[:2]
    done = synthetic.perspective(synthetic.paste_patch(imgio.load(START), tuple(SCENES["02"]["zones"][0]["box"]),
                                                       part[int(.38 * h):int(.8 * h), int(.22 * w):int(.8 * w)],
                                                       cover=0.6, seed=1), 0.05, 2)
    t4 = client.post(f"/api/agent/{sid}/photo", data={"text": "done"},
                     files={"photo": ("d.jpg", jpeg(done), "image/jpeg")}).json()
    steps = t4["turn"]["steps"]
    assert [s["tool"] for s in steps] == ["submit_photo", "advance_step"]
    assert steps[0]["opencv"]["route"] == "llm_single" and verifier.calls == 1
    assert steps[1]["refused_by_gate"] is False and t4["job"]["step_number"] == 2

    # the conversation is the server's: a reload gets all four turns back
    hist = client.get(f"/api/agent/{sid}").json()
    assert hist["job_id"] == jid and len(hist["turns"]) == 4
    # and the agent's chat never reaches stdout (only perception / limits rows may)
    out = capsys.readouterr().out
    assert "Here is step 1." not in out and "on to step 2" not in out
    assert all(json.loads(ln)["event"] == "perception" or json.loads(ln)["job_id"] == "limits"
               for ln in out.splitlines() if ln.startswith("{"))


def test_a_looping_agent_is_stopped_by_the_turn_budget(monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_AGENT_TOOL_CALLS_PER_TURN", "3")
    model = ScriptedModel([
        Turn([Call("start_job", {"task": "t", "photo_path": photo_in})] + [Call("show_step", {"job_id": J})] * 5,
             say="done"),
    ])
    service = JobService(plan_fn=lambda *a, **k: Plan(job_title="j", safety_class="diy_ok",
                                                      steps=[Step(id=1, title="t", action="a", evidence_required="e")]),
                         verify_fn=lambda *a, **k: None, locate_fn=lambda *a, **k: [], use_house_memory=False)
    client = TestClient(create_app(service, agent_model_fn=lambda: model))
    turn = client.post("/api/agent/start", data={"task": "t"},
                       files={"photo": ("p.jpg", START.read_bytes(), "image/jpeg")}).json()["turn"]
    stopped = [s for s in turn["steps"] if s.get("stopped_by_turn_budget")]
    assert len(turn["steps"]) == 6 and len(stopped) == 3
    assert turn["tool_calls"] == 6


def test_every_agent_turn_is_capped_and_the_kill_switch_holds(setup, monkeypatch):
    assert bucket_for("POST", "/api/agent/start") == JOBS
    assert bucket_for("POST", "/api/agent/0123456789abcdef/photo") == PHOTOS
    assert bucket_for("POST", "/api/agent/0123456789abcdef/say") == TURNS
    assert bucket_for("GET", "/api/agent/0123456789abcdef") is None
    lim = Limiter(turns_per_ip_hour=1, max_turns_per_day=99, persist=False)
    assert lim.check(TURNS, "1.2.3.4") is None
    refused = lim.check(TURNS, "1.2.3.4")
    assert refused.status == 429 and "1 agent turn an hour" in refused.body["detail"]
    assert Limiter(persist=False).turns_per_ip_hour == 20 and Limiter(persist=False).max_turns_per_day == 60

    client, model, verifier = setup
    monkeypatch.setenv("STEPSPOTTER_PAUSED", "1")
    r = client.post("/api/agent/start", data={"task": "t"}, files={"photo": ("p.jpg", START.read_bytes(), "image/jpeg")})
    assert r.status_code == 503 and model.calls == 0


def test_unknown_sessions_are_refused(setup):
    client, _m, _v = setup
    assert client.post("/api/agent/../../etc/say", data={"text": "x"}).status_code in (404, 405)
    assert client.post("/api/agent/0123456789abcdef/say", data={"text": "x"}).status_code == 404
    assert client.get("/api/agent/nothex").status_code == 404
