"""The chat transcript, rebuilt on the server from the job's own trace.

Form A (the chat master) shows a message feed instead of a screen stack. The feed is
NOT held in the browser: it is derived, every time, from ``data/jobs/<id>.trace.jsonl``
plus the current ``JobState``. Two reasons, both learned from a phone in a garage:

1. A phone locks, the tab is killed, the person comes back an hour later. ``?job=<id>``
   restores the whole conversation because the conversation was never client state.
2. The trace is already the audit record behind the "why did it say that" link. If the
   feed were a second, separate list of messages, the two could disagree — and the one
   the judge reads would be the one that is not the record.

So there is exactly one source of truth and the feed is a projection of it. A message
here can never claim something the trace does not hold.

Ordering rule: trace rows are appended in the order things happened, so the feed is
that order, with one exception — the step card for step N is emitted from the ``plan``
row (step 1) and from each ``advance`` row (step N+1), never from the ``card`` row,
because a card is only drawn when someone looks at it and the step exists before that.
"""

from __future__ import annotations

from typing import Any

from stepspotter.models import JobState, Step


def _legend(state: JobState, step_no: int) -> list[dict[str, Any]]:
    """The numbered badges drawn on the photo, as text the page can print.

    Numbering and colour follow marker._draw_boxes_on_photo exactly: badges are
    numbered in list order from 1, coloured by kind. If these two ever disagree, the
    photo says "look at 2" and the words describe something else.
    """
    boxes = state.box_sets.get(step_no - 1) or []
    return [
        {"n": i, "label": b.label, "kind": b.kind}
        for i, b in enumerate(boxes, start=1)
    ]


def _step_msg(state: JobState, step: Step, step_no: int) -> dict[str, Any]:
    """One step, in the card format of the reference sheet: photo, one action,
    what not to touch, the stop condition, and what the next photo must show."""
    return {
        "legend": _legend(state, step_no),
        "from": "agent",
        "kind": "step",
        "step_number": step_no,
        "total": state.total,
        "title": step.title,
        "action": step.action,
        "do_not_touch": list(step.do_not_touch),
        "stop_condition": step.stop_condition,
        "evidence_required": step.evidence_required,
        "source": step.source,
        "card_url": f"/api/jobs/{state.job_id}/card/{step_no}",
    }


#: What each OpenCV decision is called in the feed's heading.
CV_HEADINGS = {
    "ok": "Photo check passed — sent on to the model",
    "retake": "Photo check: please retake it",
    "wrong_place": "Photo check: this is not the place in your first photo",
    "replay": "Photo check: this photo was already sent",
    "no_change": "Photo check: nothing changed at the work zone yet",
    "touched_avoid": "Photo check: something changed where you were told not to touch",
    "skipped": "Photo check could not read the photo — the model decides",
}


def _ref(path: object) -> str | None:
    """A rendered picture's name without folder or extension, as the URL route wants it."""
    if not isinstance(path, str) or not path:
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".jpg") else name


def _cv_msg(state: JobState, row: dict) -> dict[str, Any]:
    """One OpenCV check, as a chat message: decision, why, the one instruction, pictures."""
    images = []
    for kind in ("match", "heatmap", "quality"):
        ref = _ref(row.get(f"img_{kind}"))
        if ref:
            images.append({"kind": kind, "url": f"/api/jobs/{state.job_id}/perception/{ref}"})
    return {
        "from": "cv",
        "kind": "perception",
        "decision": row.get("decision"),
        "heading": CV_HEADINGS.get(row.get("decision") or "", "Photo check"),
        "reason": row.get("reason") or "",
        "instruction": row.get("instruction"),
        "blocks": bool(row.get("blocks")),
        "needs_human": bool(row.get("needs_human")),
        "overridden": bool(row.get("overridden")),
        "llm_called": bool(row.get("llm_called")),
        "ms_total": row.get("ms_total"),
        "step_number": row.get("step_id"),
        "images": images,
    }


