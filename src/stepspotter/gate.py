"""The gate — the one thing in StepSpotter that a prompt cannot talk around.

``advance_step`` is cancelled in code unless the CURRENT step already has a passing
verdict from the verifier. The block is a Strands ``BeforeToolCall`` hook setting
``event.cancel_tool = "<reason>"``; Strands turns that into an error tool result, so
the model reads the refusal and relays it to the person in their own words.

Ported from spike B (tests/test_gate.py, 6/6 green offline, plus a live Bedrock run
where the model did call advance_step, was cancelled, and read the reason out).

Two escalation shapes, and they are not interchangeable:
    cancel_tool  -> this one tool call fails, the conversation carries on.
                    "You have not proven this step yet."
    interrupt    -> the whole run stops and waits for a person.
                    "The battery is hot and swollen."
A hazard must never be a cancel: a cancel lets the agent keep chatting past it.

The OpenCV layer (``perception/``) adds two things here, read from
``state.perception[current]`` — the report on the latest photo for this step:

* ``touched_avoid`` (something changed in a do-not-touch zone) raises
  ``interrupt("human_review")`` — a request for a person's approval, not a cancel. When
  the run resumes with the person's answer, ``on_review`` records it.
* any other blocking decision cancels ``advance_step`` with OpenCV's reason, even if a
  passing verdict somehow sits beside it (defence in depth: in the normal path a
  photo OpenCV refuses never gets a passing verdict, because the model is never asked).
* ``place_unconfirmed`` (route ``llm_two_image``) allows advancing only on a verdict whose
  two-photo check answered ``same_place=true``.
"""

from __future__ import annotations

from typing import Any, Callable

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from stepspotter.models import JobState

GATED_TOOLS = ("advance_step",)


class StepGate(HookProvider):
    """Cancels advance_step unless the current step has a passing verdict.

    ``state_for`` resolves the live JobState for a job id, so the gate reads the
    same state the tools just wrote rather than a stale copy captured at wiring time.
    """

    def __init__(
        self,
        state_for: Callable[[str | None], JobState | None],
        on_block: Callable[[str, dict], None] | None = None,
        on_review: Callable[[JobState, Any], bool] | None = None,
    ) -> None:
        self.state_for = state_for
        self.on_block = on_block
        self.on_review = on_review
        self.blocks: list[str] = []  # audit trail of every refusal, in order

    # -- SDK wiring ---------------------------------------------------------
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before_tool_call)

    def before_tool_call(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use.get("name") not in GATED_TOOLS:
            return
        tool_input = event.tool_use.get("input") or {}
        state = self.state_for(tool_input.get("job_id"))

        if state is None:
            reason = "Blocked: I cannot find that job, so I will not move anyone forward."
            self._block(event, reason, tool_input)
            return

        hazard = self.hazard(state)
        if hazard is not None:
            # A hazard stops the run for a person. It is not a failed step.
            event.interrupt(
                name="stop_condition",
                reason={
                    "message": hazard,
                    "needs": "a human answer before anything else happens",
                },
            )
            return

        review = self.human_review(state)
        if review is not None:
            # A request for human approval. First pass: InterruptException, the run stops.
            # On resume with the person's answer, interrupt() returns it here.
            answer = event.interrupt(
                name="human_review",
                reason={
                    "message": review,
                    "needs": "a person to look at the do-not-touch zone and approve going on",
                    "source": "opencv",
                },
            )
            approved = bool(self.on_review(state, answer)) if self.on_review else False
            self._block(
                event,
                ("A person approved the change. " if approved else "A person was asked to check it. ")
                + "Send a new photo of the finished step before moving on.",
                tool_input,
            )
            return

        reason = self.check(state, tool_input)
        if reason is None:
            reason = self.perception_block(state)
        if reason is not None:
            self._block(event, reason, tool_input)

    def _block(self, event: BeforeToolCallEvent, reason: str, tool_input: dict) -> None:
        self.blocks.append(reason)
        if self.on_block:
            self.on_block(reason, tool_input)
        event.cancel_tool = reason  # <- the whole mechanic, one settable field

    # -- policy -------------------------------------------------------------
    def hazard(self, state: JobState) -> str | None:
        """A stop flag on the current step's verdict outranks everything else."""
        verdict = state.verdicts.get(state.current)
        if verdict is not None and verdict.stop:
            return (
                f"STOP: the photo for step {state.current + 1} shows something unsafe. "
                f"{verdict.reason} Do not carry on. A person needs to look at this."
            )
        return None

    def human_review(self, state: JobState) -> str | None:
        """OpenCV saw a change where this step said not to touch: a person decides."""
        rep = state.perception.get(state.current)
        if rep is not None and rep.needs_human and not rep.overridden:
            return (
                f"HOLD for a person: on step {state.current + 1}, {rep.reason} "
                "Someone needs to check it and approve before this job goes on."
            )
        return None

    def perception_block(self, state: JobState) -> str | None:
        """The stored OpenCV report still blocks this step, whatever else says.

        And when OpenCV could not confirm the place (route llm_two_image), a pass counts
        only if the model's two-photo check said ``same_place=true``.
        """
        rep = state.perception.get(state.current)
        if rep is not None and rep.blocks and not rep.needs_human:
            return (
                f"Blocked by the photo check (OpenCV, {rep.decision}): {rep.reason} "
                f"{rep.instruction or ''}".strip()
            )
        if rep is not None and rep.route == "llm_two_image":
            verdict = state.verdicts.get(state.current)
            if verdict is None or verdict.same_place is not True:
                return (
                    "Blocked: OpenCV could not line this photo up with your first photo, and "
                    "the two-photo check did not confirm it is the same place. Send a photo "
                    "of the place in your first photo."
                )
        return None

    def check(self, state: JobState, tool_input: dict) -> str | None:
        """Return the refusal a person should hear, or None if advancing is allowed."""
        if state.done:
            return "Blocked: this job is already finished, there is no next step."

        step = state.current_step()
        name = step.title if step else f"step {state.current + 1}"

        asked = tool_input.get("step_id")
        if asked is not None:
            try:
                asked_i = int(asked)
            except (TypeError, ValueError):
                asked_i = -1
            # step_id is 1-based on the wire, current is 0-based inside.
            if asked_i != state.current + 1:
                return (
                    f"Blocked: you are on step {state.current + 1} ({name}), but that asks to "
                    f"close step {asked_i}. A pass on one step does not unlock another one."
                )

        verdict = state.verdicts.get(state.current)
        if verdict is None:
            return (
                f"Blocked: I have not checked step {state.current + 1} ({name}) yet. "
                "Send a photo of the finished step and I will look at it first."
            )
        if not verdict.passed:
            return (
                f"Blocked: step {state.current + 1} ({name}) did not pass the check. "
                f"{verdict.reason} Fix that, send a new photo, and we will move on."
            )
        return None


def escalate_stop_condition(event: BeforeToolCallEvent, message: str) -> Any:
    """Turn a hazard into a human question from inside any hook callback.

    First pass raises ``InterruptException`` (the run ends with stop_reason
    'interrupt'); once the caller resumes with the human's answer, the same call
    returns that answer. ``name`` must be unique per callback — the interrupt id is
    derived from it.
    """
    return event.interrupt(
        name="stop_condition",
        reason={"message": message, "needs": "a human answer before anything else happens"},
    )
