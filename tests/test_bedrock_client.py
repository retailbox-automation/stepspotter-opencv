"""Every Bedrock client the app creates retries (adaptive) with timeouts; a busy model that
survives the retries is a friendly 503 on the web, not a 502 with the error text. Offline:
clients are created (no call is made) and the models that answer are scripted."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError, EventStreamError
from fastapi.testclient import TestClient
from strands.types.exceptions import ModelThrottledException

from stepspotter import bedrock_client, vision
from stepspotter.guide import JobService, build_agent
from stepspotter.models import Plan, Step, StepVerdict
from stepspotter.scripted_model import Call, ScriptedModel, Turn
from stepspotter.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]
START = ROOT / SCENES["02"]["file"]


def busy(stream: bool = True) -> ClientError:
    """What Bedrock sends when it is overloaded: inside a ConverseStream response (an event,
    lowercase code) or as the HTTP answer."""
    if stream:
        return EventStreamError(
            {"Error": {"Code": "serviceUnavailableException", "Message": "Bedrock is unable to process your request."}},
            "ConverseStream",
        )
    return ClientError({"Error": {"Code": "ServiceUnavailableException", "Message": "busy"}}, "ConverseStream")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """The retry waits a second between attempts; tests need not."""
    import strands.event_loop._retry as r

    async def instant(_s):
        return None

    monkeypatch.setattr(r.asyncio, "sleep", instant)


def _assert_configured(model) -> None:
    cfg = model.client.meta.config
    assert cfg.retries == {"total_max_attempts": 4, "mode": "adaptive"}, cfg.retries
    # and botocore actually wired them: its retry handler and adaptive rate limiter sit on the call
    handlers = model.client.meta.events._emitter._handlers.prefix_search("needs-retry.bedrock-runtime.ConverseStream")
    kinds = {type(getattr(h, "__self__", h)).__name__ for h in handlers}
    assert {"RetryHandler", "ClientRateLimiter"} <= kinds, kinds
    assert cfg.connect_timeout == bedrock_client.CONNECT_TIMEOUT_S and cfg.read_timeout == bedrock_client.READ_TIMEOUT_S
    assert "strands-agents" in (cfg.user_agent_extra or "")  # the SDK still adds its own user agent


def test_the_single_shot_agents_get_retries_and_timeouts():
    agent = vision.make_agent("You check whether a photo proves that one repair step was done.", "some-model")
    _assert_configured(agent.model)
    assert isinstance(agent._retry_strategy, bedrock_client.BusyRetry)


def test_the_guide_agent_gets_retries_and_timeouts():
    for model_id in ("some-model", None):
        agent, _svc, _gate = build_agent(service=JobService(use_house_memory=False), model_id=model_id, quiet=True)
        _assert_configured(agent.model)
        assert isinstance(agent._retry_strategy, bedrock_client.BusyRetry)


def test_the_web_question_agent_gets_retries_and_timeouts(monkeypatch, tmp_path):
    from stepspotter.web import ask

    monkeypatch.setenv("STEPSPOTTER_DATA", str(tmp_path))
    made = []
    real = bedrock_client.bedrock_model

    def spy(*a, **k):
        made.append(real(*a, **k))
        return ScriptedModel([Turn([], say="Hold the jack by its body.")])

    monkeypatch.setattr(bedrock_client, "bedrock_model", spy)
    state = JobService(plan_fn=lambda *a, **k: Plan(job_title="t", safety_class="diy_ok", steps=[
        Step(id=1, title="s", action="a", evidence_required="e")]), use_house_memory=False).start("t", str(START))
    assert ask.guide_answer(state, "how do I hold it?") == "Hold the jack by its body."
    assert len(made) == 1
    _assert_configured(made[0])


def test_the_attempts_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_BEDROCK_MAX_ATTEMPTS", "6")
    assert bedrock_client.client_config().retries == {"total_max_attempts": 6, "mode": "adaptive"}
    monkeypatch.setenv("STEPSPOTTER_BEDROCK_MAX_ATTEMPTS", "nonsense")
    assert bedrock_client.client_config().retries["total_max_attempts"] == 4


def test_busy_means_busy_and_nothing_else():
    assert bedrock_client.is_model_busy(busy(stream=True))
    assert bedrock_client.is_model_busy(busy(stream=False))
    assert bedrock_client.is_model_busy(ModelThrottledException("slow down"))
    wrapped = RuntimeError("the turn failed")
    wrapped.__cause__ = busy()
    assert bedrock_client.is_model_busy(wrapped)
    invalid = ClientError({"Error": {"Code": "ValidationException", "Message": "bad id"}}, "ConverseStream")
    assert not bedrock_client.is_model_busy(invalid)
    assert not bedrock_client.is_model_busy(ValueError("no"))


def test_a_busy_stream_is_retried_once_inside_the_turn():
    """botocore does not retry an error that arrives inside a 200 stream; the agent does."""
    model = ScriptedModel([Turn([], say="Here is step 1.")], fail_on={1: busy()})
    agent, _svc, _gate = build_agent(service=JobService(use_house_memory=False), model=model, quiet=True)
    assert str(agent("hello")).strip() == "Here is step 1."
    assert model.calls == 2


# ---------------------------------------------------------------- the web layer

J = lambda c: c["job_id"]  # noqa: E731


@pytest.fixture
def web(monkeypatch, tmp_path):
    monkeypatch.setenv("STEPSPOTTER_DATA", str(tmp_path))
    service = JobService(
        plan_fn=lambda *a, **k: Plan(job_title="Fit it", safety_class="diy_ok", steps=[
            Step(id=1, title="Fit it", action="a", evidence_required="e")]),
        verify_fn=lambda step, photo, model_id=None, **kw: StepVerdict(step_id=step.id, passed=True, reason="ok"),
        locate_fn=lambda *a, **k: [],
        use_house_memory=False,
    )
    model = ScriptedModel([
        Turn([Call("start_job", {"task": "fit it", "photo_path": lambda c: c["user"].split("photo of it: ")[1].split(".jpg")[0] + ".jpg"}),
              Call("show_step", {"job_id": J})], say="Here is step 1."),
        Turn([], say="Hold it by the body."),
    ])
    return TestClient(create_app(service, agent_model_fn=lambda: model)), model, service


def _start(client) -> str:
    r = client.post("/api/agent/start", data={"task": "fit it"}, files={"photo": ("p.jpg", START.read_bytes(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()["session"]


def test_a_busy_model_after_the_retries_is_a_friendly_503(web):
    client, model, _svc = web
    sid = _start(client)
    model.fail_on = {model.calls + 1: busy(), model.calls + 2: busy()}  # the first try and its one retry
    r = client.post(f"/api/agent/{sid}/say", data={"text": "how do I hold it?"})
    assert r.status_code == 503 and r.headers.get("retry-after") == "60"
    detail = r.json()["detail"]
    assert detail.startswith("The model is busy right now. Try again in a minute")
    assert "serviceUnavailable" not in detail and "Traceback" not in detail
    assert len(client.get(f"/api/agent/{sid}").json()["turns"]) == 1  # the failed turn is not shown as a turn


def test_a_model_fault_that_is_not_busy_stays_a_502(web):
    client, model, _svc = web
    sid = _start(client)
    model.fail_on = {model.calls + 1: ClientError({"Error": {"Code": "ValidationException", "Message": "bad"}}, "ConverseStream")}
    r = client.post(f"/api/agent/{sid}/say", data={"text": "how do I hold it?"})
    assert r.status_code == 502 and r.json()["detail"].startswith("The agent could not answer")


def test_a_busy_planner_on_the_code_driven_page_is_a_503_too(monkeypatch, tmp_path):
    monkeypatch.setenv("STEPSPOTTER_DATA", str(tmp_path))

    def planner(*a, **k):
        raise busy(stream=False)

    client = TestClient(create_app(JobService(plan_fn=planner, use_house_memory=False)))
    r = client.post("/api/jobs", data={"task": "fit it"}, files={"photo": ("p.jpg", START.read_bytes(), "image/jpeg")})
    assert r.status_code == 503 and "no job was started" in r.json()["detail"]
