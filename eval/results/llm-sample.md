# Perception eval — `--config llm` (A)

Ran 2026-10-21T12:28:19+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 54 (cap 54). Code: main `43c1520`, eval `082fabd`; faces checked: —.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 1 | — | — | 2987.7 | 3153.8 | 5 |
| real_wrong_place | bad | 2 | 2 | 0 | — | — | — | 3351.7 | 3599.0 | 2 |
| good_light | good | 2 | — | — | 0 | — | — | 2804.1 | 2830.7 | 2 |
| replay_reference | bad | 2 | 0 | 2 | — | — | — | 2811.2 | 2834.4 | 2 |
| good_reshot | good | 2 | — | — | 0 | — | — | 2846.8 | 2990.3 | 2 |
| overexposed | bad | 2 | 0 | 2 | — | — | — | 3104.7 | 3235.0 | 2 |
| no_change | bad | 2 | 0 | 2 | — | — | — | 3070.5 | 3267.1 | 2 |
| good_closeup | good | 2 | — | — | 1 | — | — | 2516.6 | 2577.8 | 2 |
| dark | bad | 2 | 2 | 0 | — | — | — | 2937.8 | 2960.0 | 2 |
| good_rotate | good | 2 | — | — | 0 | — | — | 3113.6 | 3557.4 | 2 |
| zone_cut | bad | 2 | 1 | 1 | — | — | — | 2667.4 | 3012.6 | 2 |
| wrong_place_mirror | bad | 2 | 0 | 2 | — | — | — | 3101.9 | 3202.8 | 2 |
| good_act_edit | good | 2 | — | — | 0 | — | — | 2972.1 | 3178.0 | 2 |
| glare | bad | 2 | 1 | 1 | — | — | — | 3923.1 | 4370.0 | 2 |
| touched_avoid | bad | 2 | 0 | 2 | — | — | — | 3710.8 | 3922.6 | 2 |
| good_view_light | good | 2 | — | — | 1 | — | — | 2906.8 | 3297.7 | 2 |
| blur_gaussian | bad | 2 | 1 | 1 | — | — | — | 3008.2 | 3144.6 | 2 |
| replay_exact | bad | 2 | 0 | 2 | — | — | — | 2653.2 | 2755.3 | 2 |
| blur_motion | bad | 2 | 2 | 0 | — | — | — | 3158.2 | 3541.8 | 2 |
| replay_earlier | bad | 2 | 0 | 2 | — | — | — | 2952.8 | 3323.9 | 2 |
| real_replay_annotated | bad | 1 | 0 | 1 | — | — | — | 3037.3 | 3037.3 | 1 |
| real_blur | bad | 2 | 2 | 0 | — | — | — | 2135.1 | 2151.8 | 2 |
| real_wrong_place_same_room | bad | 2 | 2 | 0 | — | — | — | 3542.1 | 4163.9 | 2 |
| real_lookalike | bad | 6 | 2 | 4 | — | — | — | 3169.1 | 3258.3 | 6 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 54 | 15 / 37 | 3 / 17 | 0 | — | 2988.8 | 3738.4 |
| split: calibration | 4 | 4 | 4 / 4 | 0 / 0 | 0 | — | 2502.4 | 4025.7 |
| split: test | 50 | 50 | 11 / 33 | 3 / 17 | 0 | — | 2998.1 | 3617.6 |
| source: onq | 3 | 3 | 2 / 2 | 1 / 1 | 0 | — | 3178.3 | 3581.7 |
| source: commons | 47 | 47 | 9 / 31 | 2 / 16 | 0 | — | 2987.7 | 3600.0 |
| source: own-video | 4 | 4 | 4 / 4 | 0 / 0 | 0 | — | 2502.4 | 4025.7 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| 04-real_same_place-05 | test | onq | ok | called -> model passed=False | false_block |  | — |
| c03-replay_reference | test | commons | replay | called -> model passed=True | missed |  | — |
| c05-overexposed | test | commons | retake | called -> model passed=True | missed |  | — |
| c05-no_change | test | commons | no_change | called -> model passed=True | missed |  | — |
| c08-good_closeup | test | commons | ok | called -> model passed=False | false_block |  | — |
| c08-zone_cut | test | commons | retake | called -> model passed=True | missed |  | — |
| c08-wrong_place_mirror | test | commons | wrong_place | called -> model passed=True | missed |  | — |
| c09-overexposed | test | commons | retake | called -> model passed=True | missed |  | — |
| c09-glare | test | commons | retake | called -> model passed=True | missed |  | — |
| c09-touched_avoid | test | commons | touched_avoid | called -> model passed=True | missed |  | — |
| c10-touched_avoid | test | commons | touched_avoid | called -> model passed=True | missed |  | — |
| c15-good_view_light | test | commons | ok | called -> model passed=False | false_block |  | — |
| c21-blur_gaussian | test | commons | retake | called -> model passed=True | missed |  | — |
| c22-replay_exact | test | commons | replay | called -> model passed=True | missed |  | — |
| c23-no_change | test | commons | no_change | called -> model passed=True | missed |  | — |
| c24-replay_reference | test | commons | replay | called -> model passed=True | missed |  | — |
| c27-replay_exact | test | commons | replay | called -> model passed=True | missed |  | — |
| c30-replay_earlier | test | commons | replay | called -> model passed=True | missed |  | — |
| c38-wrong_place_mirror | test | commons | wrong_place | called -> model passed=True | missed |  | — |
| c39-replay_earlier | test | commons | replay | called -> model passed=True | missed |  | — |
| c22-real_replay_annotated-c23 | test | commons | replay | called -> model passed=True | missed |  | — |
| c03-real_lookalike-c05 | test | commons | wrong_place | called -> model passed=True | missed |  | — |
| c05-real_lookalike-c03 | test | commons | wrong_place | called -> model passed=True | missed |  | — |
| c22-real_lookalike-c31 | test | commons | wrong_place | called -> model passed=True | missed |  | — |
| c31-real_lookalike-c24 | test | commons | wrong_place | called -> model passed=True | missed |  | — |
