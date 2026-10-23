# The OpenCV 5 perception layer

StepSpotter opens the next step of a repair only after a photo proves the last one was
done. Until this layer, one model call on one photo decided that. Now OpenCV 5 looks at
every evidence photo **first**, without a model: about 70 ms on a laptop (p50 over 548 cases,
`eval/results/opencv.json`), 0.2–1.9 s on the 1-vCPU App Runner instance. What it finds
changes what happens next:

| OpenCV decision | route | what happens next | who decides after |
|---|---|---|---|
| `retake` | `opencv_block` | photo refused before any model call; the person gets ONE instruction (more light, hold still, step back so X is in frame, move the glare) | the person, with a new photo |
| `replay` | `opencv_block` | refused: it is a photo this job has already seen | the person |
| `no_change` | `opencv_block` | refused: the step had to change something and nothing changed there | the person |
| `touched_avoid` | `opencv_block` | the gate raises `interrupt("human_review")` — a request for a person's approval, not a cancel | a person |
| `place_unconfirmed` | `llm_two_image` | NOT refused: OpenCV could not line the photo up with the first photo, so the model gets **both** photos and must answer `same_place`; the gate lets the step close only on `same_place=true` | the model, then the gate |
| `ok` | `llm_single` | the photo goes on to the model check, with OpenCV's aligned crop of the work zone | the model, then the gate |
| `skipped` | `llm_single` | OpenCV could not read the file; nothing decided here | the model |

`wrong_place` is no longer produced (it stays in the `Decision` type only so jobs saved
before 2026-10-21 still load — `perception/models.py:17`). Until commit `793b987` a photo
OpenCV could not line up was refused as `wrong_place`; on our own photos that refused 3 of
5 real re-shots of the same place (see Eval, run 2), so the decision moved to the model.

Code: `src/stepspotter/perception/`. The policy, in the order it is applied, is the
docstring of `perception/inspect.py`; every number is in `perception/thresholds.py`
with where it came from. The route is `PerceptionReport.route` (`perception/models.py:167`).

## What each check measures

| module | measures | OpenCV 5 calls |
|---|---|---|
| `privacy.py` | faces found and blurred in the file **before** anything else reads it — before the quality check, before it is stored, before any model sees it (see Privacy) | `FaceDetectorYN`, `GaussianBlur` |
| `quality.py` | sharpness = p90 of Laplacian variance over 4x4 tiles (a sharp part on a soft background passes); exposure = mean grey, share of near-black (<16) and near-white (>=245) pixels, overexposure read against the first photo; blank frame = grey std; glare = largest connected saturated (>=250) blob — a note on its own, a refusal only when it newly covers the work zone; size | `Laplacian`, `calcHist`, `threshold`, `connectedComponentsWithStats` |
| `scene.py` | is the evidence the same place as the reference: SIFT (2000, on CLAHE luminance), Lowe ratio 0.75, `findHomography(USAC_MAGSAC)`, then a sanity check on the homography (orientation, convex projected quad, scale 0.2–5, not a sliver, overlap). A close-up that fails the whole-frame match is matched again against a crop of the reference around the work zone. Replay = homography near identity AND nothing different after alignment, anywhere | `SIFT_create`, `BFMatcher.knnMatch`, `findHomography`, `perspectiveTransform`, `isContourConvex`, `intersectConvexConvex` |
| `change.py` | the evidence warped onto the reference grid, CLAHE on L in Lab, sigma-3 blur, per-pixel change = any Lab channel moved > 28 levels, 5x5 opening; the changed share of each work zone and each do-not-touch zone, **read against the change outside every zone** (the noise floor) | `warpPerspective`, `cvtColor(LAB)`, `createCLAHE`, `absdiff`, `morphologyEx`, `erode` |
| `frames.py` | a video instead of a photo: 24 evenly spaced frames, scored by sharpness × exposure × (1 + inliers to the reference / 100), near-duplicates dropped, best 3 kept; the best one goes down the photo path | `VideoCapture` + the above |
| `render.py` | pictures for the person and for a judge: match (inlier lines + projected frame), change heatmap with zones and their changed share, quality bars against thresholds | drawing only; never decides |
| `inspect.py` | the policy; returns `PerceptionReport` with the decision, the route, the reason, the one instruction, every metric, the thresholds used and per-stage timings | — |