def build_feed(state: JobState, rows: list[dict]) -> list[dict]:
    """Turn one job's trace into the messages a person sees, oldest first."""
    feed: list[dict] = []
    add = feed.append
    plan = state.plan
    #: How many photos this step has already been judged on. The nth verdict row for
    #: a step is the nth photo sent for it, and web/app.py files it under that same
    #: number — so each bubble gets an address of its own instead of every attempt at
    #: a step sharing one, which a browser answers from cache with the older picture.
    attempts: dict[int, int] = {}
    #: The OpenCV row waiting for its verdict row: the photo bubble comes first, then
    #: what OpenCV saw, then the verdict — the order a person reads the story in.
    pending_cv: dict | None = None

    for row in rows:
        event = row.get("event")

        if event == "start_job":
            add({"from": "you", "kind": "task", "text": row.get("task", "")})
            add(
                {
                    "from": "you",
                    "kind": "photo",
                    "url": f"/api/jobs/{state.job_id}/start-photo",
                    "caption": "the thing I am looking at",
                }
            )

        elif event == "house_recall":
            context = (row.get("context") or "").strip()
            if context:
                add(
                    {
                        "from": "agent",
                        "kind": "note",
                        "icon": "memory",
                        "text": f"I remembered about this house: {context}",
                    }
                )

        elif event == "research":
            if row.get("status") == "found":
                pages = row.get("pages") or []
                where = f", pages {pages[0]}–{pages[-1]}" if pages else ""
                add(
                    {
                        "from": "agent",
                        "kind": "note",
                        "icon": "manual",
                        "text": f"I found the manual for {row.get('product') or 'it'}{where}. "
                        "The steps below follow it.",
                        "url": row.get("manual_url"),
                    }
                )

        elif event == "plan":
            if row.get("safety_class") == "vendor_required":
                add(
                    {
                        "from": "agent",
                        "kind": "vendor",
                        "title": plan.job_title,
                        "reason": row.get("vendor_reason") or plan.vendor_reason or "",
                    }
                )
                continue
            add(
                {
                    "from": "agent",
                    "kind": "plan",
                    "title": plan.job_title,
                    "total": state.total,
                    "tools_needed": list(plan.tools_needed),
                    "text": f"{plan.job_title} — {state.total} steps. "
                    "I will give you one at a time. The next one opens only when a "
                    "photo shows the last one is done.",
                }
            )
            first = plan.step(0)
            if first is not None:
                add(_step_msg(state, first, 1))

        elif event == "perception":
            if row.get("mode") == "submit":
                pending_cv = row

        elif event == "judge":
            add(
                {
                    "from": "agent",
                    "kind": "note",
                    "icon": "judge",
                    "text": "Judge scenario: the plan is fixed, the zones were placed by hand, "
                    f"and the photo below is {row.get('evidence') or 'generated'}. Everything "
                    "after this is the real OpenCV check and the real gate; no model is called.",
                }
            )

        elif event == "verdict":
            step_no = int(row.get("step_id") or 0)
            attempt = attempts[step_no] = attempts.get(step_no, 0) + 1
            add(
                {
                    "from": "you",
                    "kind": "photo",
                    "url": f"/api/jobs/{state.job_id}/evidence/{step_no}?attempt={attempt}",
                    "caption": "I did it",
                }
            )
            cv = pending_cv if (pending_cv and int(pending_cv.get("step_id") or 0) == step_no) else None
            pending_cv = None
            if cv is not None:
                add(_cv_msg(state, cv))
            if row.get("source") == "opencv" and cv is not None:
                # The OpenCV message above IS the refusal; a second bubble saying the same
                # thing in red would make one decision look like two. The way past it
                # (move on anyway, which the gate then refuses) is drawn on that message.
                feed[-1]["final"] = True
                continue
            add(
                {
                    "from": "agent",
                    "kind": "verdict",
                    "passed": bool(row.get("passed")),
                    "stop": bool(row.get("stop")),
                    "reason": row.get("reason") or "",
                    "step_number": step_no,
                }
            )

        elif event == "keyframes":
            add(
                {
                    "from": "cv",
                    "kind": "note",
                    "icon": "video",
                    "text": f"I picked frame {row.get('chosen_index')} ({row.get('chosen_time_s')} s) "
                    "out of your video: the sharpest one that shows the right place.",
                }
            )

        elif event == "human_review":
            approved = bool(row.get("approved"))
            add(
                {
                    "from": "agent",
                    "kind": "note",
                    "icon": "person",
                    "text": ("A person checked it and approved carrying on"
                             if approved else "A person checked it and did not approve")
                    + (f": \u201c{row.get('answer')}\u201d" if row.get("answer") else "")
                    + ". The step still needs a photo that shows it done.",
                }
            )

        elif event == "gate_block":
            add(
                {
                    "from": "agent",
                    "kind": "block",
                    "hazard": False,
                    "reason": row.get("reason") or "",
                }
            )

        elif event == "gate_stop":
            add(
                {
                    "from": "agent",
                    "kind": "block",
                    "hazard": True,
                    "review": row.get("kind") == "human_review",
                    "reason": row.get("reason") or "",
                }
            )

        elif event == "advance":
            to_step = int(row.get("to_step") or 0)
            step = plan.step(to_step - 1)
            if step is not None:
                add(_step_msg(state, step, to_step))
            else:
                add(
                    {
                        "from": "agent",
                        "kind": "done",
                        "total": state.total,
                        "text": f"That is all {state.total} steps of {plan.job_title}. "
                        "Every one of them was proven by a photo before it closed.",
                    }
                )

        elif event == "escalate":
            add(
                {
                    "from": "agent",
                    "kind": "stopped",
                    "reason": row.get("reason") or "",
                }
            )

        elif event == "ask":
            add({"from": "you", "kind": "text", "text": row.get("question") or ""})

        elif event == "answer":
            add({"from": "agent", "kind": "text", "text": row.get("text") or ""})

    for i, message in enumerate(feed):
        message["id"] = f"m{i}"
    return feed


