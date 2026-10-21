# Perception eval — `--config combined` (C)

Ran 2026-10-21T13:17:22+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 0); DRY RUN. Code: main `ea0354d`, eval `e28400a`; faces checked: True.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 0 | — | — | 82.2 | 135.5 | 0 |
| real_wrong_place | bad | 2 | 0 | 0 | — | — | — | 66.7 | 67.2 | 0 |
| good_light | good | 2 | — | — | 0 | — | — | 139.1 | 173.3 | 0 |
| replay_reference | bad | 2 | 2 | 0 | — | — | — | 74.9 | 76.7 | 0 |
| good_reshot | good | 2 | — | — | 0 | — | — | 100.2 | 101.4 | 0 |
| overexposed | bad | 2 | 2 | 0 | — | — | — | 41.8 | 45.6 | 0 |
| no_change | bad | 2 | 2 | 0 | — | — | — | 85.9 | 86.1 | 0 |
| good_closeup | good | 2 | — | — | 0 | — | — | 61.3 | 66.8 | 0 |
| dark | bad | 2 | 2 | 0 | — | — | — | 19.7 | 20.0 | 0 |
| good_rotate | good | 2 | — | — | 0 | — | — | 124.5 | 158.3 | 0 |
| zone_cut | bad | 2 | 2 | 0 | — | — | — | 48.3 | 56.8 | 0 |
| wrong_place_mirror | bad | 2 | 0 | 0 | — | — | — | 76.9 | 89.6 | 0 |
| good_act_edit | good | 2 | — | — | 0 | — | — | 115.4 | 128.5 | 0 |
| glare | bad | 2 | 2 | 0 | — | — | — | 74.2 | 76.4 | 0 |
| touched_avoid | bad | 2 | 2 | 0 | — | — | — | 139.9 | 167.8 | 0 |
| good_view_light | good | 2 | — | — | 0 | — | — | 95.5 | 123.9 | 0 |
| blur_gaussian | bad | 2 | 2 | 0 | — | — | — | 30.7 | 37.9 | 0 |
| replay_exact | bad | 2 | 2 | 0 | — | — | — | 79.1 | 104.6 | 0 |
| blur_motion | bad | 2 | 2 | 0 | — | — | — | 83.2 | 84.7 | 0 |
| replay_earlier | bad | 2 | 2 | 0 | — | — | — | 54.9 | 88.4 | 0 |
| real_replay_annotated | bad | 1 | 0 | 0 | — | — | — | 109.1 | 109.1 | 0 |
| real_blur | bad | 2 | 1 | 0 | — | — | — | 58.3 | 86.2 | 0 |
| real_wrong_place_same_room | bad | 2 | 0 | 0 | — | — | — | 87.3 | 88.4 | 0 |
| real_lookalike | bad | 6 | 0 | 0 | — | — | — | 83.0 | 106.7 | 0 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 23 | 23 / 23 | 0 / 0 | 0 | {'llm_two_image': 14, 'llm_single': 17, 'opencv_block': 23} | 71.6 | 108.8 |
| split: calibration | 4 | 1 | 1 / 1 | 0 / 0 | 0 | {'llm_two_image': 3, 'opencv_block': 1} | 27.2 | 27.2 |
| split: test | 50 | 22 | 22 / 22 | 0 / 0 | 0 | {'llm_two_image': 11, 'llm_single': 17, 'opencv_block': 22} | 72.3 | 108.9 |
| source: onq | 3 | 0 | 0 / 0 | 0 / 0 | 0 | {'llm_two_image': 3} | — | — |
| source: commons | 47 | 22 | 22 / 22 | 0 / 0 | 0 | {'llm_single': 17, 'opencv_block': 22, 'llm_two_image': 8} | 72.3 | 108.9 |
| source: own-video | 4 | 1 | 1 / 1 | 0 / 0 | 0 | {'llm_two_image': 3, 'opencv_block': 1} | 27.2 | 27.2 |

## Dry run: 31 model calls would be made

- 04-real_same_place-05 (two_image): fixtures/onq-keystone-smoke/steps/02-seat-pairs.jpg — step "Snap the jack into the plate"
- 04-real_wrong_place-06 (two_image): fixtures/onq-keystone-smoke/redteam/R2-evidence-absent.jpg — step "Snap the jack into the plate"
- 06-real_wrong_place-05 (two_image): fixtures/onq-keystone-smoke/steps/02-seat-pairs.jpg — step "Seat the cable in the module"
- c03-good_light (single): eval/cases/c03-good_light.jpg — step "Find the patch panel"
- c05-good_reshot (single): eval/cases/c05-good_reshot.jpg — step "Find the patch panel"
- c07-good_closeup (single): eval/cases/c07-good_closeup.jpg — step "Find the patch panel"
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
- c22-real_same_place-c24 (single): eval/cases/public/commons/c24-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- c24-real_same_place-c22 (single): eval/cases/public/commons/c22-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- c27-real_same_place-c28 (single): eval/cases/public/commons/c28-247-Home-Rescue-tap-sink-plumbing-water.jpg — step "Run the tap"
- c09-real_same_place-c10 (two_image): eval/cases/public/commons/c10-Panduit-Pan-Net-Cable-Management-System.jpg — step "Find the patch panel"
- c22-real_replay_annotated-c23 (single): eval/cases/public/commons/c23-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- v0990-real_blur-v0900 (two_image): eval/cases/public/own-sink-video/f0900.jpg — step "Check the disposal's drain elbow"
- v0659-real_wrong_place_same_room-v1050 (two_image): eval/cases/public/own-sink-video/f1050.jpg — step "Check the sink trap"
- v0812-real_wrong_place_same_room-v0990 (two_image): eval/cases/public/own-sink-video/f0990.jpg — step "Check the supply valve"
- c03-real_lookalike-c05 (two_image): eval/cases/public/commons/c05-Patchpanel.jpg — step "Find the patch panel"
- c05-real_lookalike-c03 (two_image): eval/cases/public/commons/c03-Baie-de-brassage.jpg — step "Find the patch panel"
- c12-real_lookalike-c15 (two_image): eval/cases/public/commons/c15-Commercial-RJ45-wall-socket-internals.jpg — step "Check the network wall jack"
- c15-real_lookalike-c12 (two_image): eval/cases/public/commons/c12-Keystone-wall-plate.jpg — step "Check the jack's wiring"
- c22-real_lookalike-c31 (two_image): eval/cases/public/commons/c31-Brass-P-trap.jpg — step "Check the sink trap"
- c31-real_lookalike-c24 (two_image): eval/cases/public/commons/c24-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
