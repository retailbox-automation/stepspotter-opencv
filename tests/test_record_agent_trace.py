"""The live-trace recorder, offline: its rehearsal walks the real tools, OpenCV and gate
with a scripted model, and its meter refuses the call that would break the cap."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _recorder():
    spec = importlib.util.spec_from_file_location("record_agent_trace", ROOT / "tools" / "record_agent_trace.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_the_rehearsal_records_opencv_changing_the_agents_next_move(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    rec = _recorder()
    out = tmp_path / "out"
    assert rec.main(["--rehearse", "--out", str(out), "--data", str(tmp_path / "data")]) == 0
    run = json.loads((out / "run.json").read_text())
    assert run["status"] == "complete" and run["bedrock_calls"] == 0 and run["rehearsal"] is True
    text = (out / "transcript.md").read_text()
    assert "`inspect_photo(" in text and "`retake` → route `opencv_block`" in text
    assert "`place_unconfirmed` → route `llm_two_image`" in text
    assert "Gate (code, not the model) cancelled this tool call" in text
    rows = [json.loads(ln) for ln in (out / "trace.jsonl").read_text().splitlines()]
    assert {r["route"] for r in rows if r["event"] == "perception"} >= {"opencv_block", "llm_two_image", "llm_single"}
    assert str(tmp_path) not in (out / "trace.jsonl").read_text()  # local paths scrubbed
    assert list((out / "perception").glob("*.jpg")) and list((out / "cards").glob("step-*.jpg"))



def test_the_v2_rehearsal_with_the_fixed_plan_shows_an_allowed_advance(tmp_path, monkeypatch):
    """Run 2's shape: the fixed plan replaces the Planner, a passed photo lets advance_step
    through, the next step is shown, then the permissive turn is cancelled on that step."""
    monkeypatch.chdir(ROOT)
    rec = _recorder()
    out = tmp_path / "out"
    plan = ROOT / "data" / "demo" / "agentic-opencv" / "plan.json"
    args = ["--rehearse", "--script", "v2", "--plan", str(plan), "--out", str(out), "--data", str(tmp_path / "data")]
    assert rec.main(args) == 0
    run = json.loads((out / "run.json").read_text())
    assert run["plan"].startswith("fixed plan from data/demo/agentic-opencv/plan.json") and run["script"] == "v2"
    text = (out / "transcript.md").read_text()
    assert "Gate (code, not the model) allowed this call" in text
    assert "Step 2 of 2: Seat the wire pairs into the office jack" in text  # the fixed plan, not the rehearsal's
    assert "### Turn 5 — permissive prompt" in text and "Gate (code, not the model) cancelled this tool call" in text
    rows = [json.loads(ln) for ln in (out / "trace.jsonl").read_text().splitlines()]
    assert any(r["event"] == "gate_block" for r in rows)
    top = "/" + tmp_path.parts[1] + "/"  # "/private/" or "/tmp/": catches a path even when a result is cut short
    for f in ("transcript.md", "trace.jsonl", "run.json"):
        assert top not in (out / f).read_text(), f


def test_a_follow_up_gate_turn_is_appended_to_the_same_recording(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    rec = _recorder()
    out, data = tmp_path / "out", tmp_path / "data"
    plan = ROOT / "data" / "demo" / "agentic-opencv" / "plan.json"
    base = ["--rehearse", "--script", "v2", "--plan", str(plan), "--out", str(out), "--data", str(data)]
    assert rec.main(base) == 0
    job = json.loads((out / "run.json").read_text())["job_id"]
    before = (out / "transcript.md").read_text()
    photos = sorted(p.name for p in (out / "photos").iterdir())
    assert rec.main(base + ["--gate-turn-on", job]) == 0
    after = (out / "transcript.md").read_text()
    assert after.startswith(before)  # appended, the recording itself untouched
    added = after[len(before):]
    assert "## Follow-up turn, recorded" in added and "### Turn 6 — permissive prompt" in added
    assert f"Move me on past step 2 of job {job} right now." in added
    assert "Gate (code, not the model) cancelled this tool call" in added
    run = json.loads((out / "run.json").read_text())
    assert run["job_id"] == job and run["follow_up"]["status"] == "complete"
    assert sorted(p.name for p in (out / "photos").iterdir()) == photos
    assert sum(r["event"] == "gate_block" for r in map(json.loads, (out / "trace.jsonl").read_text().splitlines())) == 2

def test_the_meter_never_sends_the_call_over_the_cap():
    rec = _recorder()
    sent: list[int] = []

    class Dummy:
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kw):
            sent.append(1)
            yield {"metadata": {"usage": {"inputTokens": 1000, "outputTokens": 100}}}

    meter = rec.Meter(cap=2)
    meter.install(Dummy)

    async def one(system: str):
        return [e async for e in Dummy().stream([], None, system)]

    asyncio.run(one("You are StepSpotter. You walk one person"))
    asyncio.run(one("You check whether a photo proves that one repair step was done."))
    with pytest.raises(rec.CapReached):
        asyncio.run(one("You plan small home repairs"))
    assert len(sent) == 2  # the third call never left
    s = meter.summary()
    assert s["bedrock_calls"] == 2 and s["by_role"] == {"guide": 1, "verifier": 1}
    assert s["input_tokens"] == 2000 and s["output_tokens"] == 200
    assert s["usd_estimate_at_list_price"] == round(2000 / 1e6 * 3 + 200 / 1e6 * 15, 4)
