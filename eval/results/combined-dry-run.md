# Perception eval — `--config combined`

Ran 2026-10-21T11:54:22+00:00 on 99 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 120); DRY RUN.

| class | kind | n | caught | missed | false blocks | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| good_rotate | good | 6 | — | — | 0 | — | 68.1 | 123.9 | 0 |
| good_reshot | good | 6 | — | — | 0 | — | 47.6 | 49.9 | 0 |
| good_light | good | 6 | — | — | 0 | — | 46.6 | 55.5 | 0 |
| good_closeup | good | 6 | — | — | 0 | — | 38.3 | 49.1 | 0 |
| good_act_edit | good | 6 | — | — | 0 | — | 50.0 | 56.3 | 0 |
| blur_gaussian | bad | 6 | 6 | 0 | — | — | 4.4 | 4.8 | 0 |
| blur_motion | bad | 6 | 6 | 0 | — | — | 4.8 | 28.7 | 0 |
| dark | bad | 6 | 6 | 0 | — | — | 4.4 | 4.9 | 0 |
| overexposed | bad | 6 | 6 | 0 | — | — | 4.6 | 4.9 | 0 |
| glare | bad | 6 | 6 | 0 | — | — | 4.4 | 4.8 | 0 |
| zone_cut | bad | 6 | 6 | 0 | — | — | 27.2 | 31.3 | 0 |
| replay_reference | bad | 6 | 6 | 0 | — | — | 49.5 | 50.2 | 0 |
| replay_earlier | bad | 6 | 6 | 0 | — | — | 73.1 | 76.7 | 0 |
| no_change | bad | 6 | 6 | 0 | — | — | 50.1 | 58.0 | 0 |
| touched_avoid | bad | 6 | 6 | 0 | — | — | 47.0 | 49.2 | 0 |
| real_same_place | good | 5 | — | — | 3 | — | 71.0 | 84.5 | 0 |
| real_wrong_place | bad | 4 | 4 | 0 | — | — | 41.2 | 51.5 | 0 |

| slice | n | ran | caught / bad | false blocks / good | decision = expected | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 99 | 67 | 64 / 64 | 3 / 3 | — | 44.5 | 73.8 |
| split: calibration | 49 | 32 | 30 / 30 | 2 / 2 | — | 46.4 | 73.2 |
| split: test | 50 | 35 | 34 / 34 | 1 / 1 | — | 41.2 | 71.5 |

## Failures, every one (published, not averaged away)

| case | split | expected | got | outcome | reason code |
|---|---|---|---|---|---|
| 02-real_same_place-03 | calibration | ok | wrong_place | false_block | no_scene_match |
| 01-real_same_place-03 | calibration | ok | wrong_place | false_block | no_scene_match |
| 04-real_same_place-05 | test | ok | wrong_place | false_block | no_scene_match |

## Dry run: 32 model calls would be made

- 01-good_rotate: eval/cases/01-good_rotate.jpg — step "Confirm the low-voltage panel"
- 01-good_reshot: eval/cases/01-good_reshot.jpg — step "Confirm the low-voltage panel"
- 01-good_light: eval/cases/01-good_light.jpg — step "Confirm the low-voltage panel"
- 01-good_closeup: eval/cases/01-good_closeup.jpg — step "Confirm the low-voltage panel"
- 01-good_act_edit: eval/cases/01-good_act_edit.jpg — step "Confirm the low-voltage panel"
- 02-good_rotate: eval/cases/02-good_rotate.jpg — step "Find the coax splitter"
- 02-good_reshot: eval/cases/02-good_reshot.jpg — step "Find the coax splitter"
- 02-good_light: eval/cases/02-good_light.jpg — step "Find the coax splitter"
- 02-good_closeup: eval/cases/02-good_closeup.jpg — step "Find the coax splitter"
- 02-good_act_edit: eval/cases/02-good_act_edit.jpg — step "Find the coax splitter"
- 03-good_rotate: eval/cases/03-good_rotate.jpg — step "Confirm the run lands at the module"
- 03-good_reshot: eval/cases/03-good_reshot.jpg — step "Confirm the run lands at the module"
- 03-good_light: eval/cases/03-good_light.jpg — step "Confirm the run lands at the module"
- 03-good_closeup: eval/cases/03-good_closeup.jpg — step "Confirm the run lands at the module"
- 03-good_act_edit: eval/cases/03-good_act_edit.jpg — step "Confirm the run lands at the module"
- 04-good_rotate: eval/cases/04-good_rotate.jpg — step "Snap the jack into the plate"
- 04-good_reshot: eval/cases/04-good_reshot.jpg — step "Snap the jack into the plate"
- 04-good_light: eval/cases/04-good_light.jpg — step "Snap the jack into the plate"
- 04-good_closeup: eval/cases/04-good_closeup.jpg — step "Snap the jack into the plate"
- 04-good_act_edit: eval/cases/04-good_act_edit.jpg — step "Snap the jack into the plate"
- 05-good_rotate: eval/cases/05-good_rotate.jpg — step "Lay the pairs into the jack"
- 05-good_reshot: eval/cases/05-good_reshot.jpg — step "Lay the pairs into the jack"
- 05-good_light: eval/cases/05-good_light.jpg — step "Lay the pairs into the jack"
- 05-good_closeup: eval/cases/05-good_closeup.jpg — step "Lay the pairs into the jack"
- 05-good_act_edit: eval/cases/05-good_act_edit.jpg — step "Lay the pairs into the jack"
- 06-good_rotate: eval/cases/06-good_rotate.jpg — step "Seat the cable in the module"
- 06-good_reshot: eval/cases/06-good_reshot.jpg — step "Seat the cable in the module"
- 06-good_light: eval/cases/06-good_light.jpg — step "Seat the cable in the module"
- 06-good_closeup: eval/cases/06-good_closeup.jpg — step "Seat the cable in the module"
- 06-good_act_edit: eval/cases/06-good_act_edit.jpg — step "Seat the cable in the module"
- 02-real_same_place-01: src/stepspotter/web/demo_photos/01-panel-overview.jpg — step "Find the coax splitter"
- 01-real_same_place-02: src/stepspotter/web/demo_photos/02-panel-inside.jpg — step "Confirm the low-voltage panel"