## Where the numbers came from

All measured on the six real photos in this repo (`fixtures/perception/scenes.json`),
OpenCV 5.0.0, numpy 2.5.4. "spike" = `spike/opencv5/spike.py` in the hackathon project
(2026-10-21); "exp" = measurements made while building this package the same day.

| threshold | value | source |
|---|---:|---|
| `WORK_PX` (matching size) | 1024 | spike: at 1280 px, different places reached 35 inliers with a degenerate fit; at 1024 the worst was 10 |
| `QUALITY_PX` (quality read at, long side) | 640, or half the photo if smaller | exp: Laplacian energy depends on the read scale; thresholds were measured at a 2x downscale |
| `DARK_MEAN` | 28 | spike: darkened copies 5.1–18.4, darkest real original 47.4 |
| `BRIGHT_FRAC_MAX` | 0.12 | spike: overexposed copies 0.23–0.99, originals ≤ 0.007 |
| `OVEREXPOSED_MARGIN` | 0.12 | overexposure is refused only when the near-white share is also more than this above the first photo's. Calibration half of the eval set: every overexposed case exceeded its first photo by +0.216 to +0.966, no good photo by more than +0.063; a white scene is white in both photos |
| `BRIGHT_FRAC_ABS_MAX` | 0.50 | with no readable first photo, only a photo more than half blown out is refused. Calibration: the brightest good photo 0.466 (a white scene); 8 of 12 overexposed cases above 0.50 |
| `BLANK_STD` | 8 | spike: originals ≥ 23.1 |
| `SHARP_P90_MIN` | 45 | exp at 640 px: originals 73.7–1072.5; sigma-2 blur ≤ 34.2 and motion ≤ 60 except on the densely wired 03 |
| `SHARP_RATIO_MIN` / `REL_SHARP_MIN_COVERAGE` | 0.22 / 0.6 | the evidence may not fall below this share of the first photo's sharpness; applied only when it covers ≥ 60 % of the reference (same view). Lowered from 0.35 on the calibration half of the eval set: every blur case that passed the floor had ≤ 0.193; the real same-place pair c36→c37 scored 0.255 and was wrongly refused at 0.35 |
| `WEAK_FIT_INLIERS` | 12 | the ratio is also read on a weak but sane fit (≥ 12 points, below the confirm bar), because blur is what removes matches. Calibration: the blurred trap frame v0180 kept 16 sane inliers; 12 is above the different-place maximum seen (10) |
| `GLARE_BLOB_FRAC` | 0.005 | advisory note only since the evaluation: as a refusal, a frame-wide blob rule refused 14 of 111 good calibration photos (white basins, a white wall, a flashlight hot spot) — blob size cannot tell glare from a white object |
| `GLARE_ZONE_NEW_FRAC` | 0.10 | glare refuses only when at least this share of the work zone is saturated in the evidence but not at the same place in the first photo. Calibration: good photos ≤ 0.086, synthetic glare 0.060–0.569; refuses no good calibration photo and still blocks 5 of 12 glare cases, the rest go to the model |
| `MIN_INLIERS` / `MIN_INLIER_RATIO` | 25 / 0.2 | to **confirm** the place. eval run 2 (CLAHE): every pair that did not line up had ≤ 8 inliers — different rooms (5–8) and real re-shots of the same place (4–8) alike; every confirmed match had ≥ 52 (real 01↔02: 52, 79; synthetic ≥ 118). 25 = 3x the worst unmatched, half the weakest real match. Below it the photo is not refused, it goes to the two-photo check, so a high bar costs a dearer check, never a refused person. Raised from 20 when a miss stopped being a block |
| `REPLAY_*` | corner shift ≤ 4 % of diagonal, scale ±5 %, normalised MAD ≤ 2.5, changed ≤ 1.2 %, largest changed blob ≤ 0.05 % | exp: re-encoded / resized / 2°-rotated copies MAD 0.25–0.59, largest blob ≤ 0.003 %; a small pasted part ≥ 0.03 % |
| `CHANGE_DELTA` | 28 Lab levels | spike: an edit read 0.29–0.31 inside its box, 0.0 without one |
| `NOISE_FLOOR_MAX` | 0.12 | exp: the real pair 01↔02 changed 37 % of the frame after alignment (parallax) — above this floor the change map decides nothing |
| `ACT_CHANGED_MIN` / `AVOID_CHANGED_MIN` | 0.04 / 0.06, and ≥ 2.5 × floor + 0.02 | spike edit levels, with margin over the floor |
| `ZONE_JUDGE_MIN_VISIBLE` | 0.3 | eval run 1 (below) |
| `YUNET_SCORE` | 0.8 | score threshold passed to `FaceDetectorYN.create`; not tuned on our photos (one public-domain portrait is the only face test) |
| `STUCK_AFTER` (`inspect.py`) | 3 | the coordinator's rule: after 3 OpenCV blocks in a row on one step, the next `retake` or `no_change` refusal goes to the model with OpenCV's findings attached instead |

