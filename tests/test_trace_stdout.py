"""STEPSPOTTER_TRACE_STDOUT=1: perception and limits rows on stdout, for log metrics.

The contract the AWS metric filters depend on: one JSON object per line, ``event``,
``decision``, ``reason_code``, ``llm_called``, ``ms_total``, ``step_id`` on the perception
line — and nothing private: no task text, no chat, no plan, no caller IP, no full paths.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import pytest

from stepspotter import store
from stepspotter.guide import JobService
from stepspotter.models import Plan, Step
from stepspotter.perception import imgio, synthetic

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "src" / "stepspotter" / "web" / "demo_photos" / "02-panel-inside.jpg"
SECRET_TASK = "fix the thing in my secret basement at 12 Example Road"


def _lines(out: str) -> list[dict]:
    return [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]


def _job(tmp_path) -> tuple[JobService, object]:
    start = tmp_path / "start.jpg"
    shutil.copy(PHOTO, start)
    service = JobService(
        plan_fn=lambda *a, **k: Plan(
            job_title="j", safety_class="diy_ok",
            steps=[Step(id=1, title="t", action="a", evidence_required="e")],
        ),
        verify_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called")),
        locate_fn=lambda *a, **k: [],
        use_perception=True,
    )
    return service, service.start(SECRET_TASK, str(start))


def test_perception_and_limits_rows_go_to_stdout_and_nothing_else(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("STEPSPOTTER_TRACE_STDOUT", "1")
    service, state = _job(tmp_path)
    blurry = tmp_path / "blurry.jpg"
    cv2.imwrite(str(blurry), synthetic.gaussian_blur(imgio.load(PHOTO), 4))
    service.verify(state, str(blurry))
    store.trace("limits", "rate_limited", bucket="photos", ip="203.0.113.7", path="/api/jobs/x/photo")
    out = capsys.readouterr().out

    lines = _lines(out)
    events = [(ln["job_id"], ln["event"]) for ln in lines]
    assert events == [(state.job_id, "perception"), ("limits", "rate_limited")], events
    p = lines[0]
    for key in ("event", "decision", "reason_code", "llm_called", "ms_total", "step_id", "at", "job_id"):
        assert key in p, key
    assert p["decision"] == "retake" and p["reason_code"] == "blurry"
    assert p["llm_called"] is False and p["step_id"] == 1
    assert isinstance(p["ms_total"], (int, float))
    assert p["photo"] == "blurry.jpg"  # a basename, not a path on this machine
    assert all(not isinstance(v, (dict, list)) for v in p.values()), "perception lines stay flat"

    lim = lines[1]
    assert "ip" not in lim and lim["ip_tag"] and len(lim["ip_tag"]) == 10
    assert "203.0.113.7" not in out
    assert SECRET_TASK not in out and "basement" not in out
    assert str(tmp_path) not in out


def test_nothing_is_printed_without_the_switch(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("STEPSPOTTER_TRACE_STDOUT", raising=False)
    service, state = _job(tmp_path)
    blurry = tmp_path / "blurry.jpg"
    cv2.imwrite(str(blurry), synthetic.gaussian_blur(imgio.load(PHOTO), 4))
    service.verify(state, str(blurry))
    assert _lines(capsys.readouterr().out) == []
    # ...and the job's own trace still has everything
    assert any(r["event"] == "perception" for r in store.read_trace(state.job_id))


@pytest.mark.parametrize("event", ["start_job", "plan", "verdict", "ask", "answer", "card"])
def test_private_events_never_mirror(event):
    assert store.stdout_line({"job_id": "job-x", "event": event, "task": SECRET_TASK}) is None
