"""The shapes the perception layer adds to a job: what the model sees, what a job stores."""

from __future__ import annotations

import json

from strands.tools.structured_output import convert_pydantic_to_tool_spec

from stepspotter.models import EvidenceRecord, JobState, Plan, Step, StepVerdict
from stepspotter.perception.inspect import STUCK_AFTER, apply_stuck_rule
from stepspotter.perception.models import PerceptionReport


def test_the_planner_is_asked_whether_each_step_changes_something():
    spec = json.dumps(convert_pydantic_to_tool_spec(Plan))
    assert "expects_change" in spec
    assert "confirms, inspects or tests" in spec


def test_the_model_cannot_claim_to_be_opencv():
    """``source`` is set by the code; it is not in the schema the verifier fills in."""
    props = convert_pydantic_to_tool_spec(StepVerdict)["inputSchema"]["json"]["properties"]
    assert "source" not in props
    assert StepVerdict(step_id=1, passed=True, reason="ok").source == "llm"


def test_old_steps_and_old_jobs_still_load():
    """A plan or a saved job from before this layer existed carries none of the new fields."""
    step = Step(id=1, title="t", action="a", evidence_required="e")
    assert step.expects_change is None
    old = {
        "job_id": "job-20260909-090000-aaaa",
        "task": "t",
        "start_photo": "p.jpg",
        "plan": {"job_title": "j", "safety_class": "diy_ok", "steps": [step.model_dump()]},
        "verdicts": {"0": {"step_id": 1, "passed": False, "reason": "r"}},
    }
    state = JobState.model_validate_json(json.dumps(old))
    assert state.perception == {} and state.evidence == [] and state.llm_calls_saved == 0
    assert state.verdicts[0].source == "llm"


def test_perception_reports_round_trip_with_int_keys():
    rep = PerceptionReport(decision="retake", reason_code="blurry", reason="r", instruction="i")
    state = JobState(
        job_id="job-20260909-090000-aaaa",
        task="t",
        start_photo="p.jpg",
        plan=Plan(job_title="j", safety_class="diy_ok", steps=[]),
        perception={0: rep},
        perception_streak={0: 2},
        evidence=[EvidenceRecord(step=0, photo="e.jpg", passed=False, source="opencv")],
    )
    back = JobState.model_validate_json(state.model_dump_json())
    assert back.perception[0].decision == "retake" and back.perception[0].blocks
    assert back.perception_streak == {0: 2}
    assert back.evidence[0].source == "opencv"


def test_the_stuck_rule_lets_a_photo_through_only_after_k_blocks_and_never_a_replay():
    def rep(decision: str) -> PerceptionReport:
        return PerceptionReport(decision=decision, reason_code=decision, reason="r")

    assert not apply_stuck_rule(rep("retake"), STUCK_AFTER - 1).overridden
    for d in ("retake", "wrong_place", "no_change"):
        out = apply_stuck_rule(rep(d), STUCK_AFTER)
        assert out.overridden and not out.blocks, d
    for d in ("replay", "touched_avoid"):
        out = apply_stuck_rule(rep(d), STUCK_AFTER + 5)
        assert not out.overridden and out.blocks, d
