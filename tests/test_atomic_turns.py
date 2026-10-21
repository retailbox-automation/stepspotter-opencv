"""A failed agent turn leaves no trace in the conversation — in memory, on disk, or in what
the agent sees next — while what its completed tools did stays. Offline: a scripted model
that raises in the middle of a turn, the real tools, OpenCV and the session store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stepspotter import store
from stepspotter.guide import JobService, build_agent, job_id_in_session, say
from stepspotter.models import Plan, Step, StepVerdict
from stepspotter.scripted_model import Call, ScriptedModel, Turn
from stepspotter.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]
START = str(ROOT / SCENES["02"]["file"])
OTHER = str(ROOT / SCENES["01"]["file"])

J = lambda c: c["job_id"]  # noqa: E731
SCRIPT = [
    Turn([Call("start_job", {"task": "fit the splitter", "photo_path": START}), Call("show_step", {"job_id": J})],
         say="Here is step 1."),
    # the turn that fails: one tool call goes through, then the model is unreachable
    Turn([Call("inspect_photo", {"job_id": J, "photo_path": OTHER})], say=lambda c: "Checked: " + c["last"][:60]),
]


class Recording(ScriptedModel):
    """Also keeps what it was sent on every call, to see what the agent 'remembers'."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.seen: list[list[dict]] = []

    async def stream(self, messages, *a, **k):
        self.seen.append([{"role": m["role"], "content": m["content"]} for m in messages])
        async for ev in super().stream(messages, *a, **k):
            yield ev


def _service() -> JobService:
    return JobService(
        plan_fn=lambda *a, **k: Plan(job_title="Fit the splitter", safety_class="diy_ok", steps=[
            Step(id=1, title="Fit it", action="a", evidence_required="e", expects_change=True)]),
        verify_fn=lambda step, photo, model_id=None, **kw: StepVerdict(step_id=step.id, passed=True, reason="ok"),
        locate_fn=lambda *a, **k: [],
        use_house_memory=False,
    )


def _plain(messages: list[dict]) -> list[tuple]:
    return [(m["role"], json.dumps(m["content"], sort_keys=True, default=str)) for m in messages]


def _disk(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("message_*.json"))}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("STEPSPOTTER_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "1")
    return tmp_path


def test_a_turn_that_fails_half_way_leaves_the_history_as_it_was(env):
    sessions = env / "sessions"
    model = Recording(SCRIPT)
    service = _service()
    agent, _svc, _gate = build_agent(service=service, session_id="s1", storage_dir=str(sessions), model=model, quiet=True)
    assert say(agent, "Start the job on my photo.") == "Here is step 1."
    job_id = job_id_in_session(agent)
    assert job_id
    before_mem, before_disk = _plain(agent.messages), _disk(sessions)
    rows_before = store.read_trace(job_id)
    assert before_disk  # the session really is on disk

    model.fail_on = {model.calls + 2: RuntimeError("Bedrock went away")}  # the 2nd model call of the turn
    with pytest.raises(Exception, match="Bedrock went away"):  # Strands wraps it in EventLoopException
        say(agent, "Is this photo good?")

    # the conversation forgot the turn: in memory, on disk, and in a fresh restore
    assert _plain(agent.messages) == before_mem
    assert _disk(sessions) == before_disk
    again, _s, _g = build_agent(service=service, session_id="s1", storage_dir=str(sessions),
                                model=Recording(SCRIPT), quiet=True)
    assert _plain(again.messages) == before_mem
    # what the completed tool did is real and stays: OpenCV looked at the photo
    new = store.read_trace(job_id)[len(rows_before):]
    assert [r["event"] for r in new if r["event"] == "perception"] == ["perception"]

    # the person sends it again: one clean copy of the turn, nothing left over
    reply = say(agent, "Is this photo good?")
    assert reply.startswith("Checked:")
    added = agent.messages[len(before_mem):]
    assert [m["role"] for m in added] == ["user", "assistant", "user", "assistant"]
    users = [m for m in model.seen[-1] if m["role"] == "user" and any("text" in b for b in m["content"])]
    assert [b["text"] for m in users for b in m["content"] if "text" in b] == [
        "Start the job on my photo.", "Is this photo good?"]  # the model never saw the failed turn


def test_the_web_agent_does_not_carry_a_failed_turn_into_the_next_one(env):
    model = Recording(SCRIPT)
    client = TestClient(create_app(_service(), agent_model_fn=lambda: model))
    r = client.post("/api/agent/start", data={"task": "fit the splitter"},
                    files={"photo": ("p.jpg", Path(START).read_bytes(), "image/jpeg")})
    sid = r.json()["session"]
    model.fail_on = {model.calls + 2: RuntimeError("Bedrock went away")}
    failed = client.post(f"/api/agent/{sid}/say", data={"text": "Is this photo good?"})
    assert failed.status_code == 502
    assert len(client.get(f"/api/agent/{sid}").json()["turns"]) == 1

    ok = client.post(f"/api/agent/{sid}/say", data={"text": "Is this photo good?"})
    assert ok.status_code == 200, ok.text
    sent = model.seen[-1]
    said = [b["text"] for m in sent if m["role"] == "user" for b in m["content"] if "text" in b]
    assert said.count("Is this photo good?") == 1  # restored from disk without the failed turn
    tool_uses = [b for m in sent for b in m["content"] if "toolUse" in b]
    assert [t["toolUse"]["name"] for t in tool_uses] == ["start_job", "show_step", "inspect_photo"]
