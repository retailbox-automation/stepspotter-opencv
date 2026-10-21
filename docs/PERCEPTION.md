# The OpenCV 5 perception layer

StepSpotter opens the next step of a repair only after a photo proves the last one was
done. Until this layer, one model call on one photo decided that. Now OpenCV 5 looks at
every evidence photo **first**, in tens of milliseconds and without a model. What it finds
changes what happens next:

| OpenCV decision | what happens next | who decides after |
|---|---|---|
| `retake` | photo refused before any model call; the person gets ONE instruction (more light, hold still, step back so X is in frame, move the glare) | the person, with a new photo |
| `wrong_place` | refused: it is not the place this step's zones were drawn on | the person |
| `replay` | refused: it is a photo this job has already seen | the person |
| `no_change` | refused: the step had to change something and nothing changed there | the person |
| `touched_avoid` | the gate raises `interrupt("human_review")` — a request for a person's approval, not a cancel | a person |
| `ok` | the photo goes on to the model check (with OpenCV's aligned crop of the work zone) | the model, then the gate |
| `skipped` | OpenCV could not read the file; nothing decided here | the model |

Code: `src/stepspotter/perception/`. The policy, in the order it is applied, is the
docstring of `perception/inspect.py`; every number is in `perception/thresholds.py`
with where it came from.

## What each check measures

| module | measures | OpenCV 5 calls |
|---|---|---|
| `quality.py` | sharpness = p90 of Laplacian variance over 4x4 tiles (a sharp part on a soft background passes); exposure = mean grey, share of near-black (<16) and near-white (>=245) pixels; blank frame = grey std; glare = largest connected saturated (>=250) blob; size | `Laplacian`, `calcHist`, `threshold`, `connectedComponentsWithStats` |
| `scene.py` | is the evidence the same place as the reference: SIFT (2000, on CLAHE luminance), Lowe ratio 0.75, `findHomography(USAC_MAGSAC)`, then a sanity check on the homography (orientation, convex projected quad, scale 0.2–5, not a sliver, overlap). A close-up that fails the whole-frame match is matched again against a crop of the reference around the work zone. Replay = homography near identity AND nothing different after alignment, anywhere | `SIFT_create`, `BFMatcher.knnMatch`, `findHomography`, `perspectiveTransform`, `isContourConvex`, `intersectConvexConvex` |
| `change.py` | the evidence warped onto the reference grid, CLAHE on L in Lab, sigma-3 blur, per-pixel change = any Lab channel moved > 28 levels, 5x5 opening; the changed share of each work zone and each do-not-touch zone, **read against the change outside every zone** (the noise floor) | `warpPerspective`, `cvtColor(LAB)`, `createCLAHE`, `absdiff`, `morphologyEx`, `erode` |
| `frames.py` | a video instead of a photo: 24 evenly spaced frames, scored by sharpness × exposure × (1 + inliers to the reference / 100), near-duplicates dropped, best 3 kept; the best one goes down the photo path | `VideoCapture` + the above |
| `privacy.py` | faces blurred in the file before it is stored or sent to a model — **only if the YuNet ONNX file is installed** (see Privacy) | `FaceDetectorYN`, `GaussianBlur` |
| `render.py` | pictures for the person and for a judge: match (inlier lines + projected frame), change heatmap with zones and their changed share, quality bars against thresholds | drawing only; never decides |
| `inspect.py` | the policy; returns `PerceptionReport` with the decision, the reason, the one instruction, every metric, the thresholds used and per-stage timings | — |

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
| `BLANK_STD` | 8 | spike: originals ≥ 23.1 |
| `SHARP_P90_MIN` | 45 | exp at 640 px: originals 73.7–1072.5; sigma-2 blur ≤ 34.2 and motion ≤ 60 except on the densely wired 03 |
| `SHARP_RATIO_MIN` / `REL_SHARP_MIN_COVERAGE` | 0.35 / 0.6 | exp: blurred copies keep 0.05–0.40 of the original's sharpness; applied only when the evidence covers ≥ 60 % of the reference (same view) |
| `GLARE_BLOB_FRAC` | 0.005 | exp: originals ≤ 0.002; a 5 % glare disc 0.009–0.011 |
| `MIN_INLIERS` / `MIN_INLIER_RATIO` | 20 / 0.2 | spike: different places ≤ 10 inliers; real pair 01↔02 33 (62 with CLAHE) |
| `REPLAY_*` | corner shift ≤ 4 % of diagonal, scale ±5 %, normalised MAD ≤ 2.5, changed ≤ 1.2 %, largest changed blob ≤ 0.05 % | exp: re-encoded / resized / 2°-rotated copies MAD 0.25–0.59, largest blob ≤ 0.003 %; a small pasted part ≥ 0.03 % |
| `CHANGE_DELTA` | 28 Lab levels | spike: an edit read 0.29–0.31 inside its box, 0.0 without one |
| `NOISE_FLOOR_MAX` | 0.12 | exp: the real pair 01↔02 changed 37 % of the frame after alignment (parallax) — above this floor the change map decides nothing |
| `ACT_CHANGED_MIN` / `AVOID_CHANGED_MIN` | 0.04 / 0.06, and ≥ 2.5 × floor + 0.02 | spike edit levels, with margin over the floor |
| `ZONE_JUDGE_MIN_VISIBLE` | 0.3 | eval run 1 (below) |
| `STUCK_AFTER` (`inspect.py`) | 3 | the coordinator's rule: after 3 OpenCV blocks in a row on one step, the next quality / place / no-change refusal goes to the model with OpenCV's findings attached instead |

**Not a blind test.** These thresholds were set looking at all six photos. The eval
split below (by scene) is reported per half so a reader can see whether results differ
by scene; it is not a held-out validation of these numbers. A blind test needs photos
nobody tuned on — open problem 1.

## Where OpenCV changes what happens next

1. `JobService.verify` runs `inspect_evidence` first. A blocking decision becomes
   `StepVerdict(passed=False, source="opencv")` **without calling the model**; the
   `perception` trace row says `llm_called: false` and the job's `llm_calls_saved` grows.
   Tests: `tests/test_perception_gate.py` (`Model.calls == []` in every blocking case).
2. `StepGate` (`BeforeToolCall` on `advance_step`) refuses on a stored blocking report
   even beside a passing verdict (defence in depth), and turns `touched_avoid` into
   `interrupt("human_review")`. On resume, the person's answer is recorded
   (`JobService.review`); an approval lets the do-not-touch change stand for that step
   (still measured and reported), and the step still needs a photo that passes.
3. Agent tools: `inspect_photo` (OpenCV only, nothing stored — the agent asks for a better
   photo before submitting), `submit_video` (best keyframe, then the photo path).
   `GUIDE_SYSTEM` tells the agent to relay OpenCV's one instruction.
4. Stuck rule: after 3 consecutive OpenCV blocks on a step, a further `retake`,
   `wrong_place` or `no_change` is marked `overridden` and goes to the model with
   OpenCV's findings as context — a false positive here must never trap a person.
   `replay` is never overridden (a new photo always clears it); `touched_avoid` already
   goes to a person. Tests: `tests/test_perception_failures.py`.
5. The web page: an "OpenCV photo check (code, not the model)" card per photo with the
   pictures and the time; "Everything it did" shows the same with thumbnails; a stop for
   a person carries an approve action. `For judges` on the first screen runs four
   OpenCV branches on packaged photos as real jobs through the real gate, with a
   verifier that raises if it is ever reached. `POST /api/inspect` returns the report and
   pictures for any reference + evidence (+ zones), no model, under the photo rate caps.

**Trace contract** (one flat row, `event: "perception"`): `decision`, `reason_code`,
`llm_called`, `ms_total`, `step_id`, plus `reason`, `instruction`, `mode` (submit / probe),
`blocks`, `needs_human`, `overridden`, `llm_calls_saved`, per-stage `ms_*`, `sharpness`,
`scene`, `inliers`, `act_change`, `avoid_change`, `background_change`, `faces_checked`,
`img_match` / `img_heatmap` / `img_quality`. With `STEPSPOTTER_TRACE_STDOUT=1` the
`perception` rows and the `limits` rows (IP replaced by a salted 10-character hash) are
also printed to stdout as single-line JSON, paths cut to basenames, nothing else.

## Eval

`eval/build_set.py` builds 99 cases from the six photos, deterministically (fixed seeds,
sha256 per file in `eval/cases/manifest.json`): 15 synthetic classes × 6 photos (good:
rotation, hand-held re-shot, side light, native-resolution close-up, an edit in the work
zone; bad: Gaussian and motion blur, dark, overexposed, glare, work zone cut off, replay
of the reference, replay of an earlier photo, no change, an edit in a do-not-touch zone)
plus 9 real pairs of our own photos (5 of the same place, 4 of different rooms). Every case
records its provenance (real / synthetic + generator + parameters) and its group and scene.
**Split by scene**: calibration = the panel (01–03, 49 cases), test = the office jack and
the dining node (04–06, 50 cases); no case mixes the halves. Consequence: the calibration
half has no "different place" pairs (all its photos are one panel).

`python eval/run.py --config opencv` (2026-10-21T11:54:17Z, Mac Studio shared with other
work, `nice -n 15`; full table and every failure in `eval/results/opencv.md`):

| slice | bad caught | good falsely blocked | decision = expected |
|---|---:|---:|---:|
| all (99) | 64 / 64 | 3 / 35 | 96 / 99 |
| calibration (49) | 30 / 30 | 2 / 19 | 47 / 49 |
| test (50) | 34 / 34 | 1 / 16 | 49 / 50 |
| real pairs only (9) | 4 / 4 different rooms | 3 / 5 same place | 6 / 9 |

Timing of the OpenCV decision (`ms_total`, includes reading the JPEGs), same run:
all cases p50 **45.0 ms**, p95 **74.5 ms** (max 143.9 ms); quality refusals p50 4.3 /
p95 4.8 ms; photos that went through matching and change p50 48.6 / p95 76.8 ms.

`python eval/run.py --config combined --dry-run` lists **32** model calls for the 99 cases
(the ones OpenCV lets through) against 99 for `--config llm`: 67 of 99 photos in this set
never reach the model. Whether the model would have caught them too, and what it costs,
is the LLM lane's run (`--config llm|combined --max-llm-calls N`), not this one.

**How to read the 64/64.** The synthetic bad cases are damage of a known kind and size,
and the checks were built to detect exactly that; near-100 % is expected by construction
and shows the checks fire on what they are meant to, not field accuracy. The informative
numbers are the false blocks, and above all the real pairs.

**Eval run 1** (`eval/results/opencv-run1-2026-10-21.md`, kept): 64/64 caught, **11/35**
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

1. **A real photo of the same place from another view or another day is refused as
   `wrong_place`** (3 of 5 real same-place pairs): 02→03 and 01→03 (a close-up of the
   telecom module taken at another time, cables rearranged), 04→05 (the same wall jack,
   box opened, jack pulled out). They keep 4–8 inliers (best of whole frame and zone
   crop) — the same range as the photos of different rooms (5–8), so on these photos no
   inlier threshold separates "same place, changed view" from "another room". The instruction asks the person to shoot from where the first photo was
   taken, which is a cheap retry — and the stuck rule hands the 4th photo to the model.
2. Change detection on real re-shots is noisy: parallax in 3-D clutter changed 37 % of
   the frame on the real pair. Those maps come back `unreliable` and decide nothing, so
   `no_change` and `touched_avoid` only fire when the photo is taken from close to the
   reference viewpoint.
3. `wrong_place`, `touched_avoid` and `no_change` depend on zones, which come from the
   Marker model's boxes — rough by design (`marker.py`: boxes drift and run oversized).
   No zones for a step means the scene check is recorded `not_applicable` and cannot block.
4. Large clipped white areas (a lamp-lit wall) read as glare; seen with generator v1, and
   possible with real phone photos of bright walls. Not measured on real photos.
5. Replay is "pixel-near-identical"; a person photographing from a tripod-steady position
   with nothing changed would be told it is a repeat. Not observed; no such photos.
6. Thin margin: the softest original (04, plain jack on a plain wall) reads 73.7 against a
   floor of 45.

## Privacy

`faces_checked` is **false** in every report this repository produces: the YuNet model
is **not shipped** and nothing downloads it. `tools/fetch_models.sh` fetches it with the
checksum pinned to the opencv_zoo Git LFS oid (`sha256 8f2383e4…2552fa4`, 232,589 bytes);
once installed, faces are blurred in the stored file before any model sees it. The only
test with the detector installed checks that none of the six photos (no faces in them)
gets a false blur; a positive test needs a photo of a face we have the right to use, and
the repo has none. Until both exist, face blurring is not a claimed feature.

## Deviations from DESIGN.md

- **Reference and baseline split.** The geometric reference is the photo the step's card
  was drawn on (the start photo — the zones live on it). The *change baseline* is the last
  accepted evidence of an earlier step that lined up with the reference, else the
  reference, so step 3 is not credited with what step 2 changed (DESIGN: "start photo or
  last accepted evidence" for both).
- CLAHE before SIFT (not in DESIGN): doubled inliers on the real pair.
- Quality is read at 640 px long (or half size), not 512 wide; thresholds re-measured.
- Replay also requires no changed blob > 0.05 % and ignores clipped pixels.
- Change is judged against the noise floor outside the zones, with an `unreliable` status.
- Relative sharpness only for the same view; a zone-crop match for close-ups.
- `touched_avoid` applies whatever `expects_change` says (a do-not-touch zone is never
  meant to change); only the `no_change` check is informational for `expects_change=None`.
- A `skipped` decision for files OpenCV cannot read.
- The model gets OpenCV's aligned work-zone crop on every `ok` photo, and OpenCV's
  findings as text only on a stuck-rule override.
- The pre-existing tests submit flat single-colour images and fake paths; they run with the
  layer off (`tests/conftest.py`, `STEPSPOTTER_PERCEPTION=0`), and the perception tests
  turn it on with real photos. Production default is on (pinned by a test).
- The eval report lives in `eval/results/*.md` and this file, not `docs/EVAL.md`.
  No public dataset was used (none was licence-checked in this lane). The split is by
  scene, not by photo, so scene-mates never straddle the halves.
- Added at the coordinator's request: the stuck rule, `/api/inspect`, the judge scenarios,
  the stdout trace mirror.

## Open problems

1. A blind test: photos of a real repair, taken for this purpose, that no threshold here
   was tuned on — including real before/after pairs for `no_change` and `touched_avoid`.
2. Real cross-view photos of the same place fail to match (failure mode 1).
3. Face blurring is not shipped (Privacy).
4. The model configs (`llm`, `combined`) are not run here; their numbers are the LLM lane's.
5. The live App Runner URL in the README runs the pre-OpenCV build.

## Reproduce

```bash
nice -n 15 uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q -m "not integration" -p no:cacheprovider     # whole suite, offline
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_perception*.py tests/test_eval_harness.py tests/test_trace_stdout.py
.venv/bin/python eval/build_set.py                                        # 99 cases, sha256-checked
.venv/bin/python eval/run.py --config opencv                              # eval/results/opencv.md
.venv/bin/python eval/run.py --config combined --dry-run                  # the model calls it WOULD make
.venv/bin/python eval/run.py --config llm --max-llm-calls 0               # exits 0, calls nothing
```
