# Perception eval — `--config llm2` (A')

Ran 2026-10-21T12:25:07+00:00 on 54 cases (split: all); OpenCV 5.0.0; model calls made: 0 (cap 0); DRY RUN. Code: main `43c1520`, eval `43c1520`; faces checked: —.

| class | kind | n | caught | missed | false blocks | routed to 2-photo | decision = expected | p50 ms | p95 ms | model calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| real_same_place | good | 5 | — | — | 0 | — | — | — | — | 0 |
| real_wrong_place | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| good_light | good | 2 | — | — | 0 | — | — | — | — | 0 |
| replay_reference | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| good_reshot | good | 2 | — | — | 0 | — | — | — | — | 0 |
| overexposed | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| no_change | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| good_closeup | good | 2 | — | — | 0 | — | — | — | — | 0 |
| dark | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| good_rotate | good | 2 | — | — | 0 | — | — | — | — | 0 |
| zone_cut | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| wrong_place_mirror | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| good_act_edit | good | 2 | — | — | 0 | — | — | — | — | 0 |
| glare | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| touched_avoid | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| good_view_light | good | 2 | — | — | 0 | — | — | — | — | 0 |
| blur_gaussian | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| replay_exact | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| blur_motion | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| replay_earlier | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| real_replay_annotated | bad | 1 | 0 | 0 | — | — | — | — | — | 0 |
| real_blur | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| real_wrong_place_same_room | bad | 2 | 0 | 0 | — | — | — | — | — | 0 |
| real_lookalike | bad | 6 | 0 | 0 | — | — | — | — | — | 0 |

| slice | n | ran | caught / bad | false blocks / good | routed to 2-photo | routes | e2e p50 ms | e2e p95 ms |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| all | 54 | 0 | 0 / 0 | 0 / 0 | 0 | — | — | — |
| split: calibration | 4 | 0 | 0 / 0 | 0 / 0 | 0 | — | — | — |
| split: test | 50 | 0 | 0 / 0 | 0 / 0 | 0 | — | — | — |
| source: onq | 3 | 0 | 0 / 0 | 0 / 0 | 0 | — | — | — |
| source: commons | 47 | 0 | 0 / 0 | 0 / 0 | 0 | — | — | — |
| source: own-video | 4 | 0 | 0 / 0 | 0 / 0 | 0 | — | — | — |

## Dry run: 54 model calls would be made

