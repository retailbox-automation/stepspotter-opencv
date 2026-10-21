# Devpost submission — OpenCV AI Competition 2026 (texts ready to paste)

Form: opencv26.devpost.com. Fields and their ids come from the Devpost MCP
`get_submission_requirements` (`docs/opencv26/RULES-LIVE-2026-10-21.md` in the
hackathon project). Placeholders in double braces are filled before Submit:
`{{VIDEO:url}}`, `{{FINAL:head commit}}`, `{{ZIP:…}}`; every
evaluation number is from `docs/EVAL.md` / `eval/results/*.json` at `750d152`. Submit is pressed by Mikhail only.

## Project name

StepSpotter

## Tagline (≤ 200 characters)

A home-repair assistant that won't take your word for it: OpenCV 5 checks every proof photo before the AI does, and decides what happens next.

(141 characters)

## About the project

### Inspiration

I bought my first house in Orlando and realised I didn't know how to do the simplest
things around it. What works for me is my phone: someone marks up my own photo, one
step at a time, "not this one, that one". StepSpotter does that, with one rule I
insisted on — it can't take my word that a step is done; it has to see it.

The first version (built for AWS "Agents for Humans", see Disclosure) asked a vision
model to judge one photo. It worked, and it had three blind spots no prompt fixes: a
blurred or dark photo, a photo of the wrong place or the same "before" photo sent
again, and a change in the zone the step said not to touch. Each of those is a question
about pixels and geometry, not language. That is OpenCV's job.

### What it does

You name a small job and send a photo. StepSpotter plans it and draws step 1 on your
photo: where to work, what not to touch, what the next photo must show. The next step
stays locked — a Strands `BeforeToolCall` hook cancels the `advance_step` tool in code —
until a photo proves this one.

Every evidence photo now goes through OpenCV 5 first, and its output changes what
happens next:

- blurred, dark, glare, the part out of frame → refused **without a model call**, with
  one instruction ("hold still", "more light", "step back so the splitter is in frame");
- the same photo sent again → refused, no model call;
- nothing changed in the work zone → refused, no model call;
- something changed in the do-not-touch zone → the run stops and a person approves;
- OpenCV can't line the photo up with your first photo → the model gets **both** photos
  and must answer `same_place`; the gate won't open without `true`;
- all clear → the model checks the photo with OpenCV's aligned crop of the work zone.

Faces in a photo are blurred before it is stored or sent anywhere. A video works too:
OpenCV picks the sharpest frame that shows the right place.

In agent mode (`/agent`) the Strands Guide agent decides which tools to call — it can ask
OpenCV about a photo before submitting it — and every answer shows its tool calls,
OpenCV's decision and any refusal by the gate.

### How we built it

- **OpenCV 5.0.0** (`opencv-python-headless==5.0.0.93`): Laplacian sharpness per tile,
  histogram exposure, connected-component glare; SIFT on CLAHE luminance,
  `BFMatcher.knnMatch` and `findHomography(USAC_MAGSAC)` with a sanity check on the
  homography for "same place"; near-identity homography plus aligned difference for
  "already sent"; `warpPerspective`, CLAHE in Lab, `absdiff` and morphology against the
  noise floor outside all zones for "what changed where"; `VideoCapture` keyframes;
  `FaceDetectorYN` (YuNet) for faces.
- **Strands Agents** on **Amazon Bedrock** (Claude Sonnet 4.6): the planner, the zone
  marker and the verifier with typed outputs; the gate is a `BeforeToolCall` hook that
  sets `cancel_tool` or raises `interrupt("human_review")`.
- **AWS**: one CloudFormation stack — App Runner (one x86_64 instance), a tagged Bedrock
  application inference profile, least-privilege IAM, CloudWatch metric filters on the
  JSON perception trace (decisions, model calls saved, latency), three alarms, a
  dashboard, an SNS alert topic and a $15 Budget; CodeBuild builds the image from
  `git archive` and checks `import cv2` inside it; ECR by digest. One command deploys,
  one removes.
