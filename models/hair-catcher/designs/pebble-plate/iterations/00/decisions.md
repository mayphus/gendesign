# Round 00 — pebble-plate

Search: nsga2, population 16, 6 generations, seed 7.
Generator `pebble-plate`; evaluators `drainage`, `capture`, `print-rules`.
Seeded from models/hair-catcher/designs/pebble-e/design.json.

## What changed, and why

> Run before `gendesign analyze` existed: this round searched a drawn form and only ranked it. Round 01 is the first analysis-driven round.

First round through the shared runner. Start from pebble-e, the flat plate that prints with nothing over air. The generator searches seed, spacing, grade, rib, edge rib and corner rounding. Objectives are drainage (film-discounted orifice flow) and capture (ball margin minus half the max-median gap). Print rules from requirements.yaml are constraints, so edge_rib starts at the 1.35 mm rim floor instead of E's 1.2. Who decided: the AI, from the owner's ask to make gendesign the AI + generative design loop.

## Result

12 designs on the final front. Objectives are maximized. Renders: `picks.png`, `pareto.png`, `picks/<pick>/preview.png`.

| Pick | drainage_cm3_s | capture_mm | Parameters |
|---|---|---|---|
| knee | 78.87 | 5.745 | seed=217, spacing=7.304, grade=0.001, rib=2.037, edge_rib=1.533, round_frac=0.502, plate_t=2.2, min_inscribed=3.5 |
| best-drainage | 81.23 | 4.81 | seed=216, spacing=7.304, grade=0.001, rib=2.038, edge_rib=1.533, round_frac=0.502, plate_t=2.2, min_inscribed=3.5 |
| best-capture | 63.87 | 6.265 | seed=282, spacing=7.274, grade=0.144, rib=2.229, edge_rib=1.58, round_frac=0.647, plate_t=2.2, min_inscribed=3.5 |

Mesh check of each pick (re-exported after the mesher fix in gendesign/field.py):
- **knee**: 3350.7 mm³, watertight, one body, nothing over air
- **best-drainage**: 3325.6 mm³, watertight, one body, nothing over air
- **best-capture**: 3521.6 mm³, watertight, one body, nothing over air

Calibrations in effect:
- none

What the evaluators do not know:
- **drainage**: Orifice model, Cd 0.61, 5.0 mm head. Ranks designs; not a timed drain.
- **capture**: Largest inscribed circle stands in for hair capture. No hair test yet.
- **stiffness**: Flat 2.2 mm plate; fingertip stiffness is not modeled in this round.

## AI review of the renders and the scores

Same orifice model for every row (Cd 0.61, 5 mm head). pebble-e is scored here with the round's evaluators; it fails only the 1.35 mm rim floor (its edge rib is 1.2 mm).

| | Holes | Ball range | Open | Flow | Capture |
|---|---:|---:|---:|---:|---:|
| pebble-e (start) | 15 | 4.53–5.70 mm | 45.5% | 70.0 cm³/s | 5.95 |
| knee | 11 | 5.21–6.11 mm | 51.3% | 78.9 cm³/s | 5.74 |
| best-drainage | 10 | 5.57–6.86 mm | 52.9% | 81.2 cm³/s | 4.81 |
| best-capture | 15 | 4.17–5.36 mm | 41.6% | 63.9 cm³/s | 6.26 |

The search did what the scores asked. The knee drains 13% more than pebble-e for a 0.4 mm larger worst hole, and it matches smooth v2's 78 cm³/s with a 6.1 mm ball instead of 8.6 mm. All three picks are flat plates with nothing printed over air, so printability did not trade against anything here.

What the pictures show that the scores do not:

1. **The holes got squarer.** round_frac sits at its lower bound (0.50) on the knee and best-drainage. A less rounded hole has more area, so drainage pulls it there and nothing pulls back. Next to pebble-e the knee reads as rounded polygons, not pebbles. This is the round 03 lesson again: if a round hole is better, a functional score has to say so. `gendesign.corners` already measures hair snag and corner water on the boundary; it is not in this model yet.
2. **Grade collapsed.** The front's grade runs 0.00–0.16, and the knee is at 0.00: even cells. Capture rewards a small worst hole and penalizes max-median spread, which an even pattern wins. That is consistent, not a bug. A graded "fine at the rim" catcher would need a capture score that weights where hair lands.
3. **seed is doing too much.** The knee (seed 217) and best-drainage (216) share every other gene to three decimals. Changing the seed by one gives a different layout, so NSGA-II is mostly sampling patterns through that gene. Six seeds survive on the front.
4. Stiffness is not scored. Every rib is at least 2.04 mm on a 2.2 mm plate, wider than the 1.8 mm v2 struts, but a 10 N fingertip check is still owed before a print.

The knee is the candidate I would take forward. I would not print it from this round: the squarer holes are a scoring gap, not a choice anyone made.

## Proposed next

1. Add a corner evaluator (hair snag and corner water from `gendesign.corners`) as a third objective, so rounding has to earn its place against drainage.
2. Hold the layout seed: continue from this round (`--from iterations/00`) with seed fixed per family, and let the continuous genes refine.
3. Owner: say whether a 6.1 mm worst hole is acceptable, or whether capture should stay near pebble-e's 5.7 mm.

## Owner decision

Pending. Only the owner records this: `gendesign approve <this folder> <pick>`. Nothing is printed before that.
