"""A Strands model that plays a script instead of calling Bedrock — for tests and rehearsals.

Never used to serve anyone. Two users:

* the offline tests of the agent-driven web mode (no Bedrock in tests);
* ``tools/record_agent_trace.py --rehearse``, which walks the recorder end to end for
  free before a live run spends a single model call.

The script is a list of turns, one per message the person sends. A turn is the tool
calls the "model" makes in order (one per model call, exactly as a real model emits
them) and then the text it ends with. Inputs and the closing text may be callables of
the run's context — the job id read back out of ``start_job``'s answer, and every tool
result so far — so a script can say "advance the job you just started" without knowing
its id in advance.

Everything the tools do is real: the tools run, the gate hook fires, OpenCV looks at the
photos. Only the choice of which tool to call is scripted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable

from strands.models import Model

JOB_ID = re.compile(r"job-\d{8}-\d{6}-[0-9a-f]{4}")

Ctx = dict[str, Any]
Value = Any  # a plain value, or a callable(ctx) -> value


def _resolve(v: Value, ctx: Ctx) -> Any:
    return v(ctx) if callable(v) else v


@dataclass
class Call:
    name: str
    input: dict[str, Value] = field(default_factory=dict)


@dataclass
class Turn:
    calls: list[Call] = field(default_factory=list)
    say: Value = "OK."


def _text_of(block: dict) -> str:
    if "text" in block:
        return str(block["text"])
    res = block.get("toolResult") or {}
    return " ".join(str(c.get("text", "")) for c in res.get("content", []) if isinstance(c, dict))


class ScriptedModel(Model):
    """Plays ``turns`` back. Counts its own calls; raises if the script runs out."""

    def __init__(self, turns: list[Turn]) -> None:
        self.turns = turns
        self.calls = 0

    # -- the abstract surface Strands needs -----------------------------------
    def get_config(self) -> dict:
        return {"model_id": "scripted"}

    def update_config(self, **kwargs: Any) -> None:  # pragma: no cover - nothing to configure
        pass

    async def structured_output(self, *a: Any, **k: Any):  # pragma: no cover
        raise NotImplementedError("the scripted model only drives tool calls")
        yield  # noqa: unreachable - makes this an async generator

    # -- the script ------------------------------------------------------------
    def _position(self, messages: list[dict]) -> tuple[int, int, Ctx]:
        """(turn index, tool calls already made this turn, context) from the history."""
        turn = -1
        done = 0
        ctx: Ctx = {"results": [], "job_id": None}
        for m in messages:
            content = m.get("content") or []
            if m.get("role") == "user":
                results = [b for b in content if isinstance(b, dict) and "toolResult" in b]
                if results:
                    done += len(results)
                    for b in results:
                        text = _text_of(b)
                        ctx["results"].append(text)
                        found = JOB_ID.findall(text)
                        if found and ctx["job_id"] is None:
                            ctx["job_id"] = found[0]
                else:
                    turn += 1
                    done = 0
        ctx["last"] = ctx["results"][-1] if ctx["results"] else ""
        return turn, done, ctx

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs: Any) -> AsyncGenerator[dict, None]:
        self.calls += 1
        turn_i, done, ctx = self._position(messages)
        if turn_i < 0 or turn_i >= len(self.turns):
            raise RuntimeError(f"the script has no turn {turn_i + 1}")
        turn = self.turns[turn_i]
        yield {"messageStart": {"role": "assistant"}}
        if done < len(turn.calls):
            call = turn.calls[done]
            tool_input = {k: _resolve(v, ctx) for k, v in call.input.items()}
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"s{self.calls}", "name": call.name}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": str(_resolve(turn.say, ctx))}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
                            "metrics": {"latencyMs": 0}}}
