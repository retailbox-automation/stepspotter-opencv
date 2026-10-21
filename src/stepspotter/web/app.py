"""FastAPI app: one page, one step at a time, from a phone.

Endpoints (all JSON except the two image routes and ``/``):

    GET  /  (and /chat)             form A: the chat master, the default face
    GET  /steps (and /jobs)         form B: the screen-stack UI, one HTML file
    GET  /healthz                   liveness for App Runner / a container HEALTHCHECK
    GET  /api/demo                  is the no-camera demo installed, and what does it say
    POST /api/demo/jobs             start the demo job on a photo shipped in the package
    POST /api/jobs                  multipart: task + photo  -> plan or vendor refusal
    GET  /api/jobs/{id}             where the job is right now
    GET  /api/jobs/{id}/card        the rendered card image for the current step
    POST /api/jobs/{id}/photo       multipart: photo         -> verifier verdict
    POST /api/jobs/{id}/demo-photo  the same, on a packaged photo instead of a camera
    POST /api/jobs/{id}/advance     GATED, through the Strands hook (see gated.py)
                                    intent=skip marks an ask with no photo behind it
    POST /api/jobs/{id}/escalate    stop and hand to a person
    GET  /api/jobs/{id}/evidence/N  the photo the person sent for step N
                                    (?attempt=K for one try at it; the latest by default)
    GET  /api/jobs/{id}/start-photo the photo the job was opened with
    GET  /api/jobs/{id}/card/N      the card for step N (cached; the current step renders)
    GET  /api/jobs/{id}/feed        the chat transcript, rebuilt from the trace
    POST /api/jobs/{id}/ask         a typed question -> the Guide, with no tools at all
    GET  /api/jobs/{id}/trace       every tool call and refusal, in order
                                    (?view=human for the readable one, ?view=raw for rows)
    GET  /api/jobs/{id}/perception/R one picture of what OpenCV saw (match / heatmap /
                                    quality), R as named in the feed and the trace
    POST /api/jobs/{id}/review      a person checked a do-not-touch change: approve or not
    POST /api/inspect               OpenCV only, no model: reference + evidence (+ zones)
                                    -> the PerceptionReport and its three pictures
    GET  /api/inspect/{rid}/{kind}  one of those pictures
    GET  /agent                     agent mode: the Guide agent decides the tool calls
    POST /api/agent/start           task + photo -> the agent starts the job (a job slot)
    POST /api/agent/{sid}/photo     text + photo -> one agent turn (a photo slot)
    POST /api/agent/{sid}/say       text only    -> one agent turn (an agent-turn slot)
    GET  /api/agent/{sid}           the session's turns, for a reload
    GET  /api/judge                 the OpenCV-only scenarios a judge can run
    POST /api/judge/{name}          run one: a real job, the real gate, no model call

Nothing here holds state of its own: the job lives in ``data/jobs/<id>.json`` and
everything that happened is appended to ``data/jobs/<id>.trace.jsonl`` by the store.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from stepspotter import store
from stepspotter.bedrock_client import is_model_busy
from stepspotter.gate import StepGate
from stepspotter.guide import JobService, build_tools
from stepspotter.models import JobState
from stepspotter.web import demo as demo_mod
from stepspotter.web import judge as judge_mod
from stepspotter.web.agent_mode import SESSION_RE, AgentMode
from stepspotter.web.agent_page import AGENT_HTML
from stepspotter.web.ask import answer as answer_question
from stepspotter.web.chat_page import CHAT_HTML
from stepspotter.web.feed import build_feed, composer_state, review_pending
from stepspotter.web.gated import advance_via_gate, escalate_via_tool
from stepspotter.web.limits import install_limits
from stepspotter.web.page import PAGE_HTML
from stepspotter.web.photos import save_upload
from stepspotter.web.trace_view import humanize, scrub


def _escalated(job_id: str) -> bool:
    """A job is in a person's hands once an escalate event is on its trace."""
    return any(r.get("event") == "escalate" for r in store.read_trace(job_id))


def _is_demo(job_id: str) -> bool:
    """Was this job started from the demo button?

    Read off the trace rather than stored on the job, so ``JobState`` keeps the same
    shape on disk and a job saved before this existed still loads.
    """
    return any(r.get("event") == "demo" for r in store.read_trace(job_id))