**Not a blind test.** The first thresholds were set looking at all six photos; the quality thresholds changed after the evaluation (`OVEREXPOSED_MARGIN`, `BRIGHT_FRAC_ABS_MAX`, `SHARP_RATIO_MIN`, `WEAK_FIT_INLIERS`, `GLARE_ZONE_NEW_FRAC`) were calibrated on the evaluation's calibration half only (`src/stepspotter/perception/thresholds.py`). The eval
split below (by scene) is reported per half so a reader can see whether results differ
by scene; it is not a held-out validation of these numbers. The full evaluation, with
the model configurations and photos nobody tuned on, is `docs/EVAL.md`.

## Where OpenCV changes what happens next

1. `JobService.verify` (`guide.py:409`) runs `inspect_evidence` first. A blocking decision
   becomes `StepVerdict(passed=False, source="opencv", route="opencv_block")` **without
   calling the model**; the `perception` trace row says `llm_called: false` and the job's
   `llm_calls_saved` grows. Tests: `tests/test_perception_gate.py` (`Model.calls == []` in
   every blocking case).
2. **The route picks the model check.** `place_unconfirmed` sends the person's first photo
   and the evidence to the two-photo verifier (`guide.py:447`, `verifier.py:91`), which must
   fill `same_place`; a pass without `same_place=true` is turned into a fail
   (`guide.py:453`, fail closed). `ok` sends one photo plus OpenCV's aligned crop of the
   work zone. Tests: `test_a_photo_opencv_cannot_line_up_goes_to_the_two_photo_check`,
   `test_without_a_two_photo_verifier_the_unconfirmed_place_fails_closed`,
   `test_a_confirmed_place_is_checked_on_one_photo`.
3. `StepGate` (`BeforeToolCall` on `advance_step`) refuses on a stored blocking report
   even beside a passing verdict (defence in depth, `gate.py:141`), refuses a
   `place_unconfirmed` step unless the verdict says `same_place=true` (`gate.py:153`), and
   turns `touched_avoid` into `interrupt("human_review")` (`gate.py:91`). On resume, the
   person's answer is recorded (`JobService.review`); an approval lets the do-not-touch
   change stand for that step (still measured and reported), and the step still needs a
   photo that passes.
4. Agent tools: `inspect_photo` (OpenCV only, nothing stored). On `place_unconfirmed` it
   tells the agent it may ask the person **once** for a photo from about where the first
   one was taken (active perception); the submit path never asks, so a person who did the
   step is never sent back for an angle alone. `submit_video` picks the best keyframe,
   then the photo path. `GUIDE_SYSTEM` tells the agent to relay OpenCV's one instruction.
