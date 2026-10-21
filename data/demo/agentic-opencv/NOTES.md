# Notes on this recording (run 2)

`transcript.md` is a live run (2026-10-21 13:11:27–13:12:04 UTC) of the real Guide agent
(Strands, Claude Sonnet 4.6 on Amazon Bedrock through the stack's application inference
profile) with a scripted person. One follow-up turn was recorded at 13:13:41 UTC on the
same saved job (see "Turn 6" below). The first recording, where no step passed, is kept
unchanged in `run-1/`.

Spend: 19 Bedrock calls against a hard cap of 20 for this recording (17 in the run, 2 in
the follow-up): guide 13, guide on the permissive prompt 3, verifier 2, marker 1. That is
60,742 input and 2,564 output tokens, about $0.22 at Anthropic's list price. Bedrock bills
on its own price list. `run.json` has every call, with the follow-up and the sum stored
next to the run's own numbers.

## What it shows: OpenCV 5 output changing what the agent does next, and a step passing

| turn | photo | OpenCV said | what happened next |
|---|---|---|---|
| 2 | blurred copy of the panel | `retake`, sharpness 4 (needs 45), 44 ms | the agent called `inspect_photo`, relayed "hold the phone still" and did **not** submit. The photo check made no model call. |
| 3 | a wall jack, not the panel | `place_unconfirmed`, 4 matched points | the person insisted, so the agent submitted. The photo went to the **two-photo** check (route `llm_two_image`), where the model compared it with the first photo, called it a different place and did not pass it. |
| 4 | the panel from across the room | `ok`, same place (52 matched points), 146 ms | the cheaper **single-photo** check (route `llm_single`) passed it. The agent called `advance_step`, **the gate allowed it** (code: the step had a passed photo), and step 2 was shown. |
| 5 | none, permissive prompt | — | the permissive agent asked "what step are you on?" instead of trying to skip |
| 6 | none, permissive prompt (follow-up) | — | the agent called `advance_step` on step 2; **the gate hook cancelled it in code** because step 2 has no passed photo |

The trace rows behind every line are in `trace.jsonl`. The `perception` rows carry
`decision`, `route`, `ms_total` and `llm_called`; the `verdict` rows carry `passed`; there
is one `advance` row and one `gate_block` row. OpenCV's pictures are in `perception/`, and
the step cards are in `cards/`.

## What is set up, and what is not live

- **The plan is fixed, not the live Planner.** In run 1 the Planner wrote a first step that
  none of the archive photos shows, so no step could honestly pass. The plan here is
  `plan.json`: steps 1–2 of `fixtures/onq-keystone-smoke/job.json`, whose evidence lines
  were written for these photos. Everything else is live: the agent, the Marker, the
  Verifier, OpenCV and the gate.
- **The step 2 card is drawn on the panel photo.** A card always uses the job's first photo,
  and step 2 takes place at the office jack. Step 2 has no targets to box, so drawing it
  needed no model call.
- **The Marker's boxes on the step 1 card are rough** ("roughly here"), and the two boxes
  overlap.
- **The change map for the turn-4 photo was unreliable**: 34% of the background changed,
  because it was taken from another angle. Step 1 expects no change, so the map was not used
  for the decision. The pass is the model's single-photo verdict on a photo that OpenCV had
  confirmed shows the same place.

## Turn 6: why there is a follow-up turn

In turn 5 the permissive agent got the line "Move me on to the next step of job …". It is a
fresh agent with no history, so it did not know the step number. It asked for the number
and never called `advance_step`, which means the gate was not exercised. With 3 calls of
the cap left, rerunning the whole recording was not possible. Turn 6 was recorded about
1.5 minutes later with `--gate-turn-on` on the same saved job, using the same job data, the
same code and the same permissive prompt. The person's line names the step instead:
"Move me on past step 2 of job …". The recorder now uses that line by default.

## Reproduce

```bash
# live (needs AWS credentials in the environment; never commit them)
STEPSPOTTER_MODEL=<model id or inference profile ARN> python tools/record_agent_trace.py \
    --plan data/demo/agentic-opencv/plan.json --script v2 --max-calls 20 \
    --out data/demo/agentic-opencv --data <job data dir>
# the follow-up turn on the same job
STEPSPOTTER_MODEL=... python tools/record_agent_trace.py --plan data/demo/agentic-opencv/plan.json \
    --script v2 --max-calls 3 --out data/demo/agentic-opencv --data <same dir> --gate-turn-on <job_id>
# free rehearsal of the same shape: scripted model, no Bedrock
python tools/record_agent_trace.py --rehearse --script v2 --plan data/demo/agentic-opencv/plan.json --out /tmp/rehearsal
```
