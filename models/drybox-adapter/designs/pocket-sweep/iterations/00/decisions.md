# Round 00 — pocket-sweep

Search: nsga2, population 6, 2 generations, seed 3.
Generator `pocket`; evaluators `fit`.
Cold start.
Concept **pocket sweep** from `analysis.md` (2026-11-14). Targets: pocket_mm 8.85, pocket_band_mm [8.8, 8.9], cone_floor_deg 45.0.

## What changed, and why

First round through the loop. The analysis set the pocket target at 8.85 mm (8.7 mm pin + 0.15 mm printed undersize) and screened out topology optimization. One gene, P, in 8.6–9.1 mm. Who decided: the analysis (target, concept); the AI (a short sweep, since a coupon settles this).

## Result

1 design on the final front. Objectives are maximized. Renders: `picks.png`, `pareto.png`, `picks/<pick>/preview.png`.

| Pick | fit | Parameters |
|---|---|---|
| knee | -0.011 | pocket_mm=8.861 |

Mesh check of each pick:
- **knee**: 1651.1 mm³, watertight, one body, nothing over air

Calibrations in effect:
- none

What the evaluators do not know:
- **fit**: Printed holes run about 0.1–0.2 mm small. Test-fit a coupon; CAD does not settle it.

## AI review of the renders and the scores

The search converged on 8.861 mm, 0.011 mm from the 8.85 mm target, and the mesh is watertight with nothing over air. That is by construction: with one gene and a target from the analysis, the optimizer can only find the target. It confirms the loop, not the fit.

The scores cannot settle this part. The fit evaluator knows the pin (8.7 mm, one insert, calipered) and a 0.1–0.2 mm undersize band from one earlier print with no logged diameter. The 0.1 mm width of that band is as large as the whole difference between "too tight" and "rattles". Only a printed pocket measured on the real insert narrows it.

## Proposed next

1. Owner: approve three coupons at the analysis band, 8.80 / 8.85 / 8.90 mm (`gendesign generate` each with `-o`), and print them at 100% infill, no supports.
2. Bench: caliper each printed pocket and test the insert. Write `- calibrate: fit.undersize_mm = <drawn − printed>` in the coupon's test.md, run `gendesign feedback`, then `gendesign analyze`. The target moves by the measured undersize.
3. First check that the insert still does not go straight into the dryer wall hole. If it does, this part is not needed.

## Owner decision

Pending. Only the owner records this: `gendesign approve <this folder> <pick>`. Nothing is printed before that.
