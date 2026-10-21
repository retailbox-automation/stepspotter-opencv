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