- 04-real_same_place-05 (two_image): fixtures/onq-keystone-smoke/steps/02-seat-pairs.jpg — step "Snap the jack into the plate"
- 04-real_wrong_place-06 (two_image): fixtures/onq-keystone-smoke/redteam/R2-evidence-absent.jpg — step "Snap the jack into the plate"
- 06-real_wrong_place-05 (two_image): fixtures/onq-keystone-smoke/steps/02-seat-pairs.jpg — step "Seat the cable in the module"
- c03-good_light (two_image): eval/cases/c03-good_light.jpg — step "Find the patch panel"
- c03-replay_reference (two_image): eval/cases/c03-replay_reference.jpg — step "Find the patch panel"
- c05-good_reshot (two_image): eval/cases/c05-good_reshot.jpg — step "Find the patch panel"
- c05-overexposed (two_image): eval/cases/c05-overexposed.jpg — step "Find the patch panel"
- c05-no_change (two_image): eval/cases/c05-no_change.jpg — step "Find the patch panel"
- c07-good_closeup (two_image): eval/cases/c07-good_closeup.jpg — step "Find the patch panel"
- c07-dark (two_image): eval/cases/c07-dark.jpg — step "Find the patch panel"
- c08-good_rotate (two_image): eval/cases/c08-good_rotate.jpg — step "Find the patch panel"
- c08-good_closeup (two_image): eval/cases/c08-good_closeup.jpg — step "Find the patch panel"
- c08-zone_cut (two_image): eval/cases/c08-zone_cut.jpg — step "Find the patch panel"
- c08-wrong_place_mirror (two_image): eval/cases/c08-wrong_place_mirror.jpg — step "Find the patch panel"
- c09-good_act_edit (two_image): eval/cases/c09-good_act_edit.jpg — step "Find the patch panel"
- c09-overexposed (two_image): eval/cases/c09-overexposed.jpg — step "Find the patch panel"
- c09-glare (two_image): eval/cases/c09-glare.jpg — step "Find the patch panel"
- c09-touched_avoid (two_image): eval/cases/c09-touched_avoid.jpg — step "Find the patch panel"
- c10-touched_avoid (two_image): eval/cases/c10-touched_avoid.jpg — step "Find the patch panel"
- c12-good_rotate (two_image): eval/cases/c12-good_rotate.jpg — step "Check the network wall jack"
- c12-good_reshot (two_image): eval/cases/c12-good_reshot.jpg — step "Check the network wall jack"
- c12-good_act_edit (two_image): eval/cases/c12-good_act_edit.jpg — step "Check the network wall jack"
- c15-good_view_light (two_image): eval/cases/c15-good_view_light.jpg — step "Check the jack's wiring"
- c21-blur_gaussian (two_image): eval/cases/c21-blur_gaussian.jpg — step "Open the junction box"
- c22-replay_exact (two_image): eval/cases/public/commons/c22-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- c23-good_light (two_image): eval/cases/c23-good_light.jpg — step "Check the sink trap"
- c23-no_change (two_image): eval/cases/c23-no_change.jpg — step "Check the sink trap"
- c24-blur_gaussian (two_image): eval/cases/c24-blur_gaussian.jpg — step "Check the sink trap"
- c24-blur_motion (two_image): eval/cases/c24-blur_motion.jpg — step "Check the sink trap"
- c24-glare (two_image): eval/cases/c24-glare.jpg — step "Check the sink trap"
- c24-replay_reference (two_image): eval/cases/c24-replay_reference.jpg — step "Check the sink trap"
- c27-good_view_light (two_image): eval/cases/c27-good_view_light.jpg — step "Run the tap"
- c27-replay_exact (two_image): eval/cases/public/commons/c27-247-Home-Rescue-sink-tap-plumbing-water.jpg — step "Run the tap"
- c30-dark (two_image): eval/cases/c30-dark.jpg — step "Check the sink trap"
- c30-replay_earlier (two_image): eval/cases/c30-replay_earlier.jpg — step "Check the sink trap"
- c31-blur_motion (two_image): eval/cases/c31-blur_motion.jpg — step "Check the sink trap"
- c38-wrong_place_mirror (two_image): eval/cases/c38-wrong_place_mirror.jpg — step "Check the downspout outlet"
- c39-zone_cut (two_image): eval/cases/c39-zone_cut.jpg — step "Check the downspout outlet"
- c39-replay_earlier (two_image): eval/cases/c39-replay_earlier.jpg — step "Check the downspout outlet"
- c22-real_same_place-c24 (two_image): eval/cases/public/commons/c24-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- c24-real_same_place-c22 (two_image): eval/cases/public/commons/c22-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- c27-real_same_place-c28 (two_image): eval/cases/public/commons/c28-247-Home-Rescue-tap-sink-plumbing-water.jpg — step "Run the tap"
- c09-real_same_place-c10 (two_image): eval/cases/public/commons/c10-Panduit-Pan-Net-Cable-Management-System.jpg — step "Find the patch panel"
- c22-real_replay_annotated-c23 (two_image): eval/cases/public/commons/c23-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
- v0990-real_blur-v0900 (two_image): eval/cases/public/own-sink-video/f0900.jpg — step "Check the disposal's drain elbow"
- v1106-real_blur-v0870 (two_image): eval/cases/public/own-sink-video/f0870.jpg — step "Check the disposal's drain elbow"
- v0659-real_wrong_place_same_room-v1050 (two_image): eval/cases/public/own-sink-video/f1050.jpg — step "Check the sink trap"
- v0812-real_wrong_place_same_room-v0990 (two_image): eval/cases/public/own-sink-video/f0990.jpg — step "Check the supply valve"
- c03-real_lookalike-c05 (two_image): eval/cases/public/commons/c05-Patchpanel.jpg — step "Find the patch panel"
- c05-real_lookalike-c03 (two_image): eval/cases/public/commons/c03-Baie-de-brassage.jpg — step "Find the patch panel"
- c12-real_lookalike-c15 (two_image): eval/cases/public/commons/c15-Commercial-RJ45-wall-socket-internals.jpg — step "Check the network wall jack"
- c15-real_lookalike-c12 (two_image): eval/cases/public/commons/c12-Keystone-wall-plate.jpg — step "Check the jack's wiring"
- c22-real_lookalike-c31 (two_image): eval/cases/public/commons/c31-Brass-P-trap.jpg — step "Check the sink trap"
- c31-real_lookalike-c24 (two_image): eval/cases/public/commons/c24-HK-public-toilet-bathing-hand-sink-drain.jpg — step "Check the sink trap"
