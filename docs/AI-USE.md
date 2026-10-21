# How AI was used

Two different things: AI inside the product, and AI used to build it.

## In the product, at runtime

The service calls Claude Sonnet 4.6 on Amazon Bedrock through a tagged application
inference profile (`infra/template.yaml:355`); the instance role may invoke that model
and nothing else (`infra/template.yaml:409`).

| where | what the model does | why a model | file |
|---|---|---|---|
| Planner | decides first whether the job needs a licensed trade (then: no steps), otherwise writes the steps for the thing in the person's photo | turning a photo and a sentence into ordered, plain-language steps | `src/stepspotter/planner.py` |
| Marker | finds the work zone and the do-not-touch zones on the start photo as boxes | locating named parts in an arbitrary photo | `src/stepspotter/marker.py` |
| Verifier, one photo | judges whether the photo shows the step done; gets OpenCV's aligned crop of the work zone as context | "is the connector seated?" is a judgement about content, not geometry | `src/stepspotter/verifier.py:61` |
| Verifier, two photos | when OpenCV cannot confirm the place, compares the first photo and the evidence and must answer `same_place` | OpenCV measured that it cannot tell a re-shot from another room on our photos | `src/stepspotter/verifier.py:91` |
| Guide agent (agent mode `/agent`, `stepspotter chat`) | decides which tool to call next — `inspect_photo`, `submit_photo`, `advance_step`, `escalate` — and talks to the person; at most 8 tool calls per turn on the web | orchestrating a conversation around the photo checks; the gate under every tool call still decides | `src/stepspotter/guide.py:773`, `src/stepspotter/web/agent_mode.py` |
| Questions in the chat | answers a question typed by the person, with **no tools**, so it cannot move the job | conversation | `src/stepspotter/web/ask.py` (Strands default model, `global.anthropic.claude-sonnet-4-6` in 1.55.0) |

What the model does **not** decide:

- whether a photo is sharp, lit, framed, the same photo again, or changed in the right
  zone — OpenCV 5 decides those, before the model, and a photo it refuses never reaches
  the model (`src/stepspotter/guide.py:405`);
- whether the person may move on — the `StepGate` hook does, in code
  (`src/stepspotter/gate.py`); it cancels `advance_step` without a passing verdict, without
  `same_place=true` when OpenCV could not confirm the place, or on a stored OpenCV block,
  and it stops the run for a person when a do-not-touch zone changed.

The model's verdict reasons are shown to the person as the model wrote them; each trace
row says whether a verdict came from OpenCV or from the model (`source`, `route`).

## In development

This entry was written with AI coding assistants: Claude Code agents wrote most of the
code, tests, infrastructure templates, evaluation harness, diagrams and documents, working
in parallel lanes under the author's direction. The same applies to the original StepSpotter
build that this entry imports (see Disclosure in `README.md`).

What the author, Mikhail Oskola, did:

- chose the product and its one rule — the next step opens only on a photo that proves
  the last one — and the decision to build the OpenCV layer around that gate;
- took the photos of his own panel and wall jacks that the tests and the evaluation use,
  and gave permission to publish them;
- made the decisions that leave the machine: entering the competition, publishing the
  repository, the AWS spend ceiling and the caps, what may appear in the report and the
  video;
- reviewed the results, including the change of policy after the evaluation showed
  OpenCV refusing honest re-shots.

The competition rules say that using an AI coding assistant to write the entry does not
by itself make it an agentic workflow; our claim for the Agentic Vision award rests on the
runtime loop above, not on how the code was written.
