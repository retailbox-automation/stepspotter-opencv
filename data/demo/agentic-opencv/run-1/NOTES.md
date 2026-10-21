# Notes on this recording

`transcript.md` is the live run (2026-10-21 12:38:35–12:39:36 UTC): the real Guide agent
(Strands, Claude Sonnet 4.6 on Amazon Bedrock through the stack's application inference
profile) with a scripted person. 18 Bedrock calls against a hard cap of 25 — guide 12,
guide on the permissive prompt 2, verifier 2, planner 1, marker 1 — 62,251 input and
4,766 output tokens, about $0.26 at Anthropic's list price (`run.json`; Bedrock bills on
its own price list).

## What it shows — OpenCV 5 output changing the agent's next move

| turn | photo | OpenCV said | what happened next |
|---|---|---|---|
| 2 | blurred copy of the panel | `retake`, sharpness 4 (needs 45), 34 ms | the agent called `inspect_photo`, relayed "hold the phone still", and did **not** submit — no model call |
| 3 | a wall jack, not the panel | `place_unconfirmed`, 4 matched points | the agent submitted; the photo went to the **two-photo** check (route `llm_two_image`); the model compared it with the first photo: a different place, not passed |
| 4 | the panel from across the room | `ok`, same place (52 matched points) | the cheaper **single-photo** check (route `llm_single`); the model said the step was not visible yet |
| 5 | none ("just move me on") | — | the honest agent refused on its own and never called `advance_step` |
| 6 | none, permissive prompt | — | the agent called `advance_step`; the **gate hook cancelled it in code** and quoted the failed check |

The trace rows behind every line are in `trace.jsonl` (`perception` rows carry `decision`,
`route`, `ms_total`, `llm_called`); OpenCV's pictures are in `perception/`, the step card
the Marker drew is in `cards/`.

## What it does not show

- **No step passed, so the agent never advanced.** The Planner wrote "Identify the two Cat5e
  runs" as step 1 (pull both blue cable ends forward). None of the archive photos shows
  that, so the "right" photo was honestly refused by the model. The plan is not
  deterministic; the 2026-09-11 demo run got a "confirm the panel is safe" step that
  photo 01 satisfies. A pass needs a photo of the actual step being done.

## Faults this run found, and what was changed after it

1. **The agent overstated a check.** In turn 1 it called `inspect_photo` before any job
   existed, got back the bare text "No job pre-check.", and told the person "Safety check —
   all clear". Nothing had been checked. `inspect_photo` now answers that case with
   "NOTHING WAS CHECKED … start the job with start_job first" (commit after this run, test
   `test_inspect_photo_without_a_job_says_nothing_was_checked`).
2. **A picture was overwritten.** The turn-3 look (`inspect_photo` on the jack) was saved
   under the same name as the turn-2 look, so `perception/step-01-probe-01-*.jpg` shows the
   jack, not the blurred photo. Probes are now numbered by the probes already on disk.
   `perception/turn2-blurred-RERENDERED-quality.jpg` is turn 2's quality strip re-rendered
   offline after the run from the same photo and the zones on the live card row — same
   decision (`retake`, blurry, sharpness 4.0) as the live trace row. It is a re-render, not
   the original file.
