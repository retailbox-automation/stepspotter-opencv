# Perception eval — `--config opencv`

Ran 2026-10-21T11:54:17+00:00 on 99 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 120).

| class | kind | n | caught | missed | false blocks | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| good_rotate | good | 6 | — | — | 0 | 6 | 67.3 | 125.8 | 0 |
| good_reshot | good | 6 | — | — | 0 | 6 | 47.1 | 47.6 | 0 |
| good_light | good | 6 | — | — | 0 | 6 | 46.7 | 50.6 | 0 |
| good_closeup | good | 6 | — | — | 0 | 6 | 38.0 | 48.9 | 0 |
| good_act_edit | good | 6 | — | — | 0 | 6 | 51.4 | 57.0 | 0 |
| blur_gaussian | bad | 6 | 6 | 0 | — | 6 | 4.2 | 4.5 | 0 |
| blur_motion | bad | 6 | 6 | 0 | — | 6 | 4.6 | 29.0 | 0 |
| dark | bad | 6 | 6 | 0 | — | 6 | 4.3 | 4.4 | 0 |
| overexposed | bad | 6 | 6 | 0 | — | 6 | 4.5 | 4.8 | 0 |
| glare | bad | 6 | 6 | 0 | — | 6 | 4.5 | 4.5 | 0 |
| zone_cut | bad | 6 | 6 | 0 | — | 6 | 25.5 | 31.8 | 0 |
| replay_reference | bad | 6 | 6 | 0 | — | 6 | 49.9 | 51.7 | 0 |
| replay_earlier | bad | 6 | 6 | 0 | — | 6 | 73.8 | 77.5 | 0 |
| no_change | bad | 6 | 6 | 0 | — | 6 | 50.6 | 51.4 | 0 |
| touched_avoid | bad | 6 | 6 | 0 | — | 6 | 46.8 | 51.4 | 0 |
| real_same_place | good | 5 | — | — | 3 | 2 | 66.4 | 84.0 | 0 |
| real_wrong_place | bad | 4 | 4 | 0 | — | 4 | 40.4 | 52.0 | 0 |

| slice | n | ran | caught / bad | false blocks / good | decision = expected | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 99 | 99 | 64 / 64 | 3 / 35 | 96 | 45.0 | 74.5 |
| split: calibration | 49 | 49 | 30 / 30 | 2 / 19 | 47 | 46.7 | 76.6 |
| split: test | 50 | 50 | 34 / 34 | 1 / 16 | 49 | 41.8 | 70.7 |

## Failures, every one (published, not averaged away)

| case | split | expected | got | outcome | reason code |
|---|---|---|---|---|---|
| 02-real_same_place-03 | calibration | ok | wrong_place | false_block | no_scene_match |
| 01-real_same_place-03 | calibration | ok | wrong_place | false_block | no_scene_match |
| 04-real_same_place-05 | test | ok | wrong_place | false_block | no_scene_match |
