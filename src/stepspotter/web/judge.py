"""For judges: the OpenCV branches of the gate, on photos shipped in the package, no model.

Each scenario is a REAL job walked through the REAL path — ``JobService.verify`` (OpenCV
first) and the ``advance_step`` tool through the Strands ``HookRegistry`` with the real
``StepGate`` — with three substitutions, all of them on the record:

* the plan is fixed (no Planner call), and so are the zones (no Marker call): the zones
  are the ones placed by hand on ``02-panel-inside.jpg`` (fixtures/perception/scenes.json);
* the evidence photo is generated from the packaged photos by a named, deterministic
  transformation (perception/synthetic.py) — a blur, another photo, a copy, an edit;
* the verifier is a function that RAISES if it is ever called. Every scenario here ends
  before a model would be asked; if one ever reached it, the scenario fails loudly
  instead of quietly spending a Bedrock call or faking a verdict.

So what a judge sees — the refusal, the instruction, the stop for a person, the timings
and the pictures — is exactly what a phone user would get for the same photo.
"""

from __future__ import annotations

from typing import Any, Callable

import cv2
import numpy as np

from stepspotter import store
from stepspotter.gate import StepGate
from stepspotter.guide import JobService, build_tools, run_tool_through_gate
from stepspotter.models import Box, Plan, Step
from stepspotter.web import demo as demo_mod

#: The zones placed by hand on 02-panel-inside.jpg — identical to the "02" entry of
#: fixtures/perception/scenes.json (a test keeps the two in step). Duplicated here
#: because the container ships src/, not fixtures/.
ZONES_02: list[Box] = [
    Box(label="coax splitter", kind="act", x0=0.60, y0=0.36, x1=0.90, y1=0.56),
    Box(label="telecom module", kind="avoid", x0=0.14, y0=0.33, x1=0.52, y1=0.62),
]

JUDGE_TASK = "Fit a new connector on the coax splitter, without touching the telecom module"


def _plan() -> Plan:
    return Plan(
        job_title="Fit a connector on the splitter",
        safety_class="diy_ok",
        tools_needed=["the new connector"],
        steps=[
            Step(
                id=1,
                title="Fit the new connector",
                action="Push the new connector onto the free port of the silver coax splitter.",
                do_not_touch=["the telecom module (the black block on the left)"],
                stop_condition="if anything is hot, wet or smells burnt, stop and get a person",
                evidence_required="the coax splitter with the new connector fitted, from about where you took the first photo",
                highlight_targets=["coax splitter", "telecom module"],
                expects_change=True,
            ),
            Step(
                id=2,
                title="Check the module is untouched",
                action="Look at the telecom module and confirm nothing on it moved.",
                evidence_required="the telecom module, all cables still seated",
                expects_change=False,
            ),
        ],
    )


def _load(which: str) -> np.ndarray:
    raw = demo_mod.photo_bytes(which)
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:  # pragma: no cover - the packaged photos are JPEGs
        raise ValueError(f"cannot decode the packaged {which} photo")
    return img


def _part() -> np.ndarray:
    """A foreign part to put into a zone: the yellow keystone from the packaged 04 photo."""
    img = _load("wrong")
    h, w = img.shape[:2]
    return img[int(0.38 * h) : int(0.80 * h), int(0.22 * w) : int(0.80 * w)].copy()


def _box(kind: str) -> tuple[float, float, float, float]:
    b = next(z for z in ZONES_02 if z.kind == kind)
    return (b.x0, b.y0, b.x1, b.y1)


def _blurred() -> np.ndarray:
    from stepspotter.perception import synthetic

    return synthetic.gaussian_blur(_load("start"), 4)


def _elsewhere() -> np.ndarray:
    return _load("wrong")


def _again() -> np.ndarray:
    from stepspotter.perception import synthetic

    return synthetic.resize(synthetic.jpeg(_load("start"), 70), 0.8)


def _touched() -> np.ndarray:
    from stepspotter.perception import synthetic

    edited = synthetic.paste_patch(_load("start"), _box("avoid"), _part(), cover=0.6, seed=2)
    return synthetic.perspective(edited, 0.05, 4)


#: name -> (button label, what the evidence is, what OpenCV should decide, generator)
SCENARIOS: dict[str, dict[str, Any]] = {
    "retake": {
        "label": "Blurry photo → retake, with one instruction",
        "evidence": "the start photo with a Gaussian blur, sigma 4 px",
        "expect": "retake",
        "make": _blurred,
    },
    "another_place": {
        "label": "Photo OpenCV cannot line up → the two-photo check",
        "evidence": "the packaged photo of a wall jack, not the panel",
        "expect": "place_unconfirmed",
        "make": _elsewhere,
        # Not a block any more: OpenCV routes it to the model with BOTH photos, which is
        # where judge mode stops — the scenario shows the routing decision, no model call.
        "probe": True,
    },
    "replay": {
        "label": "The first photo sent again → blocked",
        "evidence": "the start photo, re-encoded at JPEG 70 and resized to 80 %",
        "expect": "replay",
        "make": _again,
    },
    "human_approval": {
        "label": "Change in a do-not-touch zone → a person approves",
        "evidence": "the start photo with a foreign part pasted into the telecom module zone, re-shot at a slight angle",
        "expect": "touched_avoid",
        "make": _touched,
    },
}


