# Perception eval — `--config opencv` (B)

Ran 2026-10-21T13:17:15+00:00 on 548 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 0). Code: main `ea0354d`, eval `e28400a`; faces checked: True.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| good_rotate | good | 26 | — | — | 0 | — | 26 | 89.8 | 144.8 | 0 |
| good_reshot | good | 23 | — | — | 0 | — | 23 | 82.5 | 112.8 | 0 |
| good_light | good | 25 | — | — | 0 | — | 25 | 72.9 | 118.2 | 0 |
| good_closeup | good | 29 | — | — | 0 | — | 29 | 48.3 | 76.1 | 0 |
| good_act_edit | good | 28 | — | — | 0 | — | 28 | 82.4 | 103.5 | 0 |
| blur_gaussian | bad | 28 | 28 | 0 | — | — | 28 | 24.4 | 91.8 | 0 |
| blur_motion | bad | 32 | 31 | 0 | — | 1 | 31 | 44.2 | 91.6 | 0 |
| dark | bad | 23 | 23 | 0 | — | — | 23 | 21.6 | 47.6 | 0 |
| overexposed | bad | 22 | 22 | 0 | — | — | 22 | 23.9 | 49.9 | 0 |
| glare | bad | 23 | 12 | 11 | — | — | 12 | 59.2 | 94.4 | 0 |
| zone_cut | bad | 29 | 29 | 0 | — | — | 29 | 40.4 | 61.6 | 0 |
| replay_reference | bad | 24 | 24 | 0 | — | — | 24 | 67.5 | 91.6 | 0 |
| replay_earlier | bad | 24 | 24 | 0 | — | — | 23 | 97.5 | 129.7 | 0 |
| no_change | bad | 27 | 27 | 0 | — | — | 27 | 85.2 | 121.0 | 0 |
| touched_avoid | bad | 22 | 22 | 0 | — | — | 22 | 67.3 | 88.2 | 0 |
| real_same_place | good | 24 | — | — | 0 | 10 | 14 | 81.8 | 116.9 | 0 |
| real_wrong_place | bad | 4 | 0 | 0 | — | 4 | 4 | 62.3 | 84.6 | 0 |
| good_view_light | good | 24 | — | — | 3 | — | 21 | 71.9 | 98.4 | 0 |
| wrong_place_mirror | bad | 24 | 1 | 1 | — | 22 | 22 | 76.8 | 100.2 | 0 |
| replay_exact | bad | 25 | 25 | 0 | — | — | 25 | 70.2 | 106.4 | 0 |
| real_replay_annotated | bad | 1 | 0 | 1 | — | — | 0 | 83.6 | 83.6 | 0 |
| real_blur | bad | 4 | 2 | 0 | — | 2 | 2 | 69.8 | 91.6 | 0 |
| real_borderline | unscored | 2 | — | — | — | — | 0 | 65.1 | 65.6 | 0 |
| real_wrong_place_same_room | bad | 3 | 0 | 0 | — | 3 | 3 | 74.4 | 77.2 | 0 |
| real_lookalike | bad | 52 | 1 | 0 | — | 51 | 51 | 85.9 | 156.7 | 0 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 548 | 453 | 271 / 284 | 3 / 169 | 93 | {'llm_single': 180, 'opencv_block': 275, 'llm_two_image': 93} | 67.8 | 114.2 |
| split: calibration | 308 | 251 | 141 / 148 | 1 / 103 | 55 | {'llm_single': 110, 'opencv_block': 143, 'llm_two_image': 55} | 67.7 | 127.1 |
| split: test | 240 | 202 | 130 / 136 | 2 / 66 | 38 | {'llm_single': 70, 'opencv_block': 132, 'llm_two_image': 38} | 68.2 | 110.6 |
| source: onq | 125 | 104 | 64 / 66 | 1 / 38 | 21 | {'llm_single': 39, 'opencv_block': 65, 'llm_two_image': 21} | 62.0 | 96.7 |
| source: commons | 405 | 343 | 205 / 216 | 2 / 127 | 62 | {'llm_single': 136, 'opencv_block': 207, 'llm_two_image': 62} | 71.8 | 118.2 |
| source: own-video | 18 | 6 | 2 / 2 | 0 / 4 | 10 | {'llm_single': 5, 'llm_two_image': 10, 'opencv_block': 3} | 71.0 | 95.9 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| 03-glare | calibration | onq | retake | ok | missed | ok | 1238 |
| 04-glare | test | onq | retake | ok | missed | ok | 471 |
| 02-real_same_place-03 | calibration | onq | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 8 |
| 01-real_same_place-03 | calibration | onq | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 7 |
| 04-real_same_place-05 | test | onq | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 4 |
| 06-good_view_light | test | onq | ok | touched_avoid | false_block | change_in_avoid | 1218 |
| c01-glare | calibration | commons | retake | ok | missed | ok | 1518 |
| c04-good_view_light | calibration | commons | ok | touched_avoid | false_block | change_in_avoid | 1147 |
| c08-wrong_place_mirror | test | commons | wrong_place | ok | missed | ok | 55 |
| c10-glare | test | commons | retake | ok | missed | ok | 1416 |
| c11-glare | calibration | commons | retake | ok | missed | ok | 1331 |
| c13-glare | calibration | commons | retake | ok | missed | ok | 909 |
| c14-glare | calibration | commons | retake | ok | missed | ok | 1448 |
| c15-glare | test | commons | retake | ok | missed | ok | 1665 |
| c25-glare | calibration | commons | retake | ok | missed | ok | 1548 |
| c27-glare | test | commons | retake | ok | missed | ok | 652 |
| c30-good_view_light | test | commons | ok | retake | false_block | blurry | — |
| c30-wrong_place_mirror | test | commons | wrong_place | retake | caught | blurry | — |
| c30-replay_earlier | test | commons | replay | retake | caught | blurry | — |
| c33-glare | calibration | commons | retake | ok | missed | ok | 1464 |
| c38-blur_motion | test | commons | retake | place_unconfirmed | routed_two_image | place_unconfirmed | 5 |
| c16-real_same_place-c18 | calibration | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 8 |
| c18-real_same_place-c16 | calibration | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 11 |
| c35-real_same_place-c33 | calibration | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 21 |
| c09-real_same_place-c10 | test | commons | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 6 |
| v0659-real_same_place-v0448 | calibration | own-video | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 34 |
| v0042-real_same_place-v0812 | calibration | own-video | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 22 |
| v1106-real_same_place-v0990 | calibration | own-video | ok | place_unconfirmed | routed_two_image | place_unconfirmed | 6 |
| c22-real_replay_annotated-c23 | test | commons | replay | ok | missed | ok | 1512 |
| v0659-real_blur-v0240 | calibration | own-video | retake | place_unconfirmed | routed_two_image | place_unconfirmed | 8 |
| v0990-real_blur-v0900 | calibration | own-video | retake | place_unconfirmed | routed_two_image | place_unconfirmed | 0 |
| v0557-real_borderline-v0570 | calibration | own-video | borderline | retake | unscored | blurry_vs_reference | 33 |
| v0659-real_borderline-v0510 | calibration | own-video | borderline | ok | unscored | ok | 26 |
| c19-real_lookalike-c20 | calibration | commons | wrong_place | retake | caught | overexposed | — |
