"""Verifier — does this photo actually prove the step was done?

This is the half of the system that earned its keep in spike A: 8/8 correct, and
critically 4/4 on claims about things that were not in the frame at all. It refused
and named the absence ("no circuit breaker is visible in this photo") instead of
inventing one. The system prompt line that produces that behaviour is the one about
returning passed=false when the subject is not visible — do not soften it.

No confidence score is returned or used. Spike A ran the same call twice and got
0.82 then 0.20 while the boolean stayed put; a threshold on that number would flip
a person's route between two identical runs.
"""

from __future__ import annotations

from pydantic import Field

from stepspotter.models import Step, StepVerdict
from stepspotter.vision import ask_typed, load_photo


class TwoPhotoVerdict(StepVerdict):
    """The verdict when OpenCV could not confirm the place: the model sees both photos."""

    same_place: bool = Field(
        description="true only if the SECOND photo clearly shows the same place or the same "
        "object as the FIRST photo — another angle, closer, further, or with parts moved by "
        "the work all still count. false if it shows somewhere else, or you cannot tell."
    )


TWO_PHOTO_NOTE = """You get TWO photos. The FIRST is the person's starting photo of the place
this step is about. The SECOND is the photo they just sent as evidence. OpenCV could not
line the two up, which happens with a new angle or moved cables as well as with a photo
of somewhere else — so decide same_place yourself, by looking. passed=true requires the
step to be done AND visible in the SECOND photo AND same_place=true."""

VERIFIER_SYSTEM = """You check whether a photo proves that one repair step was done.
You are strict, and you are on the side of the person's safety, not their impatience.

passed=true ONLY when the photo itself clearly shows what was asked for.
passed=false, saying the evidence is not visible, when:
 - the thing being checked is not in the frame
 - it is out of focus, too dark, or hidden behind something
 - the photo shows a different object or a different place
 - you are unsure
Never assume anything outside the frame. Never accept the person's word that it is
done: the photo is the only thing you are allowed to believe. If they said they did
it and the photo does not show it, that is passed=false.

Set stop=true, on top of your pass/fail answer, if the photo shows a hazard: heat
damage, scorching, melted plastic, a swollen battery, water on wiring, smoke, or
bare live conductors. A hazard stops the whole job for a person to look at.

reason is ONE short sentence in plain words, naming what you can or cannot see. The
person reads it directly, so write it to them.

Boxes are normalized [0,1] with (0,0) at the TOP-LEFT. Box only what you can see."""


def verify_step(
    step: Step,
    photo_path: str,
    model_id: str | None = None,
    context: str | None = None,
    zone_crop: bytes | None = None,
    reference_photo: str | None = None,
) -> StepVerdict:
    """Judge one photo against one step's evidence requirement.

    ``context`` is the OpenCV layer's findings on this photo (sharpness, whether it lines
    up with the first photo, what changed where), and ``zone_crop`` this photo warped
    onto the first photo and cropped to the work zone. Both are labelled as context:
    the decision stays the model's, and the gate's. Neither is sent unless passed.

    ``reference_photo`` switches to the two-photo check (route ``llm_two_image``): the
    person's first photo goes first, the evidence second, and the answer must fill
    ``same_place``. Used when OpenCV could not confirm the evidence shows the same place.
    """
    jpeg, _img = load_photo(photo_path)
    prompt = (
        f"The person was asked to do step {step.id}: {step.title}\n"
        f"  What they had to do: {step.action}\n"
        f"  What this photo must show: {step.evidence_required}\n\n"
        "Does this photo prove that step is done? Answer passed=true only if the photo "
        "clearly shows it. If the subject is not visible in this photo, answer "
        "passed=false and say so."
    )
    if context:
        prompt += "\n\n" + context
    if reference_photo:
        ref_jpeg, _ref = load_photo(reference_photo)
        two = ask_typed(
            VERIFIER_SYSTEM + "\n\n" + TWO_PHOTO_NOTE,
            prompt + "\n\nThe FIRST image below is their starting photo; the SECOND is the evidence.",
            TwoPhotoVerdict,
            ref_jpeg,
            model_id,
            extra=[("The SECOND photo — the evidence they just sent:", jpeg)],
        )
        verdict = StepVerdict.model_validate(two.model_dump())
        verdict.same_place = bool(two.same_place)
        verdict.step_id = step.id
        verdict.source = "llm"
        verdict.route = "llm_two_image"
        if not verdict.same_place:
            verdict.passed = False  # the step cannot be proven on a photo of somewhere else
        return verdict
    extra = None
    if zone_crop is not None:
        extra = [
            (
                "Context from OpenCV: the photo above, lined up with the person's first "
                "photo and cropped to the work zone, so you can see it closer. Judge the "
                "photo above; this crop only shows where to look.",
                zone_crop,
            )
        ]
    verdict = ask_typed(VERIFIER_SYSTEM, prompt, StepVerdict, jpeg, model_id, extra=extra)
    verdict.step_id = step.id  # the model does not get to renumber the step it judged
    verdict.source = "llm"
    verdict.route = "llm_single"
    return verdict
