# Round 02 — pebble-plate

Search: nsga2, population 24, 8 generations, seed 23.
Generator `pebble-plate`; evaluators `drainage`, `capture`, `structure`, `corners`, `print-rules`.
Cold start.
Concept **flat plate** from `analysis.md` (2026-11-14). Targets: open_area_min_mm2 408, open_fraction_min 0.508, hole_min_mm 4.0, hole_max_mm 12.0, plate_t_min_mm 1.94, rib_min_mm 1.5, rim_min_mm 1.35.

## What changed, and why

Round 01's review asked two things. (1) Is the polygonal hole a scoring gap? Checked with gendesign.corners on the round 01 knee: the tightest hole corner is 1.29 mm at round_frac 0.50 and 2.06 mm at 0.80, both rounder than the 0.5 mm hook and 0.7 mm meniscus radii, so hair snag and corner water are zero either way. Rounding to 0.95 only drops open area to 334 mm², under the 408 mm² target. So rounding is not a missing score; corners are now an explicit constraint in every round. (2) Is seed 216/217 a local pick? This round runs cold (no --from) with a larger population (24 x 8) to check. Who decided: the owner said go on the catcher; the AI chose the round from round 01's proposals.

## Result

4 designs on the final front. Objectives are maximized. Renders: `picks.png`, `pareto.png`, `picks/<pick>/preview.png`.

| Pick | drainage_cm3_s | capture_mm | Parameters |
|---|---|---|---|
| knee | 84.66 | 1.69 | seed=178, spacing=8.315, grade=0.033, rib=2.08, edge_rib=1.517, round_frac=0.616, plate_t=2.2, min_inscribed=3.5 |
| best-drainage | 85.08 | 1.678 | seed=178, spacing=8.297, grade=0.033, rib=2.08, edge_rib=1.517, round_frac=0.596, plate_t=2.2, min_inscribed=3.5 |
| best-capture | 79.49 | 4.652 | seed=397, spacing=7.885, grade=0.076, rib=1.995, edge_rib=1.603, round_frac=0.596, plate_t=2.2, min_inscribed=3.5 |

Mesh check of each pick:
- **knee**: 3291.6 mm³, watertight, one body, nothing over air
- **best-drainage**: 3286.6 mm³, watertight, one body, nothing over air
- **best-capture**: 3346.6 mm³, watertight, one body, nothing over air

Calibrations in effect:
- none

What the evaluators do not know:
- **drainage**: Orifice model, Cd 0.61, 5.0 mm head. Ranks designs; not a timed drain.
- **capture**: Largest inscribed circle stands in for hair capture. No hair test yet.
- **structure**: Closed-form clamped plate, D scaled by solid fraction². Not FEA; ranks and screens.
- **corners**: Hook 0.5 mm and meniscus 0.7 mm radii are proxies, not a hair or water test.
- **stiffness**: Flat 2.2 mm plate; fingertip stiffness is not modeled in this round.

## AI review of the renders and the scores

Both questions from round 01 have an answer.

**Corners: settled by function.** Every pick passes the new corners constraint with zero hair snag and zero corner water; the tightest corner is 1.49–2.12 mm. The search moved round_frac to 0.60–0.62 here without being asked, because the corner score is a constraint, not a reward. Rounding is no longer an open gap.

**Is round 01's layout a local pick? No, it is the better one.** A cold search twice as large (24 × 8, 192 evaluations) found a sparse front: 4 designs, and none feasible in the first two generations. The flow target leaves a narrow feasible region and the integer layout seed makes it rugged. Across rounds 01 and 02 (same targets), the combined front is:

| Source | Holes | Ball range | Open area | Flow | Capture | Hard push |
|---|---:|---:|---:|---:|---:|---:|
| round 01 best-capture (seed 217) | 11 | 5.31–6.11 mm | 420 mm² | 80.2 cm³/s | 5.77 | 16.0 MPa |
| **round 01 knee (seed 216)** | 11 | 5.15–6.32 mm | 424 mm² | 81.0 cm³/s | 5.48 | 16.2 MPa |
| round 02 knee (seed 178) | 8 | 6.88–9.33 mm | 443 mm² | 84.7 cm³/s | 1.69 | 17.0 MPa |
| round 02 best-capture (seed 397) | 10 | 5.01–6.98 mm | 416 mm² | 79.5 cm³/s | 4.65 | 15.8 MPa |

Round 02's best-capture is dominated by round 01's knee on both objectives. Round 02's knee is a different product: 4.6% more flow for holes as big as smooth v2's 8.6 mm ball. With a 4-point front, the "knee" rule picked an end of a gap, not a balance. That is a limit of knee selection on a sparse front, not a recommendation.

**The candidate stays round 01's knee**: 11 holes, 5.2–6.3 mm, 81 cm³/s (4% over target), 16.2 of 20 MPa, corners 1.29 mm (rounder than both proxy radii), watertight, nothing over air.

## Proposed next

1. Owner: the round 01 knee is ready for your decision. If you want it printed, run `gendesign approve models/hair-catcher/designs/pebble-plate/iterations/01 knee`, then `gendesign generate` it. The AI will not approve.
2. Before or with that print: caliper the flange seat (Ø46 is assumed), and if you can, give the tap flow rate and the largest hole you would accept. Those two replace the assumed targets in `analysis.md`.
3. After the print: time a litre through it and press it at 30 N. Write both as `calibrate:` lines (`drainage.cd`, `structure.allowable_MPa`) in its test.md.
4. Search: treat the layout seed as a discrete choice (multi-start over seeds, continuous genes per seed) so a cold round does not depend on luck. Only worth it if the owner wants another round before printing.

## Owner decision

Pending. Only the owner records this: `gendesign approve <this folder> <pick>`. Nothing is printed before that.
