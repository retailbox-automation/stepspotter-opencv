"""Agent mode: the Guide agent drives the turn, on the web.

The default page is code-driven — the page decides "check this photo", "move on". Here
the person's words and photo go to the Guide agent (Strands + Bedrock, the same
``build_agent`` as ``stepspotter chat``), and the AGENT decides which tools to call:
``inspect_photo``, ``submit_photo``, ``advance_step``, ``escalate``… The ``StepGate`` hook
still sits under every tool call, so the agent can try to skip and the code refuses.
Each answer comes back with the tool calls it made, what OpenCV decided about each photo
(decision, route, time, pictures) and any gate refusal — the perception → decision →
action loop, visible per turn.

Spend and abuse: every turn is one of the capped buckets in ``limits.py`` — starting a
job is a job, a turn with a photo is a photo check, a turn with text only is an agent
turn — and ``STEPSPOTTER_PAUSED`` refuses them all. A ``TurnBudget`` hook also cancels
tool calls past ``STEPSPOTTER_AGENT_TOOL_CALLS_PER_TURN`` (default 8) in one turn, so a
model that loops cannot run up calls inside a single request.

State: the conversation lives in a Strands ``FileSessionManager`` per session id, under
the data root, exactly like the CLI; the turns as shown are appended to
``<data>/agent/<session>.turns.json`` so a reload shows them again.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from stepspotter import store
from stepspotter.guide import GUIDE_SYSTEM, JobService, build_agent, job_id_in_session, say
from stepspotter.web.trace_view import scrub

SESSION_RE = re.compile(r"^[0-9a-f]{16}$")
PHOTO_TOOLS = ("inspect_photo", "submit_photo", "submit_video")


def tool_call_cap() -> int:
    raw = os.environ.get("STEPSPOTTER_AGENT_TOOL_CALLS_PER_TURN", "")
    try:
        v = int(raw)
        return v if v > 0 else 8
    except ValueError:
        return 8


class TurnBudget(HookProvider):
    """Cancels any tool call past the per-turn cap. Reset at the start of every turn."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.calls = 0

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)

    def before(self, event: BeforeToolCallEvent) -> None:
        self.calls += 1
        if self.calls > self.cap:
            event.cancel_tool = (
                f"Stopped: this turn has already made {self.cap} tool calls. Answer the person "
                "with what you have and wait for their next message."
            )


def _ref(path: object) -> str | None:
    if not isinstance(path, str) or not path:
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".jpg") else name


