# StepSpotter × OpenCV 5

<img src="docs/report/prepared-by.png" alt="prepared by Mikhail" height="23">

**A home-repair assistant that will not take your word for it.** You get one step at a
time on a photo of your own thing, and the next step opens only when a photo proves the
last one was done. OpenCV 5 checks every evidence photo **before** any model sees it —
and what it finds changes what the system does next.

Entry to the **OpenCV AI Competition 2026, powered by AWS**. Live on AWS App Runner:
**<https://utgfmpcgxf.us-east-1.awsapprunner.com>** · technical report:
[`docs/REPORT.md`](docs/REPORT.md) (PDF: [`docs/report/StepSpotter-OpenCV26-report.pdf`](docs/report/StepSpotter-OpenCV26-report.pdf))
· video: {{VIDEO:url}}

## In 60 seconds

**What it does.** Name a small job (a network jack, a low-voltage panel, a
pressure-washer assembly) and send a photo. StepSpotter, a Strands Agents app on Amazon
Bedrock, plans the job, draws step 1 on your photo — where to work, what not to touch,
what the next photo must show — and waits. The `advance_step` tool is cancelled in code
by a Strands `BeforeToolCall` hook until a photo passes.

**Why OpenCV changes the decision.** A model looking at one photo cannot tell a blurred
photo from an unfinished step, the panel you started on from a similar one, or a change
in the work zone from a change in the zone you were told not to touch. OpenCV 5 can, in
tens of milliseconds and without a model:

| OpenCV sees | what happens next |
|---|---|
| blur, dark, glare, the part out of frame | refused **without a model call**, with one instruction ("hold still", "more light", "step back") |
| the same photo sent again | refused without a model call |
| nothing changed in the work zone | refused without a model call |
| something changed in the do-not-touch zone | the gate stops the run and asks a person to approve (`interrupt`) |
| it cannot line the photo up with your first photo | the model gets **both** photos and must answer `same_place`; the gate needs `true` |
| it all checks out | the model checks the photo, with OpenCV's aligned crop of the work zone |

Policy and every threshold: [`docs/PERCEPTION.md`](docs/PERCEPTION.md).

## For judges

1. Open <https://utgfmpcgxf.us-east-1.awsapprunner.com> (phone or desktop).
2. Press **"For judges: the OpenCV checks, no model"**. Four buttons run real jobs
   through the real gate on photos shipped in the repo; the model is never called:
   - *Blurry photo* → `retake` with one instruction, gate refuses.
   - *Photo OpenCV cannot line up* → `place_unconfirmed`, route `llm_two_image` (stops
     before the model call).
   - *The first photo sent again* → `replay`, gate refuses.
   - *Change in a do-not-touch zone* → `touched_avoid`, the run stops for a person; the
     **"I am the person — I checked it, carry on"** button approves.
3. Press **why** (top right) → **Everything it did**: the row *OpenCV photo check (code,
   not the model)* shows the decision, the time and "no model call needed", with the
   match lines and the change heatmap.
4. For a full job with the model: **Try a demo job**, then *Send the wrong photo* and
   *Send the right photo*.

The service is capped at 6 jobs and 30 photo checks per day for everyone together (the
four judge buttons count as photo checks), to keep it inside its budget. If the page says the demo
"has run its … for today", everything below runs offline. Exact steps and expected results:
[`docs/SUBMISSION.md`](docs/SUBMISSION.md) § Testing instructions.

{{SCREENSHOT:trace — docs/screens/trace-opencv.png}}

## Architecture

![Architecture: phone → App Runner (FastAPI, OpenCV 5 perception, Verifier, StepGate, job state) → Amazon Bedrock; CloudWatch, SNS and Budget; CodeBuild and ECR](docs/diagrams/architecture.png)

![Agent workflow: perception → route → action](docs/diagrams/agent-workflow.png)

Interactive versions with every node's source file and line:
[`docs/diagrams/architecture.html`](docs/diagrams/architecture.html),
[`docs/diagrams/agent-workflow.html`](docs/diagrams/agent-workflow.html).

## Results

From [`docs/EVAL.md`](docs/EVAL.md); every number there has the command that reproduces it.

| | A: model, 1 photo | A′: model, 2 photos | B: OpenCV only | C: OpenCV → model |
|---|---:|---:|---:|---:|
| bad evidence caught | {{EVAL:A_caught}} | {{EVAL:A2_caught}} | {{EVAL:B_caught}} | {{EVAL:C_caught}} |
| good evidence refused | {{EVAL:A_false}} | {{EVAL:A2_false}} | {{EVAL:B_false}} | {{EVAL:C_false}} |
| model calls | {{EVAL:A_calls}} | {{EVAL:A2_calls}} | 0 | {{EVAL:C_calls}} |
| latency p50 / p95 | {{EVAL:A_ms}} | {{EVAL:A2_ms}} | {{EVAL:B_ms}} | {{EVAL:C_ms}} |

