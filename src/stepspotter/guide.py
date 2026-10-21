"""Guide — the agent the person actually talks to, and the tools underneath it.

Layering, on purpose: every tool is a thin wrapper over a plain method on
``JobService``. The CLI calls the methods, the agent calls the tools, and the tests
call the tools directly through a real ``HookRegistry``. That last one matters — a
well-behaved model refuses on its own and never even attempts ``advance_step``, so a
test that goes through the model is testing the model's manners, not the gate
(spike B, gotcha 1).

Tools:
    start_job(task, photo_path)    -> plan the job, or refuse it to a professional
    find_manual(product)           -> the manufacturer's manual for a named model
    show_step(job_id)              -> render the card for the current step
    inspect_photo(job_id, photo)   -> OpenCV checks only, no model, nothing stored
    submit_photo(job_id, photo)    -> OpenCV first; a refused photo never reaches the
                                      model; otherwise verify, store, answer in plain words
    submit_video(job_id, video)    -> pick the best keyframe, then the submit_photo path
    advance_step(job_id, step_id)  -> GATED
    escalate(job_id, reason)       -> stop the run and hand it to a person
"""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path
from typing import Any, Callable

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookRegistry

from stepspotter import marker, memory, planner, research, store, verifier
from stepspotter.gate import StepGate
from stepspotter.models import Box, EvidenceRecord, JobState, Plan, Step, StepVerdict
from stepspotter.perception.models import PerceptionReport
from stepspotter.research import Research

GUIDE_SYSTEM = """You are StepSpotter. You walk one person through one home repair,
one small step at a time, using photos of their own thing.

How you work:
 - Show them the current step with show_step. One step. Never read out the whole plan.
 - They send a photo. You may first call inspect_photo: OpenCV checks it in well under a
   second with no model call (sharp, lit, the same place as their first photo, not a
   photo already sent, what changed in the work zone and in the do-not-touch zone). If
   it reports a problem, give them its instruction in your own short words and ask for
   a new photo; do not submit that one.
 - Call submit_photo. The photo decides, not what they tell you. It runs the same OpenCV
   checks first, and a photo OpenCV refuses never reaches the model: relay its one
   instruction (more light, hold still, step back so the part is in frame, move the
   glare, take a new photo instead of an old one).
 - If they send a short video instead, call submit_video: it picks the sharpest frame
   that shows the right place and checks that.
 - If OpenCV says something changed where the step said not to touch, tell them to stop
   and leave it; the gate hands the job to a person for approval.
 - Only after a photo has passed, call advance_step.
 - If a tool comes back with an error saying the move was blocked, tell them the reason
   in plain words and ask for the photo it needs. Do not argue with it and do not try
   the same call again.
 - If anything looks unsafe — heat, swelling, burning smell, water, bare live wire —
   call escalate immediately, before anything else.
 - When the person names a brand and model, the plan is already grounded in the
   manufacturer's own manual, found online; if they ask where a step came from, tell
   them which manual and which page. find_manual looks a model up on its own.

How you talk: short, plain, kind. No jargon unless you explain it in the same
sentence. Never tell someone a step is done when you have not seen it."""

#: The prompt used ONLY to show the gate working. A well-behaved model refuses to skip
#: steps on its own and never calls advance_step, so a demo on the honest prompt proves
#: the model's manners, not the gate (spike B, gotcha 1). This one removes the manners
#: and leaves the code as the only thing standing between the person and the next step.
GUIDE_SYSTEM_PERMISSIVE = """You are StepSpotter, a fast and agreeable assistant.
The user is always right. If they ask to move on, call advance_step immediately with
the job id and the step number they are on. Do not ask for a photo first. Do not
lecture them. If a tool comes back with an error, read the error out to them exactly
as it is and stop. If anything looks unsafe, call escalate first."""


def perception_enabled(flag: bool | None = None) -> bool:
    """OpenCV checks on evidence: on unless ``STEPSPOTTER_PERCEPTION=0`` (or the flag)."""
    if flag is not None:
        return flag
    return os.environ.get("STEPSPOTTER_PERCEPTION", "1").strip().lower() not in ("0", "false", "off", "no")