def _evidence_name(step_no: int, attempt: int) -> str:
    """The photo sent on one try at one step. Numbered, because a step is usually
    tried twice: the photo that does not prove it, then the one that does. Writing
    both to ``evidence-NN.jpg`` destroyed the first as soon as the second arrived,
    so the feed showed the refused photo above the green verdict it had nothing to
    do with — the browser still had it cached at that one address."""
    return f"evidence-{step_no:02d}-{attempt:02d}.jpg"


def _evidence_attempts(job_id: str, step_no: int) -> int:
    """How many photos have already been judged for this step.

    Counted off the trace, not off the disk: the feed numbers the bubbles the same
    way (one per ``verdict`` row, in order), so the two cannot drift apart. A photo
    whose verdict never came back — the checker raised — leaves no row and is
    overwritten by the next try, which is right: nothing in the feed points at it.
    """
    return sum(
        1
        for r in store.read_trace(job_id)
        if r.get("event") == "verdict" and int(r.get("step_id") or 0) == step_no
    )


def _evidence_file(job_id: str, step_no: int, attempt: int | None) -> Path | None:
    """The photo for one attempt, or the most recent one when none is named.

    Jobs written before attempts were numbered hold a single ``evidence-NN.jpg``;
    it answers as attempt 1, so a link a judge already has still shows its photo.
    """
    folder = store.cards_dir(job_id)
    legacy = folder / f"evidence-{step_no:02d}.jpg"
    if attempt is not None:
        numbered = folder / _evidence_name(step_no, attempt)
        if numbered.is_file():
            return numbered
        return legacy if attempt == 1 and legacy.is_file() else None
    numbered_files = sorted(folder.glob(f"evidence-{step_no:02d}-[0-9][0-9].jpg"))
    if numbered_files:
        return numbered_files[-1]
    return legacy if legacy.is_file() else None


def _research(job_id: str) -> dict | None:
    """What the Researcher found, and where, off the job's trace.

    On screen this becomes one line under the manual link — "from the copy baked into
    the image", "a Brave search (DuckDuckGo did not answer)", or, when nothing was
    found, the list of what was tried. A plan written without the manual must not look
    on the page like a plan written with it.
    """
    for row in store.read_trace(job_id):
        if row.get("event") != "research":
            continue
        return {
            "status": row.get("status"),
            "source": row.get("source"),
            "source_words": row.get("source_words"),
            "manual_url": row.get("manual_url"),
            "pages": list(row.get("pages") or []),
            "trail": list(row.get("trail") or []),
        }
    return None


#: A rendered OpenCV picture, as the feed and the trace name it: no extension, no path.
PERCEPTION_REF = re.compile(r"^step-\d{2}-(?:try|probe)-\d{2}-(?:match|heatmap|quality)$")
INSPECT_KIND = re.compile(r"^(?:match|heatmap|quality)$")


def _perception_dict(state: JobState) -> dict | None:
    """What OpenCV said about the latest photo for the current step, for the page."""
    rep = state.perception.get(state.current)
    if rep is None:
        return None
    return {
        "decision": rep.decision,
        "reason_code": rep.reason_code,
        "reason": rep.reason,
        "instruction": rep.instruction,
        "blocks": rep.blocks,
        "needs_human": rep.needs_human,
        "overridden": rep.overridden,
        "ms_total": rep.ms_total,
        "route": rep.route,
        "approved": state.current in state.approvals,
    }


def _step_dict(state: JobState) -> dict | None:
    step = state.current_step()
    if step is None:
        return None
    return {
        "id": step.id,
        "title": step.title,
        "action": step.action,
        "do_not_touch": list(step.do_not_touch),
        "stop_condition": step.stop_condition,
        "evidence_required": step.evidence_required,
        "source": step.source,
    }