Failures are published with pictures in `docs/EVAL.md` and `docs/PERCEPTION.md`.

## Run it

Python 3.12. Pinned: `opencv-python-headless==5.0.0.93`, `numpy==2.5.4`,
`strands-agents==1.55.0` (`pyproject.toml`); the cloud build runs `import cv2` inside the
built image and prints its version (`infra/buildspec.yml`).

```bash
git clone https://github.com/retailbox-automation/stepspotter-opencv && cd stepspotter-opencv
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
tools/fetch_models.sh                                    # YuNet face detector, SHA256-checked

# test — offline, no AWS account
.venv/bin/python -m pytest -q -m "not integration"       # {{TESTS:passed / skipped at the final commit}}

# eval — OpenCV only, no AWS account
.venv/bin/python eval/build_set.py && .venv/bin/python eval/run.py --config opencv

# run the app (the model steps need Bedrock access to Claude Sonnet 4.6 in us-east-1)
.venv/bin/stepspotter serve --port 8137

# deploy to AWS — one CloudFormation stack; creates billable resources
BUDGET_EMAIL=you@example.com ALERT_EMAIL=you@example.com infra/deploy.sh --yes
infra/destroy.sh --yes                                   # removes it
```

Deploy details, measured durations and cost: [`docs/DEPLOY.md`](docs/DEPLOY.md).
Operations, spend caps, kill switch, logs and privacy: [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Where OpenCV changes the decision in code

| what | where |
|---|---|
| OpenCV runs first; a blocked photo never reaches the model | `src/stepspotter/guide.py:396`, `:421` |
| the route picks the one-photo or the two-photo model check | `src/stepspotter/perception/models.py:163`, `src/stepspotter/guide.py:434` |
| fail closed without `same_place=true` | `src/stepspotter/guide.py:440`, `src/stepspotter/gate.py:153` |
| the gate cancels `advance_step` on a blocking report | `src/stepspotter/gate.py:141`, `:118` |
| a change in a do-not-touch zone → `interrupt("human_review")` | `src/stepspotter/gate.py:91` |
| the agent's own OpenCV tool (`inspect_photo`) | `src/stepspotter/guide.py:654` |
| the OpenCV 5 checks | `src/stepspotter/perception/` (quality, scene, change, frames, privacy) |

## Documents

[`docs/REPORT.md`](docs/REPORT.md) technical report ·
[`docs/PERCEPTION.md`](docs/PERCEPTION.md) the OpenCV layer ·
[`docs/EVAL.md`](docs/EVAL.md) evaluation ·
[`docs/DEPLOY.md`](docs/DEPLOY.md) / [`docs/OPERATIONS.md`](docs/OPERATIONS.md) AWS ·
[`docs/PLATFORM-FINDINGS.md`](docs/PLATFORM-FINDINGS.md) what we learned about OpenCV 5,
AWS and Strands ·
[`docs/AI-USE.md`](docs/AI-USE.md) how AI was used ·
[`docs/SUBMISSION.md`](docs/SUBMISSION.md) the Devpost texts ·
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) the agent roles from the first build.

## Safety

For low-voltage, low-consequence work only. The planner refuses mains wiring, gas,
roofing and structural work with an empty step list (`src/stepspotter/planner.py:26`).
That refusal is a model judgement, not a certified hazard classifier.

## Disclosure

StepSpotter was built on 9–14 September 2026 for the AWS "Agents for Humans" hackathon
(Devpost), where it won the Everyday Agents Bronze award (announced 14 October 2026), and
was also submitted to the AI Builders hackathon (judging not finished). That code is
public at <https://github.com/retailbox-automation/stepspotter> (commit `80979af`) and is
imported here as the first commit, `295e3f3`, with the text copied from manufacturers'
manuals removed. Everything OpenCV 5 — the perception package, the gate and verifier
integration, face blurring, the evaluation harness, the AWS stack and the documents — was
built on 21–24 October 2026 in this competition's window: commits `9cc6ca1` through
{{FINAL:head commit}}. The Official Rules have no clause on previously submitted projects;
the nearest is «From August 26 through October 26, teams will build, evaluate, document,
and submit their final projects.» AI coding assistants were used; see
[`docs/AI-USE.md`](docs/AI-USE.md).

## Licence

Code: MIT ([`LICENSE`](LICENSE)). The MIT licence covers this repository's own code and
our own photos only. Third-party files keep their own terms: the public-domain face test
photo ([`tests/fixtures/ATTRIBUTION.md`](tests/fixtures/ATTRIBUTION.md)), the public
photos used in the evaluation ([`eval/cases/public/ATTRIBUTION.md`](eval/cases/public/ATTRIBUTION.md)),
and the YuNet face detector (MIT, opencv_zoo), which is downloaded at build time and not
committed.