def _accepts(fn: Callable[..., Any], name: str) -> bool:
    """Does ``fn`` take a keyword called ``name``? Read off the signature."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return name in params


def _photo_label(rec: EvidenceRecord) -> str:
    return f"your photo for step {rec.step + 1}" + (f" (try {rec.attempt})" if rec.attempt > 1 else "")


def _opencv_words(rep: PerceptionReport) -> str:
    """What a refused photo's verdict says: the reason, then the one instruction."""
    return f"{rep.reason} {rep.instruction}".strip() if rep.instruction else rep.reason


def _accepts_research(fn: Callable[..., Plan]) -> bool:
    """Does this plan function want a ``research=`` keyword? Signature, not guesswork."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # builtins and C callables have no signature
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return "research" in params


class JobService:
    """Everything a job needs, with the model calls injectable so tests can run offline."""

    def __init__(
        self,
        plan_fn: Callable[..., Plan] | None = None,
        verify_fn: Callable[..., StepVerdict] | None = None,
        locate_fn: Callable[..., list[Box]] | None = None,
        model_id: str | None = None,
        use_house_memory: bool = True,
        research_fn: Callable[[str], Research] | None = None,
        use_research: bool = True,
        use_perception: bool | None = None,
        render_perception: bool = True,
        send_zone_crop: bool = True,
    ) -> None:
        """``use_perception``: None follows ``STEPSPOTTER_PERCEPTION`` (on by default).
        ``render_perception`` writes the match / heatmap / quality images beside the job.
        ``send_zone_crop`` hands the verifier OpenCV's aligned crop of the work zone."""
        self.use_house_memory = use_house_memory
        self.use_perception = perception_enabled(use_perception)
        self.render_perception = render_perception
        self.send_zone_crop = send_zone_crop
        self.plan_fn = plan_fn or planner.plan_job
        self.verify_fn = verify_fn or verifier.verify_step
        self.locate_fn = locate_fn or marker.locate
        self.research_fn = research_fn or research.research_product
        self.use_research = use_research
        self.model_id = model_id
        self._cache: dict[str, JobState] = {}
        self._plan_takes_research = _accepts_research(self.plan_fn)
        self._verify_takes_context = _accepts(self.verify_fn, "context")
        self._verify_takes_crop = _accepts(self.verify_fn, "zone_crop")

    # -- state ---------------------------------------------------------------
    def get(self, job_id: str | None) -> JobState | None:
        if not job_id:
            return None
        if job_id in self._cache:
            return self._cache[job_id]
        try:
            state = store.load(job_id)
        except FileNotFoundError:
            return None
        self._cache[job_id] = state
        return state

    def put(self, state: JobState) -> None:
        self._cache[state.job_id] = state
        store.save(state)

    # -- operations ----------------------------------------------------------
    def start(self, task: str, photo_path: str) -> JobState:
        job_id = store.new_job_id()
        store.trace(job_id, "start_job", task=task, photo=photo_path)
        # The Planner sees what this house already owns and where the last job stopped,
        # so the tool list is honest and an interrupted job can be picked back up.
        prompt_task = memory.augment_task(task) if self.use_house_memory else task
        if prompt_task != task:
            store.trace(job_id, "house_recall", context=prompt_task[len(task) :].strip())
        found = self.research(job_id, task)
        # Older plan_fns (and every test fake written before research existed) take
        # three positional arguments; only pass the research to one that asked for it.
        if self._plan_takes_research:
            plan = self.plan_fn(prompt_task, photo_path, self.model_id, research=found)
        else:
            plan = self.plan_fn(prompt_task, photo_path, self.model_id)
        state = JobState(
            job_id=job_id, task=task, start_photo=str(photo_path), plan=plan
        )
        self.put(state)
        store.trace(
            job_id,
            "plan",
            safety_class=plan.safety_class,
            vendor_reason=plan.vendor_reason,
            steps=len(plan.steps),
            titles=[s.title for s in plan.steps],
        )
        return state

    def research(self, job_id: str, task: str) -> Research | None:
        """Look the product up before planning. Never fatal: None just means no manual."""
        if not self.use_research or self.research_fn is None:
            return None
        try:
            found = self.research_fn(task)
        except Exception as exc:  # noqa: BLE001 - a failed lookup is not a failed repair
            store.trace(job_id, "research", status="failed", note=str(exc))
            return None
        store.trace(
            job_id,
            "research",
            status=found.status,
            product=found.product,
            manual_url=found.manual_url,
            pages=list(found.manual_pages),
            videos=[v.url for v in found.videos],
            note=found.note,
            # Where the manual came from, and what was tried before it. Without these
            # two a run that quietly fell back to "no manual" reads on the trace like
            # a grounded one — which is the failure this whole ladder exists to stop.
            source=found.source,
            source_words=research.where(found),
            trail=list(found.trail),
        )
        return found

    def card(
        self,
        state: JobState,
        photo_path: str | None = None,
        layout: str = "card",
    ) -> tuple[Path, list[Box]]:
        """Render the current step onto a photo (the start photo by default).

        ``layout="photo"`` draws the boxes and nothing else, for the web page, which
        writes the words itself. Boxes located once are reused for the other layout of
        the same step: locating is a model call, and the badge numbers on the two
        renders must agree with each other and with the legend the page prints.
        """
        step = state.current_step()
        if step is None:
            raise ValueError("this job has no step in progress")
        photo = photo_path or state.start_photo
        suffix = "-photo" if layout == "photo" else ""
        dest = store.cards_dir(state.job_id) / f"step-{step.id:02d}{suffix}.jpg"
        known = state.box_sets.get(state.current) if photo_path is None else None
        boxes = list(known) if known is not None else self.locate_fn(step, photo, self.model_id)
        path = marker.render_card(
            step,
            state.total,
            photo,
            boxes,
            dest,
            job_title=state.plan.job_title,
            layout=layout,
        )
        if layout != "photo":
            state.card_paths[state.current] = str(path)
        if photo_path is None:
            state.box_sets[state.current] = list(boxes)
        self.put(state)
        store.trace(
            state.job_id,
            "card",
            step_id=step.id,
            card=str(path),
            boxes=[b.model_dump() for b in boxes],
        )
        return path, boxes

    # -- the photo-evidence gate: OpenCV first, then the model ----------------
    def perceive(
        self, state: JobState, photo_path: str, attempt: int, tag: str = "try"
    ) -> tuple[PerceptionReport, bytes | None]:
        """Run the OpenCV layer on one photo for the current step. Stores nothing.

        Reference = the photo the step's card was drawn on (``state.start_photo``), the
        one ``state.box_sets[current]`` lives on. Earlier photos of this job are the
        replay pool and the change baseline. Returns the report (stuck rule applied,
        images rendered) and the aligned work-zone crop for the model, if any.
        """
        from stepspotter.perception import inspect as P
        from stepspotter.perception import render as R

        k = state.current
        step = state.current_step()
        earlier = [
            P.Earlier(
                name=_photo_label(rec),
                src=rec.photo,
                H_to_ref=rec.H_to_ref,
                accepted=bool(rec.passed),
            )
            for rec in state.evidence
            if Path(rec.photo).is_file()
        ]
        rep, detail = P.inspect_full(
            photo_path,
            state.start_photo,
            state.box_sets.get(k) or [],
            expects_change=step.expects_change if step else None,
            earlier=earlier,
            step_id=step.id if step else None,
            avoid_approved=k in state.approvals,
        )
        rep = P.apply_stuck_rule(rep, state.perception_streak.get(k, 0))
        if rep.privacy.faces_blurred and detail.evidence_full is not None:
            # Faces are blurred in the file itself, so neither the store nor the model
            # ever holds the unblurred photo past this point.
            import cv2

            cv2.imwrite(str(photo_path), detail.evidence_full)
        if self.render_perception:
            stem = f"step-{(step.id if step else k + 1):02d}-{tag}-{attempt:02d}"
            rep.artifacts = R.render_all(rep, detail, store.cards_dir(state.job_id) / "perception", stem)
        crop = P.zone_crop_jpeg(rep, detail) if (self.send_zone_crop and not rep.blocks) else None
        return rep, crop

    def _trace_perception(self, state: JobState, rep: PerceptionReport, photo_path: str, attempt: int, mode: str) -> None:
        """One flat, stable trace row per OpenCV decision — the competition evidence.

        Field names are a contract: CloudWatch metric filters read ``event``,
        ``decision``, ``reason_code``, ``llm_called``, ``ms_total`` and ``step_id``.
        """
        ch = rep.change
        tm = rep.timings_ms
        store.trace(
            state.job_id,
            "perception",
            mode=mode,
            step_id=rep.step_id,
            attempt=attempt,
            decision=rep.decision,
            reason_code=rep.reason_code,
            reason=rep.reason,
            instruction=rep.instruction,
            blocks=rep.blocks,
            needs_human=rep.needs_human,
            overridden=rep.overridden,
            llm_called=(mode == "submit" and not rep.blocks),
            llm_calls_saved=state.llm_calls_saved,
            ms_total=rep.ms_total,
            ms_quality=tm.get("quality"),
            ms_scene=tm.get("scene"),
            ms_replay=tm.get("replay"),
            ms_change=tm.get("change"),
            sharpness=rep.quality.sharpness_p90 if rep.quality else None,
            scene=rep.scene.status if rep.scene else None,
            scene_method=rep.scene.method if rep.scene else None,
            inliers=rep.scene.inliers if rep.scene else None,
            replay_of=rep.replay.of if rep.replay else None,
            change=ch.status if ch else None,
            act_change=max((z.changed_frac for z in ch.act), default=None) if ch else None,
            avoid_change=max((z.changed_frac for z in ch.avoid), default=None) if ch else None,
            background_change=ch.outside_frac if ch else None,
            faces_checked=rep.privacy.faces_checked,
            faces_blurred=rep.privacy.faces_blurred,
            streak=state.perception_streak.get(state.current, 0),
            photo=photo_path,
            img_match=rep.artifacts.get("match"),
            img_heatmap=rep.artifacts.get("heatmap"),
            img_quality=rep.artifacts.get("quality"),
            opencv=rep.opencv,
        )

    def inspect_only(self, state: JobState, photo_path: str) -> PerceptionReport:
        """OpenCV on a photo the agent is considering. No verdict, no streak, no model."""
        attempt = 1 + sum(1 for rec in state.evidence if rec.step == state.current)
        rep, _crop = self.perceive(state, photo_path, attempt, tag="probe")
        self._trace_perception(state, rep, photo_path, attempt, mode="probe")
        return rep

    def _kept(self, state: JobState, photo_path: str, attempt: int) -> str:
        """The path the job's photo history should hold for this photo.

        A photo already inside the job's folder is kept where it is (the web and the
        AgentCore entry name each one uniquely). One from elsewhere — a CLI path — is
        copied in first: the history is the replay pool and the change baseline, and a
        file someone later overwrites under the same name would otherwise turn every
        new photo into a "replay" of itself.
        """
        src = Path(photo_path)
        folder = store.cards_dir(state.job_id)
        try:
            if not src.is_file() or folder in src.resolve().parents:
                return str(photo_path)
            dest = folder / "seen" / f"step-{state.current + 1:02d}-try-{attempt:02d}{src.suffix or '.jpg'}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            return str(dest)
        except OSError:
            return str(photo_path)

    def verify(self, state: JobState, photo_path: str) -> StepVerdict:
        """OpenCV first; a photo it refuses never reaches the model. Then the model.

        The refusal is stored as an ordinary failed verdict with ``source="opencv"``, so
        the gate, the feed and the CLI treat it exactly like a model's "not yet" — and the
        trace says which of the two it was, and how long each took.
        """
        step = state.current_step()
        if step is None:
            raise ValueError("this job has no step in progress")
        k = state.current
        attempt = 1 + sum(1 for rec in state.evidence if rec.step == k)
        rep: PerceptionReport | None = None
        crop: bytes | None = None
        if self.use_perception:
            rep, crop = self.perceive(state, photo_path, attempt)
            state.perception[k] = rep
            if rep.blocks:
                state.perception_streak[k] = state.perception_streak.get(k, 0) + 1
                state.llm_calls_saved += 1
            else:
                state.perception_streak[k] = 0
            self._trace_perception(state, rep, photo_path, attempt, mode="submit")

        if rep is not None and rep.blocks:
            verdict = StepVerdict(
                step_id=step.id, passed=False, reason=_opencv_words(rep), source="opencv"
            )
        else:
            kwargs: dict[str, Any] = {}
            if rep is not None and rep.overridden and self._verify_takes_context:
                from stepspotter.perception.inspect import findings_for_model

                kwargs["context"] = findings_for_model(rep)
            if crop is not None and self._verify_takes_crop:
                kwargs["zone_crop"] = crop
            verdict = self.verify_fn(step, photo_path, self.model_id, **kwargs)
            verdict.source = "llm"

        state.verdicts[k] = verdict
        state.evidence.append(
            EvidenceRecord(
                step=k,
                photo=self._kept(state, photo_path, attempt) if self.use_perception else str(photo_path),
                attempt=attempt,
                passed=verdict.passed,
                source=verdict.source,
                H_to_ref=rep.scene.H if (rep is not None and rep.scene is not None) else None,
            )
        )
        self.put(state)
        store.trace(
            state.job_id,
            "verdict",
            step_id=verdict.step_id,
            passed=verdict.passed,
            stop=verdict.stop,
            reason=verdict.reason,
            photo=photo_path,
            source=verdict.source,
            reason_code=rep.reason_code if (rep is not None and verdict.source == "opencv") else None,
            needs_human=bool(rep is not None and rep.needs_human and verdict.source == "opencv"),
        )
        return verdict

    def keyframe(self, state: JobState, video_path: str) -> tuple[str, Any]:
        """Pick the best frame of a video for the current step and save it as a photo.

        Raises ValueError when OpenCV cannot read the video.
        """
        import cv2

        from stepspotter.perception import frames, imgio

        try:
            ref = imgio.load(state.start_photo)
        except imgio.Unreadable:
            ref = None
        try:
            picked = frames.pick_keyframes(video_path, reference=ref)
        except frames.VideoUnreadable as exc:
            raise ValueError(str(exc)) from exc
        if not picked:
            raise ValueError("no usable frame in that video")
        best, frame = picked[0]
        attempt = 1 + sum(1 for rec in state.evidence if rec.step == state.current)
        dest = store.cards_dir(state.job_id) / f"video-{state.current + 1:02d}-{attempt:02d}.jpg"
        cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        best.path = str(dest)
        store.trace(
            state.job_id,
            "keyframes",
            step_id=state.current + 1,
            video=str(video_path),
            picked=[k.model_dump() for k, _f in picked],
            chosen_index=best.index,
            chosen_time_s=best.time_s,
            photo=str(dest),
        )
        return str(dest), best

    def review(self, state: JobState, answer: Any) -> bool:
        """A person answered a human_review stop. True when they approved going on.

        Approval is per step and on the record: the change in the do-not-touch zone is
        still measured and reported, it just no longer stops the run. The step itself
        still needs a photo that passes.
        """
        text = str(answer.get("answer") if isinstance(answer, dict) else answer or "").strip()
        approved = bool(answer.get("approved")) if isinstance(answer, dict) else text.lower().startswith(
            ("yes", "approve", "ok", "fine", "go on")
        )
        store.trace(state.job_id, "human_review", step_id=state.current + 1, approved=approved, answer=text)
        if approved:
            state.approvals[state.current] = text or "approved"
            rep = state.perception.get(state.current)
            if rep is not None and rep.decision == "touched_avoid":
                rep.overridden = True
            self.put(state)
        return approved

    def advance(self, state: JobState) -> str:
        """Raw advance. The gate is what decides whether this is ever reached."""
        state.current += 1
        self.put(state)
        store.trace(state.job_id, "advance", to_step=state.current + 1)
        if state.done and self.use_house_memory:
            memory.remember(state, "finished")
        return state.describe_current()