5. Stuck rule: after 3 consecutive OpenCV blocks on a step, a further `retake` or
   `no_change` is marked `overridden` and goes to the model with OpenCV's findings as
   context — a false positive here must never trap a person. `replay` is never overridden
   (a new photo always clears it); `touched_avoid` already goes to a person. Tests:
   `tests/test_perception_failures.py`.
6. The web page: an "OpenCV photo check (code, not the model)" card per photo with the
   pictures and the time; "Everything it did" shows the same with thumbnails; a stop for
   a person carries an approve action. `For judges` on the first screen runs four
   scenarios on packaged photos as real jobs through the real gate, with a verifier that
   raises if it is ever reached: three end in OpenCV (`retake`, `replay`,
   `touched_avoid` → a person approves) and one shows the routing decision
   (`place_unconfirmed` → route `llm_two_image`) and stops before the model call.
   `POST /api/inspect` returns the report and pictures for any reference + evidence
   (+ zones), no model, under the photo rate caps.
7. Agent mode (`/agent`, `src/stepspotter/web/agent_mode.py`): the Guide agent decides the
   tool calls on the web; each answer shows the calls, OpenCV's decision and pictures for
   each photo, and any gate refusal. A recorded live run is in `data/demo/agentic-opencv/`
   (blur → `retake` in 44 ms with no model call; another room → two-photo check, not
   passed; the panel → single-photo pass → the gate allows `advance_step`; a permissive
   skip attempt cancelled by the gate).

**Trace contract** (one flat row, `event: "perception"`): `decision`, `reason_code`,
`route`, `llm_called`, `ms_total`, `step_id`, plus `reason`, `instruction`, `mode`
(submit / probe), `blocks`, `needs_human`, `overridden`, `llm_calls_saved`, per-stage
`ms_*`, `sharpness`, `scene`, `inliers`, `act_change`, `avoid_change`,
`background_change`, `faces_checked`, `faces_blurred`, `img_match` / `img_heatmap` /
`img_quality`. The `verdict` row that follows carries `source`, `route` and `same_place`.
With `STEPSPOTTER_TRACE_STDOUT=1` the `perception` rows and the `limits` rows (IP
replaced by a salted 10-character hash) are also printed to stdout as single-line JSON,
paths cut to basenames, nothing else.

## Eval

`eval/build_set.py` builds 99 cases from the six photos, deterministically (fixed seeds,
sha256 per file in `eval/cases/manifest.json`): 15 synthetic classes × 6 photos (good:
rotation, hand-held re-shot, side light, native-resolution close-up, an edit in the work
zone; bad: Gaussian and motion blur, dark, overexposed, glare, work zone cut off, replay
of the reference, replay of an earlier photo, no change, an edit in a do-not-touch zone)
plus 9 real pairs of our own photos (5 of the same place, 4 of different rooms). Every case
records its provenance (real / synthetic + generator + parameters) and its group and scene.
**Split by scene**: calibration = the panel (01–03, 49 cases), test = the office jack and
the dining node (04–06, 50 cases); no case mixes the halves.

**The numbers for the current policy, and for the model configurations, are in
`docs/EVAL.md`** (`eval/results/*.json`), on 548 cases. In short, after the quality-rule
change: OpenCV alone wrongly refused 2 of 66 good test-half photos and 1 of 103 calibration
photos (20 before), and 0 of 56 unmodified real photos (8 before)
(`eval/results/opencv.json`, `eval/results/originals.json`). The two runs below were made on 2026-10-21
before the policy change in `793b987`, when a photo OpenCV could not line up was still
refused as `wrong_place`; they are kept because they are why the policy changed.

**Run 2** (`eval/results/opencv.md` at commit `ff97511`, 2026-10-21T11:54:17Z, `wrong_place` policy):