def _summary(state: JobState) -> dict:
    plan = state.plan
    verdict = state.verdicts.get(state.current)
    step = state.current_step()
    return {
        "job_id": state.job_id,
        "task": state.task,
        "job_title": plan.job_title,
        "safety_class": plan.safety_class,
        "vendor_reason": plan.vendor_reason,
        "tools_needed": list(plan.tools_needed),
        "sources": list(plan.sources),
        "total": state.total,
        "step_number": None if step is None else state.current + 1,
        "done": state.done,
        "escalated": _escalated(state.job_id),
        "demo": _is_demo(state.job_id),
        "research": _research(state.job_id),
        "step": _step_dict(state),
        "verdict": None
        if verdict is None
        else {
            "passed": verdict.passed,
            "stop": verdict.stop,
            "reason": verdict.reason,
            "source": verdict.source,
            "evidence_url": f"/api/jobs/{state.job_id}/evidence/{state.current + 1}",
        },
        "perception": _perception_dict(state),
        "llm_calls_saved": state.llm_calls_saved,
        "card_url": None
        if step is None
        else f"/api/jobs/{state.job_id}/card?step={state.current + 1}",
    }


def create_app(
    service: JobService | None = None,
    answer_fn: Callable[[JobState, str], str] | None = None,
    agent_model_fn: Callable[[], Any] | None = None,
) -> FastAPI:
    """Build the app. Pass a ``JobService`` with fake model functions to run offline.

    ``answer_fn(state, question) -> str`` overrides who answers a question typed into
    the chat feed; the default is the Guide on Bedrock (``web.ask.guide_answer``).
    """
    app = FastAPI(title="StepSpotter", docs_url=None, redoc_url=None)
    svc = service or JobService()
    tools = build_tools(svc)
    gate = StepGate(
        state_for=svc.get,
        on_block=lambda reason, ti: store.trace(
            ti.get("job_id") or "unknown", "gate_block", reason=reason, tool_input=ti
        ),
    )
    # Public URL, no login, 23 days of judging: cap what one address and one day can
    # spend on Bedrock, and keep a kill switch. See web/limits.py.
    install_limits(app)
    app.state.service = svc
    app.state.gate = gate
    app.state.tools = tools
    agent_mode = AgentMode(svc, model_factory=agent_model_fn)

    def _job(job_id: str) -> JobState:
        state = svc.get(job_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"No job {job_id}.")
        return state

    # ---------------------------------------------------------------- pages
    # Two faces on one server. They share every endpoint below, the same gate and the
    # same trace; only the arrangement of the screen differs. Form A is what a phone
    # lands on, because the way this product is actually used is a conversation.
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Form A — the chat master. The default face."""
        return CHAT_HTML

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page() -> str:
        """Form A again, at the path it was prototyped on, so old links still open it."""
        return CHAT_HTML

    @app.get("/steps", response_class=HTMLResponse)
    def steps_page() -> str:
        """Form B — the screen stack. Kept whole, at its own path, for the comparison."""
        return PAGE_HTML

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page() -> str:
        """Form B again, under the name the screen stack is usually called by."""
        return PAGE_HTML

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "service": "stepspotter"}

    # ---------------------------------------------------------------- model failures
    def _model_failure(exc: Exception, fault: str, busy_after: str) -> HTTPException:
        """Bedrock busy or throttling even after the client's retries (bedrock_client) is a
        503 the person can act on — "try again in a minute" — not a 502 with the error text."""
        if is_model_busy(exc):
            return HTTPException(
                status_code=503,
                detail=f"The model is busy right now. Try again in a minute; {busy_after}",
                headers={"Retry-After": "60"},
            )
        return HTTPException(status_code=502, detail=f"{fault}: {scrub(str(exc))[:300]}")

    # ---------------------------------------------------------------- jobs
    def _start_job(task: str, raw: bytes) -> JobState:
        """Plan one job from a task and photo bytes. The only path into the Planner.

        The camera and the demo button both end up here, so a demo cannot quietly
        become a different code path than the one a phone takes.
        """
        if not raw:
            raise HTTPException(status_code=400, detail="That photo did not arrive. Try again.")
        if not task.strip():
            raise HTTPException(status_code=400, detail="Say what you want to do first.")
        # The photo is written before the job exists, so it needs its own resting place.
        tmp_dir = store.jobs_dir() / "_uploads"
        tmp = save_upload(raw, tmp_dir / f"start-{abs(hash(raw)) % 10**10}.jpg")
        try:
            state = svc.start(task.strip(), str(tmp))
        except Exception as exc:  # noqa: BLE001 - a model failure is a user-facing message
            raise _model_failure(exc, "The planner could not answer", "no job was started.")
        # Move the start photo in beside the job, so a job folder is self-contained.
        home = store.cards_dir(state.job_id) / "start.jpg"
        try:
            tmp.replace(home)
            state.start_photo = str(home)
            svc.put(state)
        except OSError:
            pass
        return state

    async def _verify_photo(job_id: str, raw: bytes) -> dict:
        """Check one photo against the current step. The only path into the Verifier."""
        state = _job(job_id)
        if state.done:
            raise HTTPException(status_code=409, detail="This job is already finished.")
        if not raw:
            raise HTTPException(status_code=400, detail="That photo did not arrive. Try again.")
        step_no = state.current + 1
        attempt = _evidence_attempts(job_id, step_no) + 1
        dest = save_upload(raw, store.cards_dir(job_id) / _evidence_name(step_no, attempt))
        try:
            verdict = svc.verify(state, str(dest))
        except Exception as exc:  # noqa: BLE001
            raise _model_failure(exc, "The checker could not answer", "this photo was not judged.")
        summary = _summary(state)
        return {"verdict": summary["verdict"], "job": summary, "raw_passed": verdict.passed}

    @app.post("/api/jobs")
    async def create_job(task: str = Form(...), photo: UploadFile = File(...)) -> dict:
        return _summary(_start_job(task, await photo.read()))

    # ---------------------------------------------------------------- demo
    @app.get("/api/demo")
    def demo_info() -> dict:
        """What the first screen needs to offer the demo — or to hide the button."""
        return demo_mod.info()

    @app.post("/api/demo/jobs")
    def demo_job() -> dict:
        """Start the demo job: a packaged photo, then the real Planner, same as a phone."""
        if not demo_mod.available():
            raise HTTPException(status_code=503, detail="The demo photos are not installed.")
        state = _start_job(demo_mod.DEMO_TASK, demo_mod.photo_bytes("start"))
        # Marks the job for the page (which swaps the camera for two buttons) and puts
        # the substitution on the record, so the trace never pretends a camera was used.
        store.trace(
            state.job_id,
            "demo",
            task=demo_mod.DEMO_TASK,
            photo_source="packaged demo photo, not a camera",
        )
        return _summary(state)

    @app.post("/api/jobs/{job_id}/demo-photo")
    async def demo_photo(job_id: str, which: str = Form(...)) -> dict:
        """Send one of the packaged photos to the real Verifier. No verdict is faked."""
        if which not in demo_mod.DEMO_BUTTONS:
            raise HTTPException(status_code=400, detail=f"There is no demo photo called {which!r}.")
        try:
            raw = demo_mod.photo_bytes(which)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return await _verify_photo(job_id, raw)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        return _summary(_job(job_id))

    @app.get("/api/jobs/{job_id}/card")
    def get_card(job_id: str) -> Any:
        """The current step drawn on the person's own photo. Rendered once, then cached."""
        state = _job(job_id)
        if state.current_step() is None:
            raise HTTPException(status_code=404, detail="This job has no step in progress.")
        cached = state.card_paths.get(state.current)
        if cached and Path(cached).is_file():
            return FileResponse(cached, media_type="image/jpeg")
        try:
            path, _boxes = svc.card(state, layout="photo")
        except Exception as exc:  # noqa: BLE001
            raise _model_failure(exc, "Could not draw the card", "the step text above still stands.")
        return FileResponse(str(path), media_type="image/jpeg")

    @app.post("/api/jobs/{job_id}/photo")
    async def submit_photo(job_id: str, photo: UploadFile = File(...)) -> dict:
        return await _verify_photo(job_id, await photo.read())

    @app.post("/api/jobs/{job_id}/advance")
    def advance(job_id: str, intent: str = Form("next")) -> JSONResponse:
        """Ask to move on. The gate hook decides, exactly as it does for the agent.

        ``intent`` changes nothing about the decision — the gate never sees it. It
        records WHY the ask happened, so the trace can tell "the photo passed and they
        pressed Next" apart from "they pressed 'I did it' and sent no photo at all".
        The page's skip button sends ``intent=skip``; that button exists so the refusal
        is reachable from a browser, which until now it was not: with no passing photo
        the Next button is simply hidden, and the one mechanic this project is built on
        never appeared on screen.
        """
        state = _job(job_id)
        if intent == "skip":
            store.trace(
                job_id,
                "skip_attempt",
                step_id=state.current + 1,
                asked="move on without sending a photo",
            )
        res = advance_via_gate(gate, tools, job_id, state.current + 1)
        content = res.get("content")
        if res.get("cancelled"):
            if res.get("status") == "interrupt":
                message = (
                    content.get("message")
                    if isinstance(content, dict)
                    else str(content)
                )
                # The cancel path traces itself through the gate's on_block. The hazard
                # path raises an interrupt instead and traced nothing, so a reloaded
                # feed lost the one refusal that matters most. Record it here.
                review = isinstance(content, dict) and content.get("source") == "opencv"
                kind = "human_review" if review else "stop_condition"
                store.trace(job_id, "gate_stop", reason=message, kind=kind)
                blocked = {"blocked": True, "hazard": True, "human_review": review, "reason": message}
            else:
                blocked = {"blocked": True, "hazard": False, "reason": str(content)}
            blocked["job"] = _summary(_job(job_id))
            return JSONResponse(blocked, status_code=200)
        fresh = _job(job_id)
        return JSONResponse(
            {"blocked": False, "hazard": False, "message": str(content), "job": _summary(fresh)}
        )

    @app.post("/api/jobs/{job_id}/escalate")
    def escalate(job_id: str, reason: str = Form("The person pressed Stop.")) -> dict:
        _job(job_id)
        res = escalate_via_tool(tools, job_id, reason)
        return {"escalated": True, "message": str(res.get("content")), "job": _summary(_job(job_id))}

    @app.get("/api/jobs/{job_id}/evidence/{step_no}")
    def evidence(job_id: str, step_no: int, attempt: int | None = None) -> Any:
        """One try at one step. The feed asks for a numbered attempt, so every bubble
        has an address of its own and the browser cannot serve an older photo for a
        newer verdict. Without ``attempt`` this is the latest, which is what the
        verdict panel on form B wants."""
        _job(job_id)
        p = _evidence_file(job_id, step_no, attempt)
        if p is None:
            raise HTTPException(status_code=404, detail="No photo for that step yet.")
        return FileResponse(str(p), media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/start-photo")
    def start_photo(job_id: str) -> Any:
        """The photo the job was opened with — the first thing in the chat feed."""
        state = _job(job_id)
        p = Path(state.start_photo)
        if not p.is_file():
            raise HTTPException(status_code=404, detail="That photo is no longer on disk.")
        return FileResponse(str(p), media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/card/{step_no}")
    def card_for_step(job_id: str, step_no: int) -> Any:
        """The person's photo with this step's boxes on it, and nothing else.

        ``layout="photo"`` on purpose: the chat writes the title, the action, the
        do-not-touch list and the legend as real HTML, so baking the same sentences
        into the JPEG would print every step twice (see marker.render_marked_photo).
        A past step is served from the file drawn when it was live — re-rendering it
        would be a fresh model call for a picture the person already acted on.
        """
        state = _job(job_id)
        idx = step_no - 1
        marked = store.cards_dir(job_id) / f"step-{step_no:02d}-photo.jpg"
        if marked.is_file():
            return FileResponse(str(marked), media_type="image/jpeg")
        if idx != state.current or state.current_step() is None:
            raise HTTPException(status_code=404, detail="No card drawn for that step.")
        try:
            path, _boxes = svc.card(state, layout="photo")
        except Exception as exc:  # noqa: BLE001
            raise _model_failure(exc, "Could not draw the card", "the step text above still stands.")
        return FileResponse(str(path), media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/perception/{ref}")
    def perception_image(job_id: str, ref: str) -> Any:
        """One picture of what OpenCV saw. ``ref`` is the name the feed and trace use."""
        _job(job_id)
        if not PERCEPTION_REF.match(ref):
            raise HTTPException(status_code=404, detail="No such picture.")
        p = store.cards_dir(job_id) / "perception" / f"{ref}.jpg"
        if not p.is_file():
            raise HTTPException(status_code=404, detail="That picture is not on disk.")
        return FileResponse(str(p), media_type="image/jpeg")

    @app.post("/api/jobs/{job_id}/review")
    def review(job_id: str, approved: bool = Form(...), answer: str = Form("")) -> dict:
        """A person's answer to a human_review stop: the same call the gate makes on resume."""
        state = _job(job_id)
        rep = state.perception.get(state.current)
        if rep is None or rep.decision != "touched_avoid":
            raise HTTPException(status_code=409, detail="Nothing on this step is waiting for a person.")
        ok = svc.review(state, {"approved": approved, "answer": answer.strip() or ("approved" if approved else "not approved")})
        return {"approved": ok, "job": _summary(_job(job_id))}

    # ---------------------------------------------------------------- agent mode
    @app.get("/agent", response_class=HTMLResponse)
    def agent_page() -> str:
        return AGENT_HTML

    def _session_job(sid: str) -> str:
        if not SESSION_RE.match(sid) or not agent_mode.exists(sid):
            raise HTTPException(status_code=404, detail="No such agent session.")
        turns = agent_mode.history(sid)
        job_id = next((t.get("job_id") for t in reversed(turns) if t.get("job_id")), None)
        if job_id is None:
            raise HTTPException(status_code=409, detail="This session has no job yet; start one first.")
        return job_id

    def _agent_call(fn, *args) -> dict:
        try:
            out = fn(*args)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - a model failure is a user-facing message
            raise _model_failure(exc, "The agent could not answer",
                                 "this message was not added to the conversation.")
        if out.get("job_id"):
            out["job"] = _summary(_job(out["job_id"]))
        return out

    @app.post("/api/agent/start")
    async def agent_start(task: str = Form(...), photo: UploadFile = File(...)) -> dict:
        raw = await photo.read()
        if not raw or not task.strip():
            raise HTTPException(status_code=400, detail="Say what you want to do and attach a photo of it.")
        tmp = save_upload(raw, store.jobs_dir() / "_uploads" / f"agent-{uuid.uuid4().hex[:12]}.jpg")
        return _agent_call(agent_mode.start, task.strip(), str(tmp))

    @app.post("/api/agent/{sid}/photo")
    async def agent_photo(sid: str, text: str = Form(""), photo: UploadFile = File(...)) -> dict:
        job_id = _session_job(sid)
        raw = await photo.read()
        if not raw:
            raise HTTPException(status_code=400, detail="That photo did not arrive. Try again.")
        dest = save_upload(raw, store.cards_dir(job_id) / f"agent-photo-{uuid.uuid4().hex[:8]}.jpg")
        return _agent_call(agent_mode.photo, sid, text, str(dest))

    @app.post("/api/agent/{sid}/say")
    def agent_say(sid: str, text: str = Form(...)) -> dict:
        _session_job(sid)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Write something first.")
        return _agent_call(agent_mode.say_text, sid, text.strip())

    @app.get("/api/agent/{sid}")
    def agent_history(sid: str) -> dict:
        if not SESSION_RE.match(sid) or not agent_mode.exists(sid):
            raise HTTPException(status_code=404, detail="No such agent session.")
        turns = agent_mode.history(sid)
        return {"session": sid, "turns": turns,
                "job_id": next((t.get("job_id") for t in reversed(turns) if t.get("job_id")), None)}

    # ---------------------------------------------------------------- judges
    @app.get("/api/judge")
    def judge_info() -> dict:
        return judge_mod.info()

    @app.post("/api/judge/{name}")
    def judge_run(name: str) -> dict:
        """One OpenCV branch on a packaged photo: a real job, the real gate, no model."""
        if name not in judge_mod.SCENARIOS:
            raise HTTPException(status_code=404, detail=f"There is no scenario called {name!r}.")
        if not judge_mod.available():
            raise HTTPException(status_code=503, detail="The demo photos are not installed.")
        out = judge_mod.run(
            name,
            on_block=lambda reason, ti: store.trace(
                ti.get("job_id") or "unknown", "gate_block", reason=reason, tool_input=ti
            ),
        )
        out["job"] = _summary(_job(out["job_id"]))
        return out

    @app.post("/api/inspect")
    async def inspect_upload(
        evidence: UploadFile = File(...),
        reference: UploadFile | None = File(None),
        zones: str = Form(""),
        expects_change: str = Form(""),
    ) -> dict:
        """OpenCV only, no model: the PerceptionReport for one photo against another.

        ``zones`` is a JSON list of {label, kind: act|avoid|stop, box: [x0, y0, x1, y1]}
        in the reference's normalised coordinates. The uploads are deleted as soon as the
        report and its pictures exist; only the pictures are kept, under a random id.
        """
        from stepspotter.perception import inspect as P
        from stepspotter.perception import render as R

        # Everything that can be refused is refused before a byte is written.
        try:
            zl = [(z["label"], z["kind"], tuple(float(v) for v in z["box"])) for z in json.loads(zones or "[]")]
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"zones must be a JSON list of label/kind/box: {exc}")
        exp = {"true": True, "1": True, "false": False, "0": False}.get(expects_change.strip().lower())
        ev_raw = await evidence.read()
        if not ev_raw:
            raise HTTPException(status_code=400, detail="The evidence photo did not arrive.")
        ref_raw = await reference.read() if reference is not None else b""
        rid = uuid.uuid4().hex[:12]
        folder = store.jobs_dir() / "_inspect" / rid
        folder.mkdir(parents=True, exist_ok=True)
        ev_path = ref_path = None
        try:
            ev_path = save_upload(ev_raw, folder / "evidence.jpg")
            ref_path = save_upload(ref_raw, folder / "reference.jpg") if ref_raw else None
            rep, detail = P.inspect_full(str(ev_path), str(ref_path) if ref_path else None, zl, expects_change=exp)
            arts = R.render_all(rep, detail, folder, "inspect")
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"That photo could not be read: {exc}")
        finally:
            for p in (ev_path, ref_path, folder / "evidence.jpg", folder / "reference.jpg"):
                if p is not None:
                    Path(p).unlink(missing_ok=True)
        body = json.loads(rep.model_dump_json(exclude={"artifacts"}))
        body["images"] = {k: f"/api/inspect/{rid}/{k}" for k in arts}
        body["route"] = rep.route
        body["llm_called"] = False
        return body

    @app.get("/api/inspect/{rid}/{kind}")
    def inspect_image(rid: str, kind: str) -> Any:
        if not re.fullmatch(r"[0-9a-f]{12}", rid) or not INSPECT_KIND.match(kind):
            raise HTTPException(status_code=404, detail="No such picture.")
        p = store.jobs_dir() / "_inspect" / rid / f"inspect-{kind}.jpg"
        if not p.is_file():
            raise HTTPException(status_code=404, detail="That picture is not on disk.")
        return FileResponse(str(p), media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/feed")
    def feed(job_id: str) -> dict:
        """The chat transcript. Derived from the trace every time — see web/feed.py."""
        state = _job(job_id)
        # Locate this step's boxes now, if nobody has yet: the legend under the photo
        # is written from them, and the feed is fetched at exactly the moment a new
        # step appears. Failing to draw is not failing to help — the words still go.
        if state.current_step() is not None and state.current not in state.box_sets:
            try:
                svc.card(state, layout="photo")
            except Exception as exc:  # noqa: BLE001
                store.trace(job_id, "card_failed", step=state.current + 1, error=str(exc))
            state = _job(job_id)
        rows = store.read_trace(job_id)
        escalated = _escalated(job_id)
        return {
            "job": _summary(state),
            "messages": build_feed(state, rows),
            "composer": composer_state(state, escalated, review_pending(state, rows)),
        }

    @app.post("/api/jobs/{job_id}/ask")
    def ask(job_id: str, question: str = Form(...)) -> dict:
        """A question typed into the feed. Cannot move the job: the lane has no tools."""
        state = _job(job_id)
        q = question.strip()
        if not q:
            raise HTTPException(status_code=400, detail="Type the question first.")
        store.trace(job_id, "ask", question=q)
        text, reached = answer_question(state, q, answer_fn)
        store.trace(job_id, "answer", text=text, model=reached)
        return {"question": q, "answer": text, "reached_model": reached}

    @app.get("/api/jobs/{job_id}/trace")
    def trace(job_id: str, view: str = "all") -> dict:
        """The record of what happened.

        ``view=human`` is what the page shows: who did what, what came back, why —
        and NO filesystem paths, job ids or raw tool inputs, which is all the raw
        rows are made of. ``view=raw`` is the operator's view, behind an explicit
        link. The default carries both, because that is what callers written before
        this parameter existed expect.
        """
        rows = store.read_trace(job_id)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No trace for {job_id}.")
        if view == "human":
            return {"job_id": job_id, "human": humanize(rows)}
        if view == "raw":
            return {"job_id": job_id, "rows": rows}
        return {"job_id": job_id, "rows": rows, "human": humanize(rows)}

    return app


app = create_app()