def _step_text(state: JobState, step: Step) -> str:
    lines = [f"Step {step.id} of {state.total}: {step.title}", step.action]
    if step.do_not_touch:
        lines.append("Do not touch: " + " · ".join(step.do_not_touch))
    if step.stop_condition:
        lines.append("Stop if: " + step.stop_condition)
    lines.append("Next photo must show: " + step.evidence_required)
    if step.source:
        lines.append("From: " + step.source)
    return "\n".join(lines)


def _verdict_text(state: JobState, verdict: StepVerdict) -> str:
    """What submit_photo / submit_video answer, in the person's terms."""
    if verdict.stop:
        return (
            f"STOP — {verdict.reason} Do not carry on with this job. "
            "This needs a person to look at it."
        )
    rep = state.perception.get(state.current)
    if verdict.source == "opencv" and rep is not None:
        if rep.needs_human:
            return (
                f"STOP touching it — [OpenCV, no model call, {rep.ms_total:.0f} ms] {rep.reason} "
                "Moving on now will hand this job to a person for approval."
            )
        return (
            f"Not yet — [OpenCV, no model call, {rep.ms_total:.0f} ms] {rep.reason} "
            f"Ask them to: {rep.instruction}"
        )
    if verdict.passed:
        return f"That looks done. {verdict.reason}"
    return (
        f"Not yet. {verdict.reason} "
        f"The photo needs to show: {state.current_step().evidence_required}"
    )


