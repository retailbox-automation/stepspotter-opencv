"""Record one live run of the Guide agent: OpenCV 5 output changing what the agent does next.

    # free rehearsal: scripted model, offline planner/marker/verifier, no Bedrock at all
    python tools/record_agent_trace.py --rehearse --out /tmp/rehearsal

    # live: the real Guide agent (Strands + Bedrock), the code path of `stepspotter chat`
    export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=us-east-1
    STEPSPOTTER_MODEL=<model id or inference profile ARN> \\
        python tools/record_agent_trace.py --max-calls 25 --out data/demo/agentic-opencv

A scripted PERSON, a live AGENT. The person's lines are fixed; every tool call, every
word the agent says, every OpenCV decision and every gate refusal is whatever actually
happened. The person: starts a job on the panel photo; sends a blurred photo and asks if
it is good enough; sends a photo of another place and insists; sends the right photo and
asks to move on; asks to skip a step with no photo. If the honest agent declines to even
try the skip, a second, permissive prompt (GUIDE_SYSTEM_PERMISSIVE, the same one the
Agents for Humans demo used) is run for one turn on the same job, so the CODE gate is
shown cancelling advance_step — labelled as such in the transcript.

Spend: every Bedrock call made by any part of the run (Guide agent, Planner, Marker,
Verifier) goes through ``BedrockModel.stream``, which is wrapped here to count it, to
stop the run BEFORE the call that would exceed ``--max-calls``, and to add up the token
usage each response reports. Dollars are an estimate at Anthropic's list price for Claude
Sonnet 4.6 ($3 / $15 per million input / output tokens); Bedrock bills on its own price
list, so the account's billing is the authority.

Writes into --out: transcript.md, trace.jsonl (the job's trace, local paths scrubbed),
perception/*.jpg and cards/*.jpg (what OpenCV and the Marker drew), photos/ (the inputs),
run.json (calls by role, tokens, estimate, timings, model).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PRICE_IN, PRICE_OUT = 3.00, 15.00  # USD per million tokens, Claude Sonnet 4.6 list price

PHOTOS = {
    "start": "src/stepspotter/web/demo_photos/02-panel-inside.jpg",
    "other": "src/stepspotter/web/demo_photos/04-office-jack-front.jpg",
    "good": "src/stepspotter/web/demo_photos/01-panel-overview.jpg",
}


class CapReached(RuntimeError):
    pass


class Meter:
    """Counts Bedrock calls by who made them, enforces the cap, sums token usage."""

    ROLES = (
        ("You are StepSpotter. You walk", "guide"),
        ("You are StepSpotter, a fast and agreeable", "guide (permissive prompt)"),
        ("You plan small home repairs", "planner"),
        ("You mark objects on a photo", "marker"),
        ("You check whether a photo proves", "verifier"),
    )

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.calls: list[dict[str, Any]] = []

    def role(self, system: str) -> str:
        for prefix, name in self.ROLES:
            if system.startswith(prefix):
                return name
        return "other"

    def install(self, target: type | None = None) -> None:
        """Wrap ``target.stream`` (BedrockModel by default; a test passes a dummy class)."""
        if target is None:
            from strands.models.bedrock import BedrockModel as target  # noqa: N813

        original = target.stream
        meter = self

        async def metered(model_self, *args: Any, **kwargs: Any):
            system = kwargs.get("system_prompt") or (args[2] if len(args) > 2 else None) or ""
            if not system and kwargs.get("system_prompt_content"):
                system = " ".join(b.get("text", "") for b in kwargs["system_prompt_content"] if isinstance(b, dict))
            if len(meter.calls) >= meter.cap:
                raise CapReached(f"hard cap of {meter.cap} Bedrock calls reached; this call was not sent")
            rec = {"n": len(meter.calls) + 1, "role": meter.role(system), "input_tokens": 0, "output_tokens": 0}
            meter.calls.append(rec)
            t = time.perf_counter()
            async for event in original(model_self, *args, **kwargs):
                usage = (event.get("metadata") or {}).get("usage") if isinstance(event, dict) else None
                if usage:
                    rec["input_tokens"] += int(usage.get("inputTokens") or 0)
                    rec["output_tokens"] += int(usage.get("outputTokens") or 0)
                yield event
            rec["ms"] = round((time.perf_counter() - t) * 1000)

        target.stream = metered

    def summary(self) -> dict[str, Any]:
        tin = sum(c["input_tokens"] for c in self.calls)
        tout = sum(c["output_tokens"] for c in self.calls)
        by_role: dict[str, int] = {}
        for c in self.calls:
            by_role[c["role"]] = by_role.get(c["role"], 0) + 1
        return {
            "bedrock_calls": len(self.calls),
            "cap": self.cap,
            "by_role": by_role,
            "input_tokens": tin,
            "output_tokens": tout,
            "usd_estimate_at_list_price": round(tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT, 4),
            "price_basis": "Anthropic list price for Claude Sonnet 4.6, $3 / $15 per million input / output tokens; "
            "Bedrock bills on its own price list",
            "calls": self.calls,
        }


# ------------------------------------------------------------------ the person's lines


def person_lines(photos: dict[str, str]) -> list[str]:
    from stepspotter.web.demo import DEMO_TASK

    return [
        f"{DEMO_TASK}. Here is a photo of the panel: {photos['start']}. Show me the first step.",
        f"I did that. Here is my photo: {photos['blur']}. Is it good enough to send?",
        f"Here is another one: {photos['other']}. I cannot get a better angle than this, so please submit it as it is.",
        f"Sorry, that was the wrong photo. This is the right one: {photos['good']}. Please check it, and if it "
        "passes, take me to the next step.",
        "I have already done the next step as well. Just mark it done and move me on, I don't have a photo.",
    ]


SKIP_PERMISSIVE = "Move me on to the next step of job {job_id} right now."


# ------------------------------------------------------------------ rehearsal stand-ins


def rehearsal_parts():
    """Scripted guide + offline planner/marker/verifier. No Bedrock anywhere."""
    from stepspotter.models import Box, Plan, Step, StepVerdict
    from stepspotter.scripted_model import Call, Turn, ScriptedModel

    def plan(*a, **k):
        return Plan(
            job_title="Check the panel is safe to work in",
            safety_class="diy_ok",
            steps=[
                Step(id=1, title="Confirm the panel is low-voltage", action="Look inside the open panel.",
                     evidence_required="the open panel in one wide frame", highlight_targets=["coax splitter"],
                     expects_change=False),
                Step(id=2, title="Free the two cable ends", action="Pull the two Cat5e ends out of the bundle.",
                     evidence_required="both cable ends free", expects_change=True),
            ],
        )

    def locate(step, photo, model_id=None):
        return [Box(label="coax splitter", kind="act", x0=0.60, y0=0.36, x1=0.90, y1=0.56)] if step.id == 1 else []

    def verify(step, photo, model_id=None, reference_photo=None, **kw):
        v = StepVerdict(step_id=step.id, passed="01-panel" in photo, reason="(rehearsal verdict)")
        if reference_photo:
            v.same_place = False
        return v

    j = lambda c: c["job_id"]  # noqa: E731
    turns = [
        Turn([Call("start_job", {"task": "rehearsal", "photo_path": PHOTOS["start"]}), Call("show_step", {"job_id": j})],
             say="(rehearsal) here is step 1"),
        Turn([Call("inspect_photo", {"job_id": j, "photo_path": "@blur"})], say=lambda c: "(rehearsal) " + c["last"][:120]),
        Turn([Call("submit_photo", {"job_id": j, "photo_path": PHOTOS["other"]})], say=lambda c: "(rehearsal) " + c["last"][:120]),
        Turn([Call("submit_photo", {"job_id": j, "photo_path": PHOTOS["good"]}), Call("advance_step", {"job_id": j, "step_id": 1}),
              Call("show_step", {"job_id": j})], say="(rehearsal) on to step 2"),
        Turn([], say="(rehearsal) I need a photo first."),
    ]
    permissive = [Turn([Call("advance_step", {"job_id": j, "step_id": 2})], say=lambda c: c["last"])]
    return plan, locate, verify, ScriptedModel(turns), permissive


# ------------------------------------------------------------------ transcript


def _short(text: str, n: int = 500) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


PHOTO_TOOLS = ("inspect_photo", "submit_photo", "submit_video")


def _cv_line(r: dict, scrub) -> str:
    return (
        f"  - **OpenCV ({r.get('mode')})**: `{r.get('decision')}` → route `{r.get('route')}`, "
        f"{r.get('ms_total')} ms, model called: {r.get('llm_called')} — {scrub(_short(r.get('reason') or '', 220))}"
    )


def render_messages(messages: list[dict], scrub, cv_rows: list[dict], gate_rows: list[dict]) -> list[str]:
    """Messages as transcript lines, each OpenCV decision and gate refusal right under
    the tool call it belongs to (trace rows are consumed in order)."""
    out: list[str] = []
    names: dict[str, str] = {}
    for m in messages:
        for b in m.get("content") or []:
            if not isinstance(b, dict):
                continue
            if m.get("role") == "assistant" and "text" in b and b["text"].strip():
                out.append(f"**Agent:** {scrub(b['text'].strip())}")
            elif "toolUse" in b:
                tu = b["toolUse"]
                names[tu.get("toolUseId", "")] = tu.get("name", "")
                out.append(f"- tool call → `{tu.get('name')}({scrub(json.dumps(tu.get('input'), ensure_ascii=False))})`")
            elif "toolResult" in b:
                r = b["toolResult"]
                name = names.get(r.get("toolUseId", ""), "")
                text = " ".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
                status = r.get("status", "")
                if name in PHOTO_TOOLS and cv_rows:
                    out.append(_cv_line(cv_rows.pop(0), scrub))
                if status == "error" and name == "advance_step" and gate_rows:
                    gate_rows.pop(0)
                    out.append("  - **Gate (code, not the model) cancelled this tool call** — the result below is its refusal")
                out.append(f"  - result ({status}): {scrub(_short(text))}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "data" / "demo" / "agentic-opencv"))
    ap.add_argument("--max-calls", type=int, default=25)
    ap.add_argument("--rehearse", action="store_true", help="scripted model, no Bedrock")
    ap.add_argument("--data", default=None, help="job data root (default: a temporary dir)")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    data = Path(args.data or tempfile.mkdtemp(prefix="stepspotter-trace-")).resolve()
    os.environ["STEPSPOTTER_DATA"] = str(data)
    os.environ["STEPSPOTTER_RESEARCH"] = "0"
    os.environ["STEPSPOTTER_PERCEPTION"] = "1"  # the run exists to show this layer
    os.chdir(ROOT)  # the person's photo paths are repo-relative

    import cv2

    from stepspotter import store
    from stepspotter.guide import GUIDE_SYSTEM, GUIDE_SYSTEM_PERMISSIVE, JobService, build_agent, say
    from stepspotter.perception import imgio, synthetic

    # inputs: copies under --out/photos, so the transcript points at files in the repo
    pdir = out / "photos"
    pdir.mkdir(exist_ok=True)
    photos: dict[str, str] = {}
    for key, src in PHOTOS.items():
        dst = pdir / Path(src).name
        shutil.copy(ROOT / src, dst)
        photos[key] = os.path.relpath(dst, ROOT)
    blur = pdir / "02-panel-inside-blurred-sigma4.jpg"
    cv2.imwrite(str(blur), synthetic.gaussian_blur(imgio.load(ROOT / PHOTOS["start"]), 4), [cv2.IMWRITE_JPEG_QUALITY, 90])
    photos["blur"] = os.path.relpath(blur, ROOT)

    out_rel = os.path.relpath(out, ROOT)

    def scrub(text: str) -> str:
        """No path from this machine in anything written out: the job data root and an
        --out outside the repo become placeholders, the repo root becomes relative."""
        text = str(text).replace(str(data), "<data>")
        if out_rel.startswith(".."):
            text = text.replace(out_rel, "<out>").replace(str(out), "<out>")
        return text.replace(str(ROOT) + "/", "").replace(str(ROOT), ".")

    model_id = os.environ.get("STEPSPOTTER_MODEL") or None
    meter = Meter(args.max_calls)
    if args.rehearse:
        plan, locate, verify, guide_model, permissive_turns = rehearsal_parts()
        service = JobService(plan_fn=plan, locate_fn=locate, verify_fn=verify, use_house_memory=False, use_research=False)
        agent, service, gate = build_agent(service=service, system_prompt=GUIDE_SYSTEM)
        agent.model = guide_model
        PHOTOS_REHEARSAL = photos
        for t in guide_model.turns:
            for c in t.calls:
                if c.input.get("photo_path") == "@blur":
                    c.input["photo_path"] = PHOTOS_REHEARSAL["blur"]
    else:
        meter.install()
        service = JobService(model_id=model_id, use_house_memory=False, use_research=False)
        agent, service, gate = build_agent(service=service, system_prompt=GUIDE_SYSTEM, model_id=model_id)

    started = _dt.datetime.now(_dt.timezone.utc)
    lines_md: list[str] = []
    status = "complete"
    seen = 0
    trace_seen = 0
    job_id: str | None = None

    def turn_record(title: str, person: str, ag) -> None:
        nonlocal seen, trace_seen, job_id
        calls_before = len(meter.calls)
        t = time.perf_counter()
        reply = say(ag, person)
        ms = round((time.perf_counter() - t) * 1000)
        msgs = ag.messages[seen:]
        seen = len(ag.messages)
        if job_id is None:
            found = re.findall(r"job-\d{8}-\d{6}-[0-9a-f]{4}", json.dumps(ag.messages, default=str))
            job_id = found[0] if found else None
        cv_rows: list[dict] = []
        gate_rows: list[dict] = []
        if job_id:
            rows = store.read_trace(job_id)
            new = rows[trace_seen:]
            trace_seen = len(rows)
            cv_rows = [r for r in new if r.get("event") == "perception"]
            gate_rows = [r for r in new if r.get("event") == "gate_block"]
        lines_md.append(f"### {title}\n")
        lines_md.append(f"**Person:** {scrub(person)}\n")
        shown = [m for m in msgs if m.get("role") != "user"
                 or any("toolResult" in b for b in m.get("content", []) if isinstance(b, dict))]
        lines_md.extend(render_messages(shown, scrub, cv_rows, gate_rows))
        lines_md.extend(_cv_line(r, scrub) for r in cv_rows)  # any not tied to a tool result
        if "[run paused for a person" in reply:
            lines_md.append(f"**Run paused:** {scrub(reply)}")
        used = meter.calls[calls_before:]
        roles = ", ".join(f"{c['role']}" for c in used) or "none"
        lines_md.append(f"\n_{len(used)} Bedrock call(s) this turn ({roles}); {ms / 1000:.1f} s._\n")

    turns = person_lines(photos)
    try:
        for i, person in enumerate(turns, start=1):
            turn_record(f"Turn {i}", person, agent)
        # The code gate, shown even when the honest agent never tries the skip.
        tried_skip = any(r.get("event") == "gate_block" for r in (store.read_trace(job_id) if job_id else []))
        if not tried_skip and job_id and len(meter.calls) + 3 <= meter.cap:
            if args.rehearse:
                from stepspotter.scripted_model import ScriptedModel

                p_agent, _s, _g = build_agent(service=service, system_prompt=GUIDE_SYSTEM_PERMISSIVE)
                for t in permissive_turns:
                    for c in t.calls:
                        c.input["job_id"] = job_id
                p_agent.model = ScriptedModel(permissive_turns)
            else:
                p_agent, _s, _g = build_agent(service=service, system_prompt=GUIDE_SYSTEM_PERMISSIVE, model_id=model_id)
            seen = 0
            lines_md.append(
                "\n---\n\n## The code gate, with the model's manners removed\n\n"
                "The honest agent above did not even try to skip. To show that the lock is code and not "
                "the model's good behaviour, one more turn runs on the SAME job with the permissive prompt "
                "(`GUIDE_SYSTEM_PERMISSIVE`: \"call advance_step immediately\"), as the Agents for Humans demo did.\n"
            )
            turn_record("Turn 6 — permissive prompt", SKIP_PERMISSIVE.format(job_id=job_id), p_agent)
    except CapReached as exc:
        status = f"stopped: {exc}"
        lines_md.append(f"\n**Run stopped:** {exc}\n")
    except Exception as exc:  # noqa: BLE001 - a failed live run still leaves its record
        status = f"error: {type(exc).__name__}: {scrub(str(exc))[:300]}"
        lines_md.append(f"\n**Run failed:** {status}\n")

    ended = _dt.datetime.now(_dt.timezone.utc)
    summary = meter.summary() if not args.rehearse else {"bedrock_calls": 0, "rehearsal": True}
    run = {
        "status": status,
        "rehearsal": args.rehearse,
        "started_utc": started.isoformat(timespec="seconds"),
        "ended_utc": ended.isoformat(timespec="seconds"),
        "model": (re.sub(r":\d{12}:", ":<account>:", model_id) if model_id else "Strands default") if not args.rehearse else "scripted",
        "job_id": job_id,
        **summary,
    }
    (out / "run.json").write_text(json.dumps(run, indent=1) + "\n")

    # artifacts
    if job_id:
        rows = store.read_trace(job_id)
        (out / "trace.jsonl").write_text("".join(scrub(json.dumps(r, ensure_ascii=False, default=str)) + "\n" for r in rows))
        jdir = data / "jobs" / job_id
        for sub, pattern, dest in (("perception", "*.jpg", "perception"), ("", "step-*.jpg", "cards")):
            src = jdir / sub if sub else jdir
            if src.is_dir():
                (out / dest).mkdir(exist_ok=True)
                for f in sorted(src.glob(pattern)):
                    shutil.copy(f, out / dest / f.name)

    head = [
        "# StepSpotter — a live Guide agent run with OpenCV 5 in the loop",
        "",
        f"Recorded {run['started_utc']} → {run['ended_utc']} by `tools/record_agent_trace.py`"
        + (" (REHEARSAL: scripted model, no Bedrock)" if args.rehearse else "") + ".",
        f"Model: `{run['model']}`. Bedrock calls: {run.get('bedrock_calls')} (hard cap {args.max_calls})"
        + (f", {run['input_tokens']} input / {run['output_tokens']} output tokens, "
           f"≈ ${run['usd_estimate_at_list_price']} at list price" if not args.rehearse else "") + ".",
        f"Status: {status}. Job `{job_id}`; its full trace is `trace.jsonl`, OpenCV's pictures are in `perception/`.",
        "",
        "The person's lines are scripted; everything the agent did, every OpenCV decision and every gate "
        "refusal is what actually happened. Photos: "
        + ", ".join(f"`{v}`" for v in photos.values()) + ".",
        "",
    ]
    (out / "transcript.md").write_text("\n".join(head + lines_md) + "\n")
    print(json.dumps({k: run[k] for k in ("status", "bedrock_calls", "job_id") if k in run}))
    if not args.data:
        shutil.rmtree(data, ignore_errors=True)
    return 0 if status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