- An evaluation harness that runs the same gate code in four configurations — model on
  one photo, model on two photos, OpenCV only, OpenCV then model — with a hard cap on
  model calls.

### Challenges we ran into

- **Real re-shots don't line up.** On our own photos, a photo of the same panel from
  another angle kept 4–8 SIFT inliers, exactly the range of photos of different rooms.
  No threshold separates them, and our first policy refused 3 of 5 honest re-shots. We
  changed the policy: when OpenCV cannot confirm the place, it doesn't refuse — it sends
  both photos to the model and makes the gate demand `same_place=true`.
- **Parallax.** Aligning a real re-shot of a cluttered panel left 37 % of the frame
  "changed". Change is now read against the noise floor outside all zones, and a noisy
  map decides nothing.
- **A false positive must never trap a person.** After three OpenCV refusals in a row on
  one step, the next photo goes to the model with OpenCV's findings attached.
- **White things look like glare.** The first evaluation run showed OpenCV refusing 8 of
  56 ordinary real photos — white basins, a white wall, a flashlight hot spot. Glare now
  refuses a photo only when it newly covers the work zone, and overexposure is judged
  against the first photo; 0 of 56 are refused now. The price: some synthetic glare now
  goes on to the model.
- App Runner runs x86_64 images only, so the Graviton plan changed; the build now checks
  the image architecture before pushing.

### Accomplishments that we're proud of

- OpenCV output decides the next action — no model call, a one-photo or two-photo model
  call, a cancelled tool, or a person's approval — and every step of that is in the
  trace and covered by an offline test.
- On 50 held-out cases, the model on one photo refused 11 of 33 bad photos; our gate
  refused 30 of 33, wrongly refused 2 of 15 good ones (as many as the model alone, leaving
  out 2 mislabelled pairs), made 31 model calls for 54 checks instead of 54 and cost $0.89
  per 100 checks instead of $1.27. Shown both photos, the model alone matches us on
  look-alikes of another place; our edge is a resent photo, no change, a change in a
  do-not-touch zone, overexposure and a cut-off work zone. Small sample: 2 cases per
  synthetic class, one run.
- A live recording of the real agent (`data/demo/agentic-opencv/`): a blurred photo is
  refused in 44 ms without a model call, a photo of another room goes to the two-photo
  check and fails, the right photo passes and the gate lets the agent move on, and a skip
  attempt is cancelled by the gate.
- We published the failures next to the successes, including the policy that refused
  honest photos and why we dropped it.

### What we learned

Most "is this step done?" failures are not about understanding the photo; they are about
whether this is the right photo at all. Geometry answers that cheaply and the same way
every time — and where geometry can't answer, the honest move is to say so and ask a
better question, not to refuse.

### What's next

- A blind test on photos of a real repair that no threshold was tuned on.
- The misses we know about: mirror-image look-alikes, a resent photo with a mark drawn on
  it, a smeared video frame that passes the blur check.
- Segmentation instead of boxes for the work and do-not-touch zones.
- Job state outside the instance, so a job survives a redeploy.

### Disclosure

StepSpotter was built on 9–14 September 2026 for the AWS "Agents for Humans" hackathon on
Devpost, where it won the Everyday Agents Bronze award (announced 14 October 2026). It was
also submitted to the AI Builders hackathon, whose judging has not finished. That code is
public at github.com/retailbox-automation/stepspotter (commit 80979af) and is imported
into this repository as its first commit (295e3f3), with the text copied from
manufacturers' manuals removed. Everything OpenCV 5 — the perception package, its
integration into the gate and the verifier, face blurring, the evaluation harness, the
AWS stack, the diagrams and the report — was built on 21–24 October 2026, in this
competition's window: commits 9cc6ca1 through {{FINAL:head commit}}. We found no clause in
the Official Rules about previously submitted projects; the nearest is «From August 26
through October 26, teams will build, evaluate, document, and submit their final
projects.» The code was written with AI coding assistants (docs/AI-USE.md); the product
uses Claude Sonnet 4.6 on Amazon Bedrock at runtime.