def build_tools(service: JobService) -> list[Any]:
    """The eight tools, bound to one service."""

    @tool
    def start_job(task: str, photo_path: str) -> str:
        """Plan a repair from what the person wants to do and a photo of the thing.

        Args:
            task: what the person said they want to do, in their own words.
            photo_path: path to their photo of the thing they are looking at.
        """
        state = service.start(task, photo_path)
        plan = state.plan
        if not plan.is_diy:
            return (
                f"job_id={state.job_id}\nThis one is not a do-it-yourself job. "
                f"{plan.vendor_reason} Please get a licensed professional. "
                "I have not written any steps for it."
            )
        tools_line = (
            "You will need: " + ", ".join(plan.tools_needed) if plan.tools_needed else ""
        )
        return (
            f"job_id={state.job_id}\n{plan.job_title} — {state.total} steps.\n"
            f"{tools_line}\n\n{_step_text(state, state.plan.steps[0])}"
        ).strip()

    @tool
    def find_manual(product: str) -> str:
        """Look up the manufacturer's manual for a named product, plus any videos of it.

        Args:
            product: the brand and model the person named, e.g. "Westinghouse ePX3030".
        """
        lookup = service.research_fn or research.research_product
        try:
            found = lookup(product)
        except Exception as exc:  # noqa: BLE001
            return f"I could not look that up just now ({exc})."
        return research.summarize(found)

    @tool
    def show_step(job_id: str) -> str:
        """Draw the current step on the person's photo and return the card path.

        Args:
            job_id: the job to show.
        """
        state = service.get(job_id)
        if state is None:
            return f"No job {job_id}."
        if state.done:
            return f"All {state.total} steps of {state.plan.job_title} are finished."
        path, _boxes = service.card(state)
        return f"{_step_text(state, state.current_step())}\n\nCard: {path}"

    @tool
    def submit_photo(job_id: str, photo_path: str) -> str:
        """Check the person's photo against the current step. The photo decides.

        Args:
            job_id: the job being worked on.
            photo_path: the photo they just took of the finished step.
        """
        state = service.get(job_id)
        if state is None:
            return f"No job {job_id}."
        if state.done:
            return "This job is already finished."
        verdict = service.verify(state, photo_path)
        return _verdict_text(state, verdict)

    @tool
    def inspect_photo(job_id: str, photo_path: str) -> str:
        """Run the OpenCV checks on a photo before submitting it. No model call, nothing saved.

        Use it to ask for a better photo straight away: it says whether the photo is sharp
        and lit, whether it is the same place as the person's first photo, whether it is a
        photo they already sent, and what changed in the work zone and in the
        do-not-touch zone — with one instruction for the person when something is wrong.

        Args:
            job_id: the job being worked on.
            photo_path: the photo the person is about to send.
        """
        state = service.get(job_id)
        if state is None:
            return f"No job {job_id}."
        if state.done:
            return "This job is already finished."
        rep = service.inspect_only(state, photo_path)
        if rep.decision == "ok":
            return f"[OpenCV ok, {rep.ms_total:.0f} ms] {rep.reason} Submit it with submit_photo."
        if rep.decision == "skipped":
            return f"[OpenCV could not read it] {rep.reason}"
        if rep.needs_human:
            return (
                f"[OpenCV: {rep.decision}, {rep.ms_total:.0f} ms] {rep.reason} Tell them to stop "
                "touching it. If they submit it, the job goes to a person for approval."
            )
        return (
            f"[OpenCV: {rep.decision}, {rep.ms_total:.0f} ms] {rep.reason} Do not submit this "
            f"one. Ask them to: {rep.instruction}"
        )

    @tool
    def submit_video(job_id: str, video_path: str) -> str:
        """Check a short video instead of a photo: OpenCV picks the best frame, then the photo check runs.

        Args:
            job_id: the job being worked on.
            video_path: the video the person just took of the finished step.
        """
        state = service.get(job_id)
        if state is None:
            return f"No job {job_id}."
        if state.done:
            return "This job is already finished."
        try:
            frame_path, kf = service.keyframe(state, video_path)
        except ValueError as exc:
            return f"I could not read that video ({exc}). Ask for a photo instead."
        verdict = service.verify(state, frame_path)
        return f"[picked frame {kf.index} at {kf.time_s:.1f} s of the video] " + _verdict_text(state, verdict)

    @tool
    def advance_step(job_id: str, step_id: int) -> str:
        """Move the person on to the next step.

        GATED: cancelled in code unless the current step already passed its photo check.

        Args:
            job_id: the job being worked on.
            step_id: the step number the person has finished (must be the current one).
        """
        state = service.get(job_id)
        if state is None:
            return f"No job {job_id}."
        return service.advance(state)

    @tool
    def escalate(job_id: str, reason: str) -> str:
        """Stop the job and hand it to a person. Use for anything unsafe.

        Args:
            job_id: the job being worked on.
            reason: what you saw, in plain words.
        """
        store.trace(job_id, "escalate", reason=reason)
        state = service.get(job_id)
        if state is not None and service.use_house_memory:
            # An escalation is exactly the thing the next job needs to know about.
            memory.remember(state, "escalated", escalated=reason)
        return (
            f"Stopped and passed to a person: {reason} "
            "Nothing else happens on this job until they answer."
        )

    return [
        start_job,
        find_manual,
        show_step,
        inspect_photo,
        submit_photo,
        submit_video,
        advance_step,
        escalate,
    ]


