# Round 01 — pebble-plate

Search: nsga2, population 16, 6 generations, seed 11.
Generator `pebble-plate`; evaluators `drainage`, `capture`, `structure`, `print-rules`.
Seeded from models/hair-catcher/designs/pebble-plate/iterations/00.
Concept **flat plate** from `analysis.md` (2026-11-14). Targets: open_area_min_mm2 408, open_fraction_min 0.508, hole_min_mm 4.0, hole_max_mm 12.0, plate_t_min_mm 1.94, rib_min_mm 1.5, rim_min_mm 1.35.

## What changed, and why

Round 00 ran before the analysis stage existed: it searched a drawn form (pebble-e) and only ranked flow. The owner asked for mechanical design order: requirements, then analysis, then the algorithm and the AI decide the form. `gendesign analyze` now derives the targets first (analysis.md): 408 mm² open area from the orifice equation for v2-level flow, a 4.0 mm hole floor from the capillary length, a 1.94 mm plate minimum from the 30 N hard push. It screened flat plate, cone and two-level and chose the flat plate, because drainage binds and structure has 1.29x margin. This round makes the flow target a constraint and adds the plate stress and deflection check. It continues from the round 00 picks. Who decided: the owner (order of work), the analysis (concept and targets), the AI (seeding from round 00).

## Result

9 designs on the final front. Objectives are maximized. Renders: `picks.png`, `pareto.png`, `picks/<pick>/preview.png`.

| Pick | drainage_cm3_s | capture_mm | Parameters |
|---|---|---|---|
| knee | 80.98 | 5.48 | seed=216, spacing=7.304, grade=0.005, rib=1.922, edge_rib=1.533, round_frac=0.502, plate_t=2.2, min_inscribed=3.5 |
| best-drainage | 82.62 | 4.765 | seed=216, spacing=7.304, grade=0.001, rib=1.959, edge_rib=1.533, round_frac=0.502, plate_t=2.2, min_inscribed=3.5 |
| best-capture | 80.16 | 5.77 | seed=217, spacing=7.513, grade=0.001, rib=2.043, edge_rib=1.427, round_frac=0.502, plate_t=2.2, min_inscribed=3.5 |

Mesh check of each pick:
- **knee**: 3325.7 mm³, watertight, one body, nothing over air
- **best-drainage**: 3309.1 mm³, watertight, one body, nothing over air
- **best-capture**: 3335.4 mm³, watertight, one body, nothing over air

Calibrations in effect:
- none

What the evaluators do not know:
- **drainage**: Orifice model, Cd 0.61, 5.0 mm head. Ranks designs; not a timed drain.
- **capture**: Largest inscribed circle stands in for hair capture. No hair test yet.
- **structure**: Closed-form clamped plate, D scaled by solid fraction². Not FEA; ranks and screens.
- **stiffness**: Flat 2.2 mm plate; fingertip stiffness is not modeled in this round.

## AI review of the renders and the scores

Every pick meets the analysis targets: open area 420–432 mm² against 408, holes 5.2–6.9 mm against the 4.0 mm floor, plate stress 16.0–16.5 MPa against 20, fingertip 0.09–0.10 mm against 0.5. All three meshes are watertight, one body, nothing over air.

| | Holes | Ball range | Open area | Flow | Hard push | Fingertip |
|---|---:|---:|---:|---:|---:|---:|
| round 00 knee | 11 | 5.21–6.11 mm | 412 mm² | 78.9 cm³/s | — | — |
| knee | 11 | 5.15–6.32 mm | 424 mm² | 81.0 cm³/s | 16.2 MPa | 0.095 mm |
| best-drainage | 10 | 5.61–6.91 mm | 432 mm² | 82.6 cm³/s | 16.5 MPa | 0.100 mm |
| best-capture | 11 | 5.31–6.11 mm | 420 mm² | 80.2 cm³/s | 16.0 MPa | 0.093 mm |

The analysis predicted a flat plate would meet the flow target with holes near 5.3 mm. The front sits at 5.2–6.9 mm, so the hexagonal estimate was close. The flow constraint did its job: only 2 of 16 starting designs were feasible, and the whole population was by generation 4. round 00's knee (412 mm²) would only just pass.

What the renders show that the scores do not:

1. **The holes are still rounded polygons.** round_frac is at its 0.50 lower bound on every pick. Nothing in the scores rewards a rounder hole, and drainage rewards area. This is the same gap as round 00, and the analysis does not close it: corner radius is a hair-snag and corner-water question, and `gendesign.corners` already measures both.
2. **Exploration narrowed.** Seeding from round 00 kept two layouts (seeds 216 and 217). The picks are refinements of one pattern, not alternatives. That is right for refinement and wrong for a first look at a constrained space.
3. **Structure is now the second constraint.** At 53% open, hard-push stress is 16 MPa, 0.8 of the 20 MPa allowable, and that allowable is a guess. More open area will run into it before it runs into the deflection limit.

The knee is the candidate. Flow is 4% above the target, capture is close to round 00, and it has structural margin. I would not print it until the corner gap is scored and a 30 N press test confirms the allowable.

## Proposed next

1. Add the corner evaluator (`gendesign.corners`: hair snag and corner water) as a third objective, so rounding competes with drainage instead of sitting at its bound.
2. Run the next round cold (no `--from`) with the analysis constraints, to check that 216/217 is not a local pick.
3. Owner: a measured tap flow rate and the largest acceptable hole would replace the two assumed targets in `analysis.md`.
4. Bench: a 30 N press on a printed coupon calibrates `structure.allowable` via `- calibrate:` in its test.md.

## Owner decision

Pending. Only the owner records this: `gendesign approve <this folder> <pick>`. Nothing is printed before that.