## Built with

opencv · python · aws-app-runner · amazon-bedrock · claude-sonnet · strands-agents ·
aws-cloudformation · amazon-cloudwatch · aws-codebuild · amazon-ecr · aws-budgets ·
amazon-sns · fastapi · numpy · pydantic · sift · yunet

(Devpost's "Built with" widget splits tags on spaces — enter each as one word with hyphens.)

## Repository URL (field 28209, required)

https://github.com/retailbox-automation/stepspotter-opencv

## Testing instructions (field 28210, required)

```
LIVE APP (no login, no install): https://utgfmpcgxf.us-east-1.awsapprunner.com
Works on a phone or a desktop browser.

A. THE OPENCV BRANCHES - NO MODEL CALL (about 2 minutes)
1. On the first screen press "For judges: the OpenCV checks, no model". Four buttons appear.
   Each one starts a real job, sends a photo generated from the photos shipped in the repo,
   and runs it through the real OpenCV layer and the real gate. The model is never called
   (the verifier in this mode raises an error if it is ever reached).
2. "Blurry photo -> retake, with one instruction"
   Expected: decision retake, the reason with the measured sharpness, ONE instruction
   (hold the phone still), the time in milliseconds, "no model call needed", and the gate
   refusing to move on.
3. "The first photo sent again -> blocked"
   Expected: decision replay (the photo was re-encoded and resized, and is still caught),
   gate refuses, no model call.
4. "Change in a do-not-touch zone -> a person approves"
   Expected: decision touched_avoid; the run stops for a person (interrupt human_review),
   not a plain refusal. Press "I am the person - I checked it, carry on" to approve; the
   step still needs a photo that passes.
5. "Photo OpenCV cannot line up -> the two-photo check"
   Expected: decision place_unconfirmed, route llm_two_image: OpenCV does not refuse it, it
   decides that the next call is the model's two-photo check (first photo + this one, must
   answer same_place). Judge mode stops before that call.

B. READ THE TRACE
6. Press "why" (top right) -> "Everything it did". The row "OpenCV photo check (code, not
   the model)" shows the decision, the time and whether a model call was needed, with the
   pictures OpenCV made: matched points between the two photos, the change heatmap with the
   zones, the quality bars.

C. ONE FULL JOB WITH THE MODEL (about 2 minutes, uses Amazon Bedrock)
7. Reload the page, press "Try a demo job". The planner (Claude Sonnet 4.6) writes the steps
   for a real photo of a structured-wiring panel and draws step 1.
8. Press "Send the wrong photo" (a close-up of a wall jack). Expected: "Not yet" with the
   reason; in the trace, OpenCV's row first, then the model's verdict. The step does not
   advance.
9. Press "Send the right photo" (the open panel). Expected: OpenCV passes it to the model,
   the verdict is shown, and "Next step" appears if the model passed it. The model is not
   deterministic; the trace shows whatever came back.

E. AGENT MODE - THE AGENT DECIDES THE TOOL CALLS (about 3 minutes, uses Amazon Bedrock)
10. Open https://utgfmpcgxf.us-east-1.awsapprunner.com/agent . Type a task and attach a photo
   (e.g. src/stepspotter/web/demo_photos/02-panel-inside.jpg from the repo: "Confirm the
   structured wiring panel is safe to work on"). The Guide agent starts the job.
11. Send a blurred photo (data/demo/agentic-opencv/photos/02-panel-inside-blurred-sigma4.jpg),
   then one of another place (src/stepspotter/web/demo_photos/04-office-jack-front.jpg), then
   the panel from further back (src/stepspotter/web/demo_photos/01-panel-overview.jpg). Expected: under each answer you see the tool calls
   the agent made, OpenCV's decision for the photo (retake / place_unconfirmed / ok), its
   time and pictures, and any gate refusal; a blurred photo is refused without a model call.
   The model is not deterministic, so wording and the exact calls vary.
   A recorded run of this, with the full trace: data/demo/agentic-opencv/transcript.md

LIMITS: the live service allows, per day for everyone together, 6 jobs, 30 photo checks
(the four judge buttons count as photo checks) and 60 agent turns; per address per hour,
6 jobs, 30 photo checks and 20 agent turns; at most 8 tool calls in one agent turn. This
keeps it inside its budget. If the page says the demo has run its quota for today, use D.

D. OFFLINE, NO AWS ACCOUNT
  git clone https://github.com/retailbox-automation/stepspotter-opencv && cd stepspotter-opencv
  python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
  tools/fetch_models.sh
  .venv/bin/python -m pytest -q -m "not integration"
  .venv/bin/python eval/build_set.py && .venv/bin/python eval/run.py --config opencv
Expected: 433 passed, 1 skipped (with the face model fetched).
The test tests/test_perception_gate.py shows each OpenCV decision changing the next call
(no model call / one-photo / two-photo check / cancel_tool / interrupt) with the model
replaced by a recorder.

Where in the code: src/stepspotter/guide.py (JobService.verify), src/stepspotter/gate.py
(StepGate), src/stepspotter/perception/ (the OpenCV 5 checks). Report: docs/REPORT.md.
```

## Working web endpoint (field 28211)

https://utgfmpcgxf.us-east-1.awsapprunner.com

## Special Award Consideration (field 28208)

Agentic Vision Award — only. (Not "Best Use of COOL Award": we did not build a COOL
integration.)

## Video

{{VIDEO:url}} — ≤ 5 minutes, public on YouTube.

## Files (zip_file_required)

{{ZIP:name and SHA-256 — the release archive with the code, docs/report/StepSpotter-OpenCV26-report.pdf, docs/diagrams/ and eval/results/}}

## Gallery (upload in this order; files in `docs/screens/gallery/`, captions ≤ 140 characters)

Images 1, 2, 4 and 5 are screenshots of the live app taken on 21 October 2026 (build 3f75518, headless
Chromium at phone size 390×844 and desktop 1440×900); 3 is the headline table of `docs/EVAL.md`; 6 and 8
are `docs/diagrams/`; 7 is the shipped keyframe code (`perception/frames.py`) run on
`eval/cases/public/own-sink-video/clip-31s-36s.mp4`. The single screenshots are in `docs/screens/`.
Each image is ≥ 1800 px wide and under 1 MB.

1. **01-retake-224ms-no-model.png** — Live: a blurred proof photo refused by OpenCV 5 in 224 ms with one instruction. No model call; the next step stays locked. (122)
2. **02-trace-opencv-pictures.png** — The trace on the live app: OpenCV's row with match lines, change heatmap and quality bars, its time, and whether a model was asked. (131)
3. **03-eval-table.png** — 50 held-out cases: model alone vs OpenCV 5 then the model. 30 of 33 bad photos refused, 31 model calls instead of 54, misses listed. (132)
4. **04-human-approval.png** — 35% of the do-not-touch zone changed: OpenCV stops the run, no model call, and nothing moves until a person approves. (117)
5. **05-agent-mode-inspect-photo.png** — Agent mode: the Strands agent calls inspect_photo itself; OpenCV says retake in 219 ms, so the agent asks for a new shot. (121)
6. **06-architecture.png** — What runs on AWS: App Runner with OpenCV 5 before the Bedrock verifier and the Strands gate; CloudWatch, Budget, CodeBuild, ECR. (128)
7. **07-sink-video-keyframes.jpg** — A video instead of a photo: OpenCV samples our own under-sink leak clip and keeps the sharpest frames. The video never reaches a model. (135)
8. **08-agent-workflow.png** — Perception, decision, action: OpenCV's route picks no model call, a one- or two-photo model check; the gate cancels or asks a person. (133)