def review_pending(state: JobState, rows: list[dict]) -> bool:
    """Has the gate stopped this step for a person who has not answered yet?"""
    if state.current in state.approvals:
        return False
    step_no = state.current + 1
    stopped = answered = False
    for r in rows:
        if r.get("event") == "gate_stop" and r.get("kind") == "human_review":
            stopped = True
            answered = False
        elif r.get("event") == "human_review" and int(r.get("step_id") or 0) == step_no:
            answered = True
    rep = state.perception.get(state.current)
    return stopped and not answered and rep is not None and rep.needs_human and not rep.overridden


def composer_state(state: JobState, escalated: bool, pending_review: bool = False) -> dict[str, Any]:
    """What the one action button at the bottom should be right now.

    One action per screen, on purpose: on a phone, standing in front of an open panel,
    a choice between four buttons is a choice the person did not ask for.
    """
    if not state.plan.is_diy:
        return {"action": "restart", "label": "Start something else", "can_ask": False}
    if escalated:
        return {"action": "restart", "label": "Start something else", "can_ask": True}
    if state.done:
        return {"action": "restart", "label": "Start another job", "can_ask": True}
    verdict = state.verdicts.get(state.current)
    rep = state.perception.get(state.current)
    if verdict is not None and verdict.source == "opencv" and rep is not None:
        if rep.needs_human and not rep.overridden:
            if pending_review:
                # The gate has already stopped for a person; the one action left is theirs.
                return {"action": "approve", "label": "I am the person: I checked it, carry on",
                        "can_ask": True, "hint": "Nothing moves until a person approves the change."}
            # Through the gate on purpose: it stops the run and asks a person.
            return {"action": "advance", "label": "Ask a person to check it", "can_ask": True,
                    "hint": "The gate stops the job here until a person checks it."}
        if rep.needs_human:  # a person approved the change; the step still needs its photo
            return {"action": "photo", "label": "Take a new photo", "can_ask": True,
                    "hint": "A person approved the change. Now send a photo that shows the step done."}
        return {"action": "photo", "label": "Take a new photo", "can_ask": True,
                "hint": rep.instruction or ""}
    if verdict is not None and verdict.passed and not verdict.stop:
        return {"action": "advance", "label": "Next step", "can_ask": True}
    if verdict is not None and verdict.stop:
        return {"action": "escalate", "label": "Stop — get a person", "can_ask": True}
    if verdict is not None:
        return {"action": "photo", "label": "Try again — take photo", "can_ask": True}
    return {"action": "photo", "label": "I did it — take photo", "can_ask": True}