| slice | bad caught | good falsely blocked | decision = expected |
|---|---:|---:|---:|
| all (99) | 64 / 64 | 3 / 35 | 96 / 99 |
| real pairs only (9) | 4 / 4 different rooms | 3 / 5 same place | 6 / 9 |

The three false blocks were all real re-shots of the same place refused as `wrong_place`
(02→03, 01→03, 04→05), with 4–8 inliers — the same range as photos of different rooms
(5–8). No inlier threshold separates the two on these photos, which is the measurement
behind `place_unconfirmed`. Timing of the OpenCV decision in that run (`ms_total`,
includes reading the JPEGs, Mac Studio): p50 45.0 ms, p95 74.5 ms.

**How to read "bad caught".** The synthetic bad cases are damage of a known kind and
size, and the checks were built to detect exactly that; near-100 % is expected by
construction and shows the checks fire on what they are meant to, not field accuracy.
The informative numbers are the false blocks, and above all the real pairs.

**Run 1** (`eval/results/opencv-run1-2026-10-21.md`, kept): 64/64 caught, **11/35**
good refused. Four of its findings were fixed before run 2, none by moving a threshold:
- the `good_light` generator v1 clipped 7–31 % of the pixels of the brighter photos —
  overexposed photos mislabelled as good (v2: a non-clipping side light; the newly clipped
  share is now recorded per case, max 0.41 %);
- close-ups were refused as "blurrier than the first photo" because magnification lowers
  texture per pixel — the ratio rule now applies only to the same view (coverage ≥ 0.6);
  comparing the evidence warped onto the reference was tried first and dropped (the
  ratio swung from 0.37 on a sharp re-shot to 5.5 on a blurred copy);
- a low-resolution close-up was read at a finer scale than the thresholds were measured
  at — quality is now read after at least a 2x downscale;
- a close-up holding 1.2 % of a do-not-touch zone raised `touched_avoid` on that sliver —
  zones below 30 % visibility are not judged.

## Failure modes seen

1. **A real photo of the same place from another view or another day does not line up**
   (3 of 5 real same-place pairs in run 2): 02→03 and 01→03 (a close-up of the telecom
   module taken at another time, cables rearranged), 04→05 (the same wall jack, box
   opened, jack pulled out). They keep 4–8 inliers, the same range as photos of
   different rooms. Since `793b987` these go to the two-photo model check instead of
   being refused: the cost is a model call (and the model's own judgement of
   `same_place`), not a refused person. OpenCV alone can no longer reject a photo of
   another room; only the model can, through `same_place`.
2. Change detection on real re-shots is noisy: parallax in 3-D clutter changed 37 % of
   the frame on the real pair. Those maps come back `unreliable` and decide nothing, so
   `no_change` and `touched_avoid` only fire when the photo is taken from close to the
   reference viewpoint, and never on a photo that did not line up at all.
3. `place_unconfirmed`, `touched_avoid` and `no_change` depend on zones, which come from
   the Marker model's boxes — rough by design (`marker.py`: boxes drift and run
   oversized). No zones for a step means the scene check is recorded `not_applicable`
   and routes nothing to the two-photo check.
4. White subjects read as glare. The evaluation measured it on real photos: before the
   quality-rule change, 8 of 56 unmodified real photos were refused, mostly as glare on
   white basins, a white wall and a flashlight hot spot. Glare now refuses only when it newly
   covers the work zone, and none of the 56 is refused; the price is that 11 of 23
   synthetic glare discs now pass OpenCV and are left to the model (`docs/EVAL.md`).
5. Replay is "pixel-near-identical"; a person photographing from a tripod-steady position
   with nothing changed would be told it is a repeat. Not observed; no such photos.
6. Thin margin: the softest original (04, plain jack on a plain wall) reads 73.7 against a
   floor of 45.
7. Still open (`docs/EVAL.md`): a mirror-image look-alike of a symmetric scene can line up
   with the first photo (c08, 55 inliers) and passes the model checks too; a resent photo with a circle drawn on it counts as a change, not a replay; the
   smeared trap frame f0195 of our own video passes the blur check.