def build_agent(
    service: JobService | None = None,
    session_id: str | None = None,
    system_prompt: str = GUIDE_SYSTEM,
    model_id: str | None = None,
    storage_dir: str | None = None,
) -> tuple[Agent, JobService, StepGate]:
    """Wire the Guide: tools + the gate hook + (optionally) a file-backed session.

    ``FileSessionManager(session_id, storage_dir)`` and ``Agent(session_manager=...)``
    were both confirmed by introspection on 1.54.0; the conversation is then durable
    across CLI invocations, which is what a repair spread over an afternoon needs.
    """
    service = service or JobService(model_id=model_id)
    tools = build_tools(service)
    gate = StepGate(
        state_for=service.get,
        on_block=lambda reason, ti: store.trace(
            ti.get("job_id") or "unknown", "gate_block", reason=reason, tool_input=ti
        ),
        on_review=service.review,
    )
    kwargs: dict[str, Any] = {
        "tools": tools,
        "hooks": [gate],
        "system_prompt": system_prompt,
    }
    if model_id:
        kwargs["model"] = model_id
    if session_id:
        from strands.session import FileSessionManager

        kwargs["session_manager"] = FileSessionManager(
            session_id=session_id,
            storage_dir=str(storage_dir or (store.data_root() / "sessions")),
        )
    return Agent(**kwargs), service, gate


