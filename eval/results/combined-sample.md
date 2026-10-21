# Perception eval — `--config combined` (C)

Ran 2026-10-21T12:33:41+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 24 (cap 42). Code: main `c7c84e0`, eval `082fabd`; faces checked: True.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 4 | — | — | 52.3 | 161.1 | 3 |
| real_wrong_place | bad | 2 | 2 | 0 | — | — | — | 126.6 | 163.8 | 2 |
| good_light | good | 2 | — | — | 1 | — | — | 72.8 | 98.7 | 1 |
| replay_reference | bad | 2 | 2 | 0 | — | — | — | 89.5 | 148.4 | 0 |
| good_reshot | good | 2 | — | — | 0 | — | — | 98.7 | 103.7 | 2 |
| overexposed | bad | 2 | 2 | 0 | — | — | — | 34.3 | 36.0 | 0 |
| no_change | bad | 2 | 2 | 0 | — | — | — | 62.7 | 81.9 | 0 |
| good_closeup | good | 2 | — | — | 2 | — | — | 31.3 | 51.2 | 1 |
| dark | bad | 2 | 2 | 0 | — | — | — | 17.5 | 17.9 | 0 |
| good_rotate | good | 2 | — | — | 0 | — | — | 105.8 | 114.0 | 2 |
| zone_cut | bad | 2 | 2 | 0 | — | — | — | 48.1 | 56.6 | 0 |
| wrong_place_mirror | bad | 2 | 0 | 2 | — | — | — | 82.4 | 100.8 | 2 |
| good_act_edit | good | 2 | — | — | 0 | — | — | 127.5 | 150.2 | 2 |
| glare | bad | 2 | 2 | 0 | — | — | — | 33.5 | 34.7 | 0 |
| touched_avoid | bad | 2 | 2 | 0 | — | — | — | 115.3 | 123.9 | 0 |
| good_view_light | good | 2 | — | — | 1 | — | — | 84.6 | 103.3 | 2 |
| blur_gaussian | bad | 2 | 2 | 0 | — | — | — | 26.2 | 33.0 | 0 |
| replay_exact | bad | 2 | 2 | 0 | — | — | — | 43.5 | 50.7 | 0 |
| blur_motion | bad | 2 | 2 | 0 | — | — | — | 58.0 | 81.7 | 0 |
| replay_earlier | bad | 2 | 2 | 0 | — | — | — | 29.5 | 41.5 | 0 |
| real_replay_annotated | bad | 1 | 1 | 0 | — | — | — | 39.3 | 39.3 | 0 |
| real_blur | bad | 2 | 2 | 0 | — | — | — | 25.2 | 26.2 | 0 |
| real_wrong_place_same_room | bad | 2 | 2 | 0 | — | — | — | 91.8 | 96.7 | 2 |
| real_lookalike | bad | 6 | 6 | 0 | — | — | — | 87.7 | 108.4 | 5 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 54 | 35 / 37 | 8 / 17 | 0 | {'llm_two_image': 12, 'opencv_block': 30, 'llm_single': 12} | 95.0 | 5158.9 |
| split: calibration | 4 | 4 | 4 / 4 | 0 / 0 | 0 | {'opencv_block': 2, 'llm_two_image': 2} | 1691.0 | 3812.8 |
| split: test | 50 | 50 | 31 / 33 | 8 / 17 | 0 | {'llm_two_image': 10, 'opencv_block': 28, 'llm_single': 12} | 95.0 | 5215.9 |
| source: onq | 3 | 3 | 2 / 2 | 1 / 1 | 0 | {'llm_two_image': 3} | 3999.3 | 4391.7 |
| source: commons | 47 | 47 | 29 / 31 | 7 / 16 | 0 | {'opencv_block': 28, 'llm_single': 12, 'llm_two_image': 7} | 84.1 | 5258.6 |
| source: own-video | 4 | 4 | 4 / 4 | 0 / 0 | 0 | {'opencv_block': 2, 'llm_two_image': 2} | 1691.0 | 3812.8 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| 04-real_same_place-05 | test | onq | ok | place_unconfirmed -> model passed=False, same_place=True | false_block | place_unconfirmed | 4 |
| c03-good_light | test | commons | ok | retake | false_block | glare | — |
| c07-good_closeup | test | commons | ok | retake | false_block | glare | — |
| c08-good_closeup | test | commons | ok | ok -> model passed=False | false_block | ok | 512 |
| c08-wrong_place_mirror | test | commons | wrong_place | ok -> model passed=True | missed | ok | 55 |
| c15-good_view_light | test | commons | ok | ok -> model passed=False | false_block | ok | 996 |
| c38-wrong_place_mirror | test | commons | wrong_place | place_unconfirmed -> model passed=True, same_place=True | missed | place_unconfirmed | 23 |
| c22-real_same_place-c24 | test | commons | ok | retake | false_block | glare | — |
| c24-real_same_place-c22 | test | commons | ok | retake | false_block | glare | — |
| c09-real_same_place-c10 | test | commons | ok | place_unconfirmed -> model passed=False, same_place=True | false_block | place_unconfirmed | 6 |