## Privacy

Faces are blurred in the evidence file itself, before the quality check, before the
photo is stored and before any model sees it (`inspect.py`, step 1; `guide.py`
`perceive` writes the blurred pixels back to the stored file). The detector is YuNet from
opencv_zoo (MIT, Copyright (c) 2020 Shiqi Yu), run through `cv2.FaceDetectorYN`. The
ONNX file is not committed: the container build fetches it and checks its size and
SHA256 against the pins in `src/stepspotter/perception/fetch_yunet.py` (`sha256
8f2383e4…2552fa4`, 232,589 bytes) and writes the MIT notice beside it; a mismatch fails
the build (`Dockerfile`). A checkout gets the same file with `tools/fetch_models.sh`.

Every report says whether the check ran (`faces_checked`) and how many faces were
blurred (`faces_blurred`); wherever the model file is absent — a checkout that has not
fetched it — `faces_checked` is `false` and nothing claims otherwise.
`tests/test_privacy_faces.py` runs the detector on a public-domain NASA portrait
(`tests/fixtures/ATTRIBUTION.md`): the face is found and blurred, nothing else in the
frame moves, the stored file is blurred before the model is called, and the six photos
of this repo (no faces in them) get no false blur. One portrait is a smoke test, not a
measured detection rate.

## Deviations from DESIGN.md

- **Reference and baseline split.** The geometric reference is the photo the step's card
  was drawn on (the start photo — the zones live on it). The *change baseline* is the last
  accepted evidence of an earlier step that lined up with the reference, else the
  reference, so step 3 is not credited with what step 2 changed.
- **`wrong_place` became `place_unconfirmed`** (route `llm_two_image`): measured on real
  re-shots, a missed match is not evidence of another place.
- CLAHE before SIFT (not in DESIGN): doubled inliers on the real pair.
- Quality is read at 640 px long (or half size), not 512 wide; thresholds re-measured.
- Replay also requires no changed blob > 0.05 % and ignores clipped pixels.
- Change is judged against the noise floor outside the zones, with an `unreliable` status.
- Relative sharpness only for the same view; a zone-crop match for close-ups.
- `touched_avoid` applies whatever `expects_change` says (a do-not-touch zone is never
  meant to change); only the `no_change` check is informational for `expects_change=None`.
- A `skipped` decision for files OpenCV cannot read.
- The model gets OpenCV's aligned work-zone crop on every `ok` photo, both photos on
  `place_unconfirmed`, and OpenCV's findings as text only on a stuck-rule override.
- The pre-existing tests submit flat single-colour images and fake paths; they run with the
  layer off (`tests/conftest.py`, `STEPSPOTTER_PERCEPTION=0`), and the perception tests
  turn it on with real photos. Production default is on (pinned by a test).
- Added at the coordinator's request: the stuck rule, `/api/inspect`, the judge scenarios,
  the stdout trace mirror.

## Open problems

1. A blind test: photos of a real repair, taken for this purpose, that no threshold here
   was tuned on — including real before/after pairs for `no_change` and `touched_avoid`.
2. Real cross-view photos of the same place do not line up (failure mode 1); they now
   cost a model call instead of a refusal.
3. Face detection is checked on one portrait; no detection rate is claimed.

## Reproduce

```bash
nice -n 15 uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q -m "not integration" -p no:cacheprovider     # whole suite, offline
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_perception*.py tests/test_privacy_faces.py tests/test_eval_harness.py tests/test_trace_stdout.py
tools/fetch_models.sh                                                     # YuNet, SHA256-checked (face tests skip without it)
.venv/bin/python eval/build_set.py                                        # 99 cases, sha256-checked
.venv/bin/python eval/run.py --config opencv                              # eval/results/opencv.md
.venv/bin/python eval/run.py --config combined --dry-run                  # the model calls it WOULD make
```
