# Perception eval — `--config combined` (C)

Ran 2026-10-21T12:25:11+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 0); DRY RUN. Code: main `43c1520`, eval `43c1520`; faces checked: True.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 2 | — | — | 48.1 | 139.7 | 0 |
| real_wrong_place | bad | 2 | 0 | 0 | — | — | — | 70.7 | 70.9 | 0 |
| good_light | good | 2 | — | — | 1 | — | — | 77.2 | 111.0 | 0 |
| replay_reference | bad | 2 | 2 | 0 | — | — | — | 101.3 | 170.2 | 0 |
| good_reshot | good | 2 | — | — | 0 | — | — | 96.0 | 103.6 | 0 |
| overexposed | bad | 2 | 2 | 0 | — | — | — | 36.2 | 42.3 | 0 |
| no_change | bad | 2 | 2 | 0 | — | — | — | 59.6 | 78.5 | 0 |
| good_closeup | good | 2 | — | — | 1 | — | — | 32.0 | 52.3 | 0 |
| dark | bad | 2 | 2 | 0 | — | — | — | 16.4 | 16.4 | 0 |
| good_rotate | good | 2 | — | — | 0 | — | — | 105.6 | 120.7 | 0 |
| zone_cut | bad | 2 | 2 | 0 | — | — | — | 47.2 | 56.8 | 0 |
| wrong_place_mirror | bad | 2 | 0 | 0 | — | — | — | 77.9 | 92.8 | 0 |
| good_act_edit | good | 2 | — | — | 0 | — | — | 119.1 | 132.0 | 0 |
| glare | bad | 2 | 2 | 0 | — | — | — | 37.7 | 38.4 | 0 |
| touched_avoid | bad | 2 | 2 | 0 | — | — | — | 93.9 | 101.1 | 0 |
| good_view_light | good | 2 | — | — | 0 | — | — | 86.5 | 103.5 | 0 |
| blur_gaussian | bad | 2 | 2 | 0 | — | — | — | 28.1 | 38.7 | 0 |
| replay_exact | bad | 2 | 2 | 0 | — | — | — | 42.3 | 51.0 | 0 |
| blur_motion | bad | 2 | 2 | 0 | — | — | — | 62.2 | 84.4 | 0 |
| replay_earlier | bad | 2 | 2 | 0 | — | — | — | 30.5 | 44.1 | 0 |
| real_replay_annotated | bad | 1 | 1 | 0 | — | — | — | 34.1 | 34.1 | 0 |
| real_blur | bad | 2 | 2 | 0 | — | — | — | 24.4 | 25.3 | 0 |
| real_wrong_place_same_room | bad | 2 | 0 | 0 | — | — | — | 92.3 | 96.8 | 0 |
| real_lookalike | bad | 6 | 1 | 0 | — | — | — | 91.0 | 99.7 | 0 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 30 | 26 / 26 | 4 / 4 | 0 | {'llm_two_image': 12, 'opencv_block': 30, 'llm_single': 12} | 36.7 | 95.1 |
| split: calibration | 4 | 2 | 2 / 2 | 0 / 0 | 0 | {'opencv_block': 2, 'llm_two_image': 2} | 24.4 | 25.3 |
| split: test | 50 | 28 | 24 / 24 | 4 / 4 | 0 | {'llm_two_image': 10, 'opencv_block': 28, 'llm_single': 12} | 37.3 | 96.6 |
| source: onq | 3 | 0 | 0 / 0 | 0 / 0 | 0 | {'llm_two_image': 3} | — | — |
| source: commons | 47 | 28 | 24 / 24 | 4 / 4 | 0 | {'opencv_block': 28, 'llm_single': 12, 'llm_two_image': 7} | 37.3 | 96.6 |
| source: own-video | 4 | 2 | 2 / 2 | 0 / 0 | 0 | {'opencv_block': 2, 'llm_two_image': 2} | 24.4 | 25.3 |

## Failures, every one (published, not averaged away)

| case | split | source | expected | got | outcome | reason code | inliers |
|---|---|---|---|---|---|---|---:|
| c03-good_light | test | commons | ok | retake | false_block | glare | — |
| c07-good_closeup | test | commons | ok | retake | false_block | glare | — |
| c22-real_same_place-c24 | test | commons | ok | retake | false_block | glare | — |
| c24-real_same_place-c22 | test | commons | ok | retake | false_block | glare | — |

## Dry run: 24 model calls would be made

- 04-real_same_place-05 (two_image): fixtures/onq-keystone-smoke/steps/02-seat-pairs.jpg — step "Snap the jack into the plate"
- 04-real_wrong_place-06 (two_image): fixtures/onq-keystone-smoke/redteam/R2-evidence-absent.jpg — step "Snap the jack into the plate"
- 06-real_wrong_place-05 (two_image): fixtures/onq-keystone-smoke/steps/02-seat-pairs.jpg — step "Seat the cable in the module"
- c05-good_reshot (single): eval/cases/c05-good_reshot.jpg — step "Find the patch panel"
- c08-good_rotate (single): eval/cases/c08-good_rotate.jpg — step "Find the patch panel"
- c08-good_closeup (single): eval/cases/c08-good_closeup.jpg — step "Find the patch panel"
- c08-wrong_place_mirror (single): eval/cases/c08-wrong_place_mirror.jpg — step "Find the patch panel"
- c09-good_act_edit (single): eval/cases/c09-good_act_edit.jpg — step "Find the patch panel"
- c12-good_rotate (single): eval/cases/c12-good_rotate.jpg — step "Check the network wall jack"
- c12-good_reshot (single): eval/cases/c12-good_reshot.jpg — step "Check the network wall jack"
- c12-good_act_edit (single): eval/cases/c12-good_act_edit.jpg — step "Check the network wall jack"
- c15-good_view_light (single): eval/cases/c15-good_view_light.jpg — step "Check the jack's wiring"
- c23-good_light (single): eval/cases/c23-good_light.jpg — step "Check the sink trap"
- c27-good_view_light (single): eval/cases/c27-good_view_light.jpg — step "Run the tap"
- c38-wrong_place_mirror (two_image): eval/cases/c38-wrong_place_mirror.jpg — step "Check the downspout outlet"
- c27-real_same_place-c28 (single): eval/cases/public/commons/c28-247-Home-Rescue-tap-sink-plumbing-water.jpg — step "Run the tap"
- c09-real_same_place-c10 (two_image): eval/cases/public/commons/c10-Panduit-Pan-Net-Cable-Management-System.jpg — step "Find the patch panel"
- v0659-real_wrong_place_same_room-v1050 (two_image): eval/cases/public/own-sink-video/f1050.jpg — step "Check the sink trap"
- v0812-real_wrong_place_same_room-v0990 (two_image): eval/cases/public/own-sink-video/f0990.jpg — step "Check the supply valve"
- c03-real_lookalike-c05 (two_image): eval/cases/public/commons/c05-Patchpanel.jpg — step "Find the patch panel"
- c05-real_lookalike-c03 (two_image): eval/cases/public/commons/c03-Baie-de-brassage.jpg — step "Find the patch panel"
- c12-real_lookalike-c15 (two_image): eval/cases/public/commons/c15-Commercial-RJ45-wall-socket-internals.jpg — step "Check the network wall jack"
- c15-real_lookalike-c12 (two_image): eval/cases/public/commons/c12-Keystone-wall-plate.jpg — step "Check the jack's wiring"
- c22-real_lookalike-c31 (two_image): eval/cases/public/commons/c31-Brass-P-trap.jpg — step "Check the sink trap"
