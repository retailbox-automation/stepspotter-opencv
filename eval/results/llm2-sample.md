# Perception eval — `--config llm2` (A')

Ran 2026-10-21T12:31:56+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 54 (cap 54). Code: main `c7c84e0`, eval `082fabd`; faces checked: —.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 2 | — | — | 4665.4 | 7064.0 | 5 |
| real_wrong_place | bad | 2 | 2 | 0 | — | — | — | 3227.7 | 3599.9 | 2 |
| good_light | good | 2 | — | — | 0 | — | — | 4099.4 | 4116.4 | 2 |
| replay_reference | bad | 2 | 1 | 1 | — | — | — | 3691.2 | 4061.9 | 2 |
| good_reshot | good | 2 | — | — | 0 | — | — | 3536.9 | 3671.4 | 2 |
| overexposed | bad | 2 | 0 | 2 | — | — | — | 3578.5 | 3659.6 | 2 |
| no_change | bad | 2 | 0 | 2 | — | — | — | 3852.1 | 4039.9 | 2 |
| good_closeup | good | 2 | — | — | 0 | — | — | 3575.4 | 3628.4 | 2 |
| dark | bad | 2 | 2 | 0 | — | — | — | 3427.9 | 3532.3 | 2 |
| good_rotate | good | 2 | — | — | 0 | — | — | 4379.8 | 4513.3 | 2 |
| zone_cut | bad | 2 | 1 | 1 | — | — | — | 4005.8 | 4289.3 | 2 |
| wrong_place_mirror | bad | 2 | 0 | 2 | — | — | — | 3552.9 | 3696.7 | 2 |
| good_act_edit | good | 2 | — | — | 0 | — | — | 4355.0 | 4962.7 | 2 |
| glare | bad | 2 | 2 | 0 | — | — | — | 4016.7 | 4067.3 | 2 |
| touched_avoid | bad | 2 | 0 | 2 | — | — | — | 3706.9 | 3890.9 | 2 |
| good_view_light | good | 2 | — | — | 1 | — | — | 3301.3 | 3736.5 | 2 |
| blur_gaussian | bad | 2 | 1 | 1 | — | — | — | 3531.6 | 3618.6 | 2 |
| replay_exact | bad | 2 | 1 | 1 | — | — | — | 3358.2 | 3677.2 | 2 |
| blur_motion | bad | 2 | 2 | 0 | — | — | — | 3622.1 | 3622.6 | 2 |
| replay_earlier | bad | 2 | 1 | 1 | — | — | — | 5756.2 | 6968.5 | 2 |
| real_replay_annotated | bad | 1 | 0 | 1 | — | — | — | 3651.3 | 3651.3 | 1 |
| real_blur | bad | 2 | 2 | 0 | — | — | — | 3297.9 | 3493.7 | 2 |
| real_wrong_place_same_room | bad | 2 | 2 | 0 | — | — | — | 3634.8 | 3715.1 | 2 |
| real_lookalike | bad | 6 | 6 | 0 | — | — | — | 4098.2 | 4253.7 | 6 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 54 | 23 / 37 | 3 / 17 | 0 | — | 3688.6 | 5026.6 |
| split: calibration | 4 | 4 | 4 / 4 | 0 / 0 | 0 | — | 3530.6 | 3697.2 |
| split: test | 50 | 50 | 19 / 33 | 3 / 17 | 0 | — | 3701.8 | 5027.7 |
| source: onq | 3 | 3 | 2 / 2 | 1 / 1 | 0 | — | 3641.3 | 3792.4 |
| source: commons | 47 | 47 | 17 / 31 | 2 / 16 | 0 | — | 3712.7 | 5028.5 |
| source: own-video | 4 | 4 | 4 / 4 | 0 / 0 | 0 | — | 3530.6 | 3697.2 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| 04-real_same_place-05 | test | onq | ok | called -> model passed=False, same_place=True | false_block |  | — |
| c03-replay_reference | test | commons | replay | called -> model passed=True, same_place=True | missed |  | — |
| c05-overexposed | test | commons | retake | called -> model passed=True, same_place=True | missed |  | — |
| c05-no_change | test | commons | no_change | called -> model passed=True, same_place=True | missed |  | — |
| c08-zone_cut | test | commons | retake | called -> model passed=True, same_place=True | missed |  | — |
| c08-wrong_place_mirror | test | commons | wrong_place | called -> model passed=True, same_place=True | missed |  | — |
| c09-overexposed | test | commons | retake | called -> model passed=True, same_place=True | missed |  | — |
| c09-touched_avoid | test | commons | touched_avoid | called -> model passed=True, same_place=True | missed |  | — |
| c10-touched_avoid | test | commons | touched_avoid | called -> model passed=True, same_place=True | missed |  | — |
| c15-good_view_light | test | commons | ok | called -> model passed=False, same_place=True | false_block |  | — |
| c21-blur_gaussian | test | commons | retake | called -> model passed=True, same_place=True | missed |  | — |
| c23-no_change | test | commons | no_change | called -> model passed=True, same_place=True | missed |  | — |
| c27-replay_exact | test | commons | replay | called -> model passed=True, same_place=True | missed |  | — |
| c38-wrong_place_mirror | test | commons | wrong_place | called -> model passed=True, same_place=True | missed |  | — |
| c39-replay_earlier | test | commons | replay | called -> model passed=True, same_place=True | missed |  | — |
| c09-real_same_place-c10 | test | commons | ok | called -> model passed=False, same_place=True | false_block |  | — |
| c22-real_replay_annotated-c23 | test | commons | replay | called -> model passed=True, same_place=True | missed |  | — |
