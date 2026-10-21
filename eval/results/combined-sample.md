# Perception eval — `--config combined` (C)

Ran 2026-10-21T13:19:23+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 31 (cap 58). Code: main `3f75518`, eval `e28400a`; faces checked: True.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 2 | — | — | 81.7 | 148.2 | 5 |
| real_wrong_place | bad | 2 | 2 | 0 | — | — | — | 73.6 | 75.4 | 2 |
| good_light | good | 2 | — | — | 0 | — | — | 144.8 | 169.0 | 2 |
| replay_reference | bad | 2 | 2 | 0 | — | — | — | 91.5 | 92.7 | 0 |
| good_reshot | good | 2 | — | — | 0 | — | — | 100.3 | 104.4 | 2 |
| overexposed | bad | 2 | 2 | 0 | — | — | — | 46.7 | 48.2 | 0 |
| no_change | bad | 2 | 2 | 0 | — | — | — | 118.6 | 129.9 | 0 |
| good_closeup | good | 2 | — | — | 1 | — | — | 78.0 | 83.9 | 2 |
| dark | bad | 2 | 2 | 0 | — | — | — | 31.8 | 41.3 | 0 |
| good_rotate | good | 2 | — | — | 0 | — | — | 143.8 | 147.7 | 2 |
| zone_cut | bad | 2 | 2 | 0 | — | — | — | 88.1 | 111.8 | 0 |
| wrong_place_mirror | bad | 2 | 0 | 2 | — | — | — | 97.7 | 119.7 | 2 |
| good_act_edit | good | 2 | — | — | 0 | — | — | 121.7 | 149.7 | 2 |
| glare | bad | 2 | 2 | 0 | — | — | — | 85.3 | 86.9 | 0 |
| touched_avoid | bad | 2 | 2 | 0 | — | — | — | 98.8 | 109.1 | 0 |
| good_view_light | good | 2 | — | — | 1 | — | — | 96.6 | 114.6 | 2 |
| blur_gaussian | bad | 2 | 2 | 0 | — | — | — | 31.7 | 41.1 | 0 |
| replay_exact | bad | 2 | 2 | 0 | — | — | — | 95.0 | 120.2 | 0 |
| blur_motion | bad | 2 | 2 | 0 | — | — | — | 89.7 | 90.7 | 0 |
| replay_earlier | bad | 2 | 2 | 0 | — | — | — | 57.8 | 90.8 | 0 |
| real_replay_annotated | bad | 1 | 0 | 1 | — | — | — | 90.5 | 90.5 | 1 |
| real_blur | bad | 2 | 2 | 0 | — | — | — | 57.0 | 80.2 | 1 |
| real_wrong_place_same_room | bad | 2 | 2 | 0 | — | — | — | 121.2 | 148.5 | 2 |
| real_lookalike | bad | 6 | 6 | 0 | — | — | — | 94.5 | 112.7 | 6 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 54 | 34 / 37 | 4 / 17 | 0 | {'llm_two_image': 14, 'llm_single': 17, 'opencv_block': 23} | 2919.8 | 4555.7 |
| split: calibration | 4 | 4 | 4 / 4 | 0 / 0 | 0 | {'llm_two_image': 3, 'opencv_block': 1} | 3487.7 | 3820.2 |
| split: test | 50 | 50 | 30 / 33 | 4 / 17 | 0 | {'llm_two_image': 11, 'llm_single': 17, 'opencv_block': 22} | 2829.1 | 4568.4 |
| source: onq | 3 | 3 | 2 / 2 | 1 / 1 | 0 | {'llm_two_image': 3} | 3595.4 | 3705.3 |
| source: commons | 47 | 47 | 28 / 31 | 3 / 16 | 0 | {'llm_single': 17, 'opencv_block': 22, 'llm_two_image': 8} | 2640.1 | 4577.9 |
| source: own-video | 4 | 4 | 4 / 4 | 0 / 0 | 0 | {'llm_two_image': 3, 'opencv_block': 1} | 3487.7 | 3820.2 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| 04-real_same_place-05 | test | onq | ok | place_unconfirmed -> model passed=False, same_place=True | false_block | place_unconfirmed | 4 |
| c08-good_closeup | test | commons | ok | ok -> model passed=False | false_block | ok | 512 |
| c08-wrong_place_mirror | test | commons | wrong_place | ok -> model passed=True | missed | ok | 55 |
| c15-good_view_light | test | commons | ok | ok -> model passed=False | false_block | ok | 996 |
| c38-wrong_place_mirror | test | commons | wrong_place | place_unconfirmed -> model passed=True, same_place=True | missed | place_unconfirmed | 23 |
| c09-real_same_place-c10 | test | commons | ok | place_unconfirmed -> model passed=False, same_place=True | false_block | place_unconfirmed | 6 |
| c22-real_replay_annotated-c23 | test | commons | replay | ok -> model passed=True | missed | ok | 1512 |
