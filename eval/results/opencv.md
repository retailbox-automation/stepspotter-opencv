# Perception eval — `--config opencv` (B)

Ran 2026-10-21T12:25:07+00:00 on 548 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 0). Code: main `43c1520`, eval `43c1520`; faces checked: True.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| good_rotate | good | 26 | — | — | 3 | — | 23 | 88.7 | 136.0 | 0 |
| good_reshot | good | 23 | — | — | 4 | — | 19 | 65.1 | 102.3 | 0 |
| good_light | good | 25 | — | — | 4 | — | 21 | 65.5 | 108.7 | 0 |
| good_closeup | good | 29 | — | — | 5 | — | 24 | 43.4 | 79.0 | 0 |
| good_act_edit | good | 28 | — | — | 3 | — | 25 | 77.7 | 119.2 | 0 |
| blur_gaussian | bad | 28 | 28 | 0 | — | — | 28 | 19.7 | 82.6 | 0 |
| blur_motion | bad | 32 | 31 | 0 | — | 1 | 31 | 41.6 | 87.4 | 0 |
| dark | bad | 23 | 23 | 0 | — | — | 23 | 19.2 | 40.1 | 0 |
| overexposed | bad | 22 | 22 | 0 | — | — | 22 | 20.5 | 38.9 | 0 |
| glare | bad | 23 | 23 | 0 | — | — | 23 | 21.4 | 42.8 | 0 |
| zone_cut | bad | 29 | 29 | 0 | — | — | 29 | 40.9 | 59.9 | 0 |
| replay_reference | bad | 24 | 24 | 0 | — | — | 21 | 61.6 | 86.7 | 0 |
| replay_earlier | bad | 24 | 24 | 0 | — | — | 18 | 87.1 | 125.3 | 0 |
| no_change | bad | 27 | 27 | 0 | — | — | 22 | 63.9 | 97.7 | 0 |
| touched_avoid | bad | 22 | 22 | 0 | — | — | 19 | 61.7 | 84.3 | 0 |
| real_same_place | good | 24 | — | — | 5 | 10 | 9 | 73.3 | 115.7 | 0 |
| real_wrong_place | bad | 4 | 0 | 0 | — | 4 | 4 | 65.6 | 86.0 | 0 |
| good_view_light | good | 24 | — | — | 6 | — | 18 | 66.0 | 102.4 | 0 |
| wrong_place_mirror | bad | 24 | 4 | 1 | — | 19 | 19 | 72.0 | 94.5 | 0 |
| replay_exact | bad | 25 | 25 | 0 | — | — | 20 | 56.2 | 110.5 | 0 |
| real_replay_annotated | bad | 1 | 1 | 0 | — | — | 0 | 43.0 | 43.0 | 0 |
| real_blur | bad | 4 | 3 | 0 | — | 1 | 3 | 27.2 | 59.3 | 0 |
| real_borderline | unscored | 2 | — | — | — | — | 0 | 72.7 | 72.7 | 0 |
| real_wrong_place_same_room | bad | 3 | 0 | 0 | — | 3 | 3 | 77.1 | 81.9 | 0 |
| real_lookalike | bad | 52 | 7 | 0 | — | 45 | 45 | 78.3 | 105.1 | 0 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 548 | 463 | 293 / 294 | 30 / 169 | 83 | {'llm_single': 141, 'opencv_block': 324, 'llm_two_image': 83} | 60.9 | 106.3 |
| split: calibration | 308 | 256 | 153 / 153 | 20 / 103 | 50 | {'llm_single': 84, 'opencv_block': 174, 'llm_two_image': 50} | 61.8 | 109.2 |
| split: test | 240 | 207 | 140 / 141 | 10 / 66 | 33 | {'llm_single': 57, 'opencv_block': 150, 'llm_two_image': 33} | 57.2 | 103.1 |
| source: onq | 125 | 104 | 66 / 66 | 2 / 38 | 21 | {'llm_single': 36, 'opencv_block': 68, 'llm_two_image': 21} | 61.3 | 97.0 |
| source: commons | 405 | 352 | 224 / 225 | 28 / 127 | 53 | {'llm_single': 100, 'opencv_block': 252, 'llm_two_image': 53} | 60.7 | 109.6 |
| source: own-video | 18 | 7 | 3 / 3 | 0 / 4 | 9 | {'llm_single': 5, 'llm_two_image': 9, 'opencv_block': 4} | 72.7 | 93.2 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| 02-real_same_place-03 | calibration | onq | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 8 |
| 01-real_same_place-03 | calibration | onq | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 7 |
| 04-real_same_place-05 | test | onq | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 4 |
| 01-good_view_light | calibration | onq | ok | retake | false_block | glare | — |
| 06-good_view_light | test | onq | ok | touched_avoid | false_block | change_in_avoid | 1218 |
| c03-good_light | test | commons | ok | retake | false_block | glare | — |
| c04-good_view_light | calibration | commons | ok | touched_avoid | false_block | change_in_avoid | 1147 |
| c07-good_closeup | test | commons | ok | retake | false_block | glare | — |
| c08-wrong_place_mirror | test | commons | wrong_place | ok | missed | ok | 55 |
| c19-good_closeup | calibration | commons | ok | retake | false_block | glare | — |
| c20-good_rotate | calibration | commons | ok | retake | false_block | overexposed | — |
| c20-good_light | calibration | commons | ok | retake | false_block | overexposed | — |
| c20-good_closeup | calibration | commons | ok | retake | false_block | overexposed | — |
| c20-good_act_edit | calibration | commons | ok | retake | false_block | overexposed | — |
| c20-replay_exact | calibration | commons | replay | retake | caught | overexposed | — |
| c20-replay_earlier | calibration | commons | replay | retake | caught | overexposed | — |
| c20-no_change | calibration | commons | no_change | retake | caught | overexposed | — |
| c22-wrong_place_mirror | test | commons | wrong_place | retake | caught | glare | — |
| c22-replay_exact | test | commons | replay | retake | caught | glare | — |
| c22-replay_reference | test | commons | replay | retake | caught | glare | — |
| c22-replay_earlier | test | commons | replay | retake | caught | glare | — |
| c22-no_change | test | commons | no_change | retake | caught | glare | — |
| c23-good_reshot | test | commons | ok | retake | false_block | glare | — |
| c23-wrong_place_mirror | test | commons | wrong_place | retake | caught | glare | — |
| c23-no_change | test | commons | no_change | retake | caught | glare | — |
| c23-touched_avoid | test | commons | touched_avoid | retake | caught | glare | — |
| c24-good_reshot | test | commons | ok | retake | false_block | glare | — |
| c24-good_view_light | test | commons | ok | retake | false_block | glare | — |
| c24-good_act_edit | test | commons | ok | retake | false_block | glare | — |
| c24-replay_exact | test | commons | replay | retake | caught | glare | — |
| c24-replay_reference | test | commons | replay | retake | caught | glare | — |
| c24-no_change | test | commons | no_change | retake | caught | glare | — |
| c24-touched_avoid | test | commons | touched_avoid | retake | caught | glare | — |
| c25-good_light | calibration | commons | ok | retake | false_block | glare | — |
| c25-good_view_light | calibration | commons | ok | retake | false_block | glare | — |
| c30-good_view_light | test | commons | ok | retake | false_block | blurry | — |
| c30-wrong_place_mirror | test | commons | wrong_place | retake | caught | blurry | — |
| c30-replay_earlier | test | commons | replay | retake | caught | blurry | — |
| c33-good_closeup | calibration | commons | ok | retake | false_block | glare | — |
| c34-good_rotate | calibration | commons | ok | retake | false_block | glare | — |
| c34-good_reshot | calibration | commons | ok | retake | false_block | glare | — |
| c34-good_closeup | calibration | commons | ok | retake | false_block | glare | — |
| c34-replay_exact | calibration | commons | replay | retake | caught | glare | — |
| c34-replay_reference | calibration | commons | replay | retake | caught | glare | — |
| c34-no_change | calibration | commons | no_change | retake | caught | glare | — |
| c34-touched_avoid | calibration | commons | touched_avoid | retake | caught | glare | — |
| c35-good_act_edit | calibration | commons | ok | retake | false_block | glare | — |
| c35-replay_exact | calibration | commons | replay | retake | caught | glare | — |
| c38-blur_motion | test | commons | retake | place_unconfirmed | routed_two_image | place_unconfirmed | 5 |
| c38-replay_earlier | test | commons | replay | retake | caught | blurry_vs_reference | 601 |
| c39-replay_earlier | test | commons | replay | retake | caught | blurry_vs_reference | 736 |
| c40-good_rotate | calibration | commons | ok | retake | false_block | glare | — |
| c40-good_reshot | calibration | commons | ok | retake | false_block | glare | — |
| c40-good_light | calibration | commons | ok | retake | false_block | glare | — |
| c40-wrong_place_mirror | calibration | commons | wrong_place | retake | caught | glare | — |
| c40-replay_earlier | calibration | commons | replay | retake | caught | glare | — |
| c22-real_same_place-c24 | test | commons | ok | retake | false_block | glare | — |
| c24-real_same_place-c22 | test | commons | ok | retake | false_block | glare | — |
| c16-real_same_place-c18 | calibration | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 8 |
| c18-real_same_place-c16 | calibration | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 11 |
| c33-real_same_place-c34 | calibration | commons | ok | retake | false_block | glare | — |
| c34-real_same_place-c35 | calibration | commons | ok | retake | false_block | glare | — |
| c35-real_same_place-c33 | calibration | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 21 |
| c36-real_same_place-c37 | calibration | commons | ok | retake | false_block | blurry_vs_reference | 44 |
| c09-real_same_place-c10 | test | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 6 |
| v0659-real_same_place-v0448 | calibration | own-video | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 34 |
| v0042-real_same_place-v0812 | calibration | own-video | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 22 |
| v1106-real_same_place-v0990 | calibration | own-video | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 6 |
| c22-real_replay_annotated-c23 | test | commons | replay | retake | caught | glare | — |
| v0180-real_blur-v0195 | calibration | own-video | retake | place_unconfirmed | routed_two_image | place_unconfirmed | 16 |
| v0557-real_borderline-v0570 | calibration | own-video | borderline | retake | unscored | blurry_vs_reference | 33 |
| v0659-real_borderline-v0510 | calibration | own-video | borderline | ok | unscored | ok | 26 |
| c19-real_lookalike-c20 | calibration | commons | wrong_place | retake | caught | overexposed | — |
| c29-real_lookalike-v0042 | calibration | commons | wrong_place | retake | caught | glare | — |
| c30-real_lookalike-c23 | test | commons | wrong_place | retake | caught | glare | — |
| c31-real_lookalike-c24 | test | commons | wrong_place | retake | caught | glare | — |
| c31-real_lookalike-c22 | test | commons | wrong_place | retake | caught | glare | — |
| c32-real_lookalike-v0042 | calibration | commons | wrong_place | retake | caught | glare | — |
| c36-real_lookalike-c40 | calibration | commons | wrong_place | retake | caught | glare | — |