class AgentMode:
    """Runs agent turns for the web, one Strands agent per session, restored per request."""

    def __init__(self, service: JobService, model_factory: Callable[[], Any] | None = None) -> None:
        self.service = service
        self.model_factory = model_factory

    # -- storage ----------------------------------------------------------------
    @staticmethod
    def sessions_dir() -> Path:
        d = store.data_root() / "agent"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _turns_file(self, sid: str) -> Path:
        return self.sessions_dir() / f"{sid}.turns.json"

    def history(self, sid: str) -> list[dict]:
        p = self._turns_file(sid)
        try:
            return json.loads(p.read_text()) if p.is_file() else []
        except ValueError:
            return []

    def exists(self, sid: str) -> bool:
        return bool(SESSION_RE.match(sid)) and self._turns_file(sid).is_file()

    # -- the agent ----------------------------------------------------------------
    def _agent(self, sid: str):
        budget = TurnBudget(tool_call_cap())
        model = self.model_factory() if self.model_factory else None
        agent, _svc, gate = build_agent(
            service=self.service,
            session_id=f"web-{sid}",
            system_prompt=GUIDE_SYSTEM,
            model_id=os.environ.get("STEPSPOTTER_MODEL") or None,
            storage_dir=str(self.sessions_dir() / "sessions"),
            model=model,
            hooks=[budget],
            quiet=True,
        )
        gate.on_review = self.service.review
        gate.on_block = lambda reason, ti: store.trace(
            ti.get("job_id") or "unknown", "gate_block", reason=reason, tool_input=ti, via="agent"
        )
        return agent, budget

    def run(self, sid: str, message: str, person: dict[str, Any]) -> dict[str, Any]:
        """One turn: the person's message to the agent, and what the agent did about it."""
        agent, budget = self._agent(sid)
        before = len(agent.messages)
        job_before = job_id_in_session(agent)
        trace_before = len(store.read_trace(job_before)) if job_before else 0
        reply = say(agent, message)
        job_id = job_id_in_session(agent)
        new_rows = store.read_trace(job_id)[trace_before if job_id == job_before else 0 :] if job_id else []
        cv_rows = [r for r in new_rows if r.get("event") == "perception"]
        steps = self._steps(agent.messages[before:], job_id, cv_rows)
        turn = {
            "person": person,
            "steps": steps,
            "reply": scrub(reply),
            "interrupted": "[run paused for a person" in reply,
            "tool_calls": budget.calls,
            "job_id": job_id,
        }
        turns = self.history(sid) + [turn]
        self._turns_file(sid).write_text(json.dumps(turns))
        return {"session": sid, "job_id": job_id, "turn": turn}

    def _steps(self, messages: list[dict], job_id: str | None, cv_rows: list[dict]) -> list[dict]:
        """Tool calls in order, each with its result, OpenCV's decision and any gate refusal."""
        steps: list[dict] = []
        by_id: dict[str, dict] = {}
        for m in messages:
            for b in m.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if "toolUse" in b:
                    tu = b["toolUse"]
                    step = {
                        "tool": tu.get("name"),
                        "input": {k: scrub(v) for k, v in (tu.get("input") or {}).items() if k != "job_id"},
                    }
                    by_id[tu.get("toolUseId", "")] = step
                    steps.append(step)
                elif "toolResult" in b:
                    r = b["toolResult"]
                    step = by_id.get(r.get("toolUseId", ""))
                    if step is None:
                        continue
                    text = " ".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
                    step["status"] = r.get("status")
                    step["result"] = scrub(text)[:600]
                    err = r.get("status") == "error"
                    step["refused_by_gate"] = bool(err and text.startswith("Blocked"))
                    step["stopped_by_turn_budget"] = bool(err and text.startswith("Stopped: this turn"))
                    if step["tool"] in PHOTO_TOOLS and cv_rows:
                        row = cv_rows.pop(0)
                        step["opencv"] = {
                            "decision": row.get("decision"),
                            "route": row.get("route"),
                            "ms_total": row.get("ms_total"),
                            "llm_called": row.get("llm_called"),
                            "reason": scrub(row.get("reason")),
                            "instruction": scrub(row.get("instruction")) if row.get("instruction") else None,
                            "images": [
                                {"kind": k, "url": f"/api/jobs/{job_id}/perception/{ref}"}
                                for k in ("match", "heatmap", "quality")
                                if job_id and (ref := _ref(row.get(f"img_{k}")))
                            ],
                        }
        return steps

    # -- the three kinds of turn ------------------------------------------------------
    def start(self, task: str, photo_path: str) -> dict[str, Any]:
        sid = uuid.uuid4().hex[:16]
        message = (
            f"{task}\n\nHere is my photo of it: {photo_path}. Please start the job and show me the first step."
        )
        out = self.run(sid, message, {"text": task, "photo": True})
        self._settle_start_photo(out.get("job_id"), photo_path)
        return out

    def photo(self, sid: str, text: str, photo_path: str) -> dict[str, Any]:
        said = text.strip() or "Here is my photo."
        return self.run(sid, f"{said}\n\n[The person attached a photo: {photo_path}]", {"text": said, "photo": True})

    def say_text(self, sid: str, text: str) -> dict[str, Any]:
        return self.run(sid, text, {"text": text, "photo": False})

    def _settle_start_photo(self, job_id: str | None, photo_path: str) -> None:
        """Move the start photo in beside the job, as the code-driven page does."""
        state = self.service.get(job_id) if job_id else None
        if state is None or state.start_photo != photo_path:
            return
        home = store.cards_dir(state.job_id) / "start.jpg"
        try:
            Path(photo_path).replace(home)
            state.start_photo = str(home)
            self.service.put(state)
        except OSError:
            pass