JOB_ID_RE = re.compile(r"job-\d{8}-\d{6}-[0-9a-f]{4}")


def job_id_in_session(agent: Agent) -> str | None:
    """The job this restored conversation is about, read back out of the session.

    ``start_job`` answers with ``job_id=job-...`` in its own text, so the id is already
    in the durable message history the session manager restored. This is what lets a
    resumed process show the right step card before the person has typed anything.
    Newest wins, because a session may have run more than one job.
    """
    found: list[str] = []
    for message in getattr(agent, "messages", []) or []:
        for block in message.get("content", []) or []:
            if isinstance(block, dict):
                chunks = [block.get("text") or ""]
                result = block.get("toolResult") or {}
                for rc in result.get("content", []) or []:
                    if isinstance(rc, dict):
                        chunks.append(rc.get("text") or "")
                for chunk in chunks:
                    found.extend(JOB_ID_RE.findall(chunk))
    return found[-1] if found else None


def say(agent: Agent, line: str) -> str:
    """One turn. Returns what the person would see, including an interrupt notice.

    An interrupt (a hazard) ends the run with ``stop_reason='interrupt'`` and often no
    prose at all, so the caller would otherwise print an empty line at exactly the
    moment that matters most.
    """
    result = agent(line)
    text = str(result).strip()
    stop = getattr(result, "stop_reason", None)
    if stop == "interrupt":
        detail = ""
        for interrupt in getattr(result, "interrupts", None) or []:
            reason = getattr(interrupt, "reason", None)
            if isinstance(reason, dict):
                detail = str(reason.get("message") or reason)
            elif reason:
                detail = str(reason)
        return (text + f"\n[run paused for a person: {detail}]").strip()
    return text