def available() -> bool:
    return demo_mod.available()


def info() -> dict:
    return {
        "available": available(),
        "task": JUDGE_TASK,
        "scenarios": [
            {"name": k, "label": v["label"], "evidence": v["evidence"], "expect": v["expect"]}
            for k, v in SCENARIOS.items()
        ],
        "note": "Real OpenCV, real gate, a fixed plan and hand-placed zones. The model is never called.",
    }


def _never(*_a: Any, **_k: Any):
    raise RuntimeError("a judge scenario reached the model check; it must end in OpenCV")


def service() -> JobService:
    return JobService(
        plan_fn=lambda *a, **k: _plan(),
        verify_fn=_never,
        locate_fn=lambda *a, **k: list(ZONES_02),
        use_house_memory=False,
        use_research=False,
        use_perception=True,
    )


def run(name: str, on_block: Callable[[str, dict], None] | None = None) -> dict:
    """Walk one scenario end to end. Returns what happened, for the API and the page."""
    if name not in SCENARIOS:
        raise KeyError(name)
    sc = SCENARIOS[name]
    svc = service()
    tmp = store.jobs_dir() / "_uploads" / f"judge-start-{name}.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(demo_mod.photo_bytes("start"))
    state = svc.start(JUDGE_TASK, str(tmp))
    home = store.cards_dir(state.job_id) / "start.jpg"
    tmp.replace(home)
    state.start_photo = str(home)
    svc.put(state)
    store.trace(
        state.job_id,
        "judge",
        scenario=name,
        evidence=sc["evidence"],
        note="fixed plan, hand-placed zones, generated evidence photo; the model is never called",
    )
    svc.card(state, layout="photo")  # draws the zones; locate_fn is the fixed list

    evidence = store.cards_dir(state.job_id) / "evidence-01-01.jpg"
    cv2.imwrite(str(evidence), sc["make"](), [cv2.IMWRITE_JPEG_QUALITY, 90])
    if sc.get("probe"):
        # OpenCV decides the route and the job stops there: the next call would be the
        # model's two-photo check, which judge mode never makes.
        rep = svc.inspect_only(state, str(evidence))
        return {
            "scenario": name,
            "job_id": state.job_id,
            "expected": sc["expect"],
            "decision": rep.decision,
            "as_expected": rep.decision == sc["expect"],
            "reason": rep.reason,
            "instruction": rep.instruction,
            "route": rep.route,
            "ms_total": rep.ms_total,
            "llm_called": False,
            "verdict_source": None,
            "gate": {"blocked": None, "human_review": False,
                     "reason": "Not refused: the next call would be the model's two-photo check "
                               "(first photo + this one, same_place required). Judge mode stops here."},
            "images": {k: f"/api/jobs/{state.job_id}/perception/{_ref(p)}" for k, p in rep.artifacts.items()},
        }
    verdict = svc.verify(state, str(evidence))
    rep = state.perception[0]

    tools = build_tools(svc)
    gate = StepGate(state_for=svc.get, on_block=on_block, on_review=svc.review)
    res = run_tool_through_gate(gate, tools, "advance_step", {"job_id": state.job_id, "step_id": 1})
    if res.get("status") == "interrupt":
        content = res.get("content")
        message = content.get("message") if isinstance(content, dict) else str(content)
        store.trace(state.job_id, "gate_stop", reason=message, kind="human_review")
        gate_out = {"blocked": True, "human_review": True, "reason": message}
    else:
        gate_out = {"blocked": bool(res.get("cancelled")), "human_review": False, "reason": str(res.get("content"))}
    return {
        "scenario": name,
        "job_id": state.job_id,
        "expected": sc["expect"],
        "decision": rep.decision,
        "as_expected": rep.decision == sc["expect"],
        "reason": rep.reason,
        "instruction": rep.instruction,
        "ms_total": rep.ms_total,
        "route": rep.route,
        "llm_called": False,
        "verdict_source": verdict.source,
        "gate": gate_out,
        "images": {k: f"/api/jobs/{state.job_id}/perception/{_ref(p)}" for k, p in rep.artifacts.items()},
    }


def _ref(path: str) -> str:
    """``.../perception/step-01-try-01-match.jpg`` -> ``step-01-try-01-match``."""
    name = path.rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".jpg") else name