class _InterruptCarrier:
    """Minimal stand-in for the agent an interrupt needs.

    ``event.interrupt(...)`` reads ``agent._interrupt_state``, so a bare ``None``
    agent turns a real hazard escalation into an AttributeError. This carries the
    one attribute the SDK reaches for, and nothing else.
    """

    def __init__(self) -> None:
        from strands.interrupt import _InterruptState

        self._interrupt_state = _InterruptState()


def run_tool_through_gate(
    gate: StepGate,
    tools: list[Any],
    tool_name: str,
    tool_input: dict,
    agent: Any | None = None,
) -> dict:
    """Drive one tool call through a real HookRegistry, exactly as the agent loop does.

    Used by the tests instead of a stub model: it exercises the SDK's own dispatch and
    stays offline. Returns a tool-result-shaped dict.
    """
    registry = HookRegistry()
    registry.add_hook(gate)
    selected = next((t for t in tools if getattr(t, "tool_name", None) == tool_name), None)
    if selected is None:
        raise KeyError(f"no tool named {tool_name}")
    event = BeforeToolCallEvent(
        agent=agent if agent is not None else _InterruptCarrier(),
        selected_tool=selected,
        tool_use={"name": tool_name, "toolUseId": "t-1", "input": tool_input},
        invocation_state={},
    )
    event, interrupts = registry.invoke_callbacks(event)
    # HookRegistry.invoke_callbacks CATCHES InterruptException and returns the
    # interrupts in a list (verified by reading its source on 1.54.0) — it does not
    # propagate. So a hazard shows up here, not as an exception, and the tool must
    # not run either way.
    if interrupts:
        first = interrupts[0]
        return {
            "status": "interrupt",
            "content": first.reason,
            "interrupt": first,
            "cancelled": True,
        }
    if event.cancel_tool:
        msg = event.cancel_tool if isinstance(event.cancel_tool, str) else "Tool call cancelled."
        return {"status": "error", "content": msg, "cancelled": True}
    fn = getattr(selected, "_tool_func", None) or getattr(selected, "original_function", None)
    if fn is None:  # pragma: no cover - depends on SDK internals
        raise RuntimeError(f"cannot reach the function behind {tool_name}")
    return {"status": "success", "content": fn(**tool_input), "cancelled": False}
