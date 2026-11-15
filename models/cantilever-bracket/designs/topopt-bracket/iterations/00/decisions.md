# Round 00 — topopt-bracket

Search: nsga2, population 4, 2 generations, seed 1.
Generator `topopt-bracket`; evaluators `stiffness-mass`, `print-support`.
Cold start.
Concept **2-D SIMP topology** from `analysis.md` (2026-11-15). Targets: tip_load_N 50.0, volfrac_max 0.4, min_feature_mm 2.0, domain_mm [120.0, 40.0, 5.0].

## What changed, and why

first topopt round: trade volume vs stiffness

## Result

4 designs on the final front. Objectives are maximized. Renders: `picks.png`, `pareto.png`, `picks/<pick>/preview.png`.

| Pick | stiffness | lightness | Parameters |
|---|---|---|---|
| knee | -673.2 | -0.2832 | volfrac=0.2832, rmin_mm=2.935, load_y_frac=0.6303, nelx=30, nely=10, niter=20, rmin_elem=1.2, compliance=673.174013, volume=0.2832, overhang_frac=0.617, print_flat=True, L_mm=120.0, H_mm=40.0, thickness_mm=5.0 |
| best-stiffness | -298.1 | -0.3991 | volfrac=0.3991, rmin_mm=3.12, load_y_frac=0.6303, nelx=30, nely=10, niter=20, rmin_elem=1.2, compliance=298.071405, volume=0.3991, overhang_frac=0.2907, print_flat=True, L_mm=120.0, H_mm=40.0, thickness_mm=5.0 |
| best-lightness | -1285 | -0.2256 | volfrac=0.2256, rmin_mm=4.271, load_y_frac=0.3538, nelx=30, nely=10, niter=20, rmin_elem=1.2, compliance=1285.475719, volume=0.2256, overhang_frac=0.7692, print_flat=True, L_mm=120.0, H_mm=40.0, thickness_mm=5.0 |

Mesh check of each pick:
- **knee**: 3473.0102398428767 mm³, watertight, one body, nothing over air
- **best-stiffness**: 7643.928204292909 mm³, watertight, one body, nothing over air
- **best-lightness**: 1696.5605975421615 mm³, watertight, one body, nothing over air

Calibrations in effect:
- none

What the evaluators do not know:
- **stiffness-mass**: Compliance from unit-E SIMP FEA; ranks layouts, not physical tip deflection. Yield is not checked.
- **print-support**: Flat print: in-plane overhang not binding. Edge-on would use the AM filter.

## AI review of the renders and the scores

_AI: pending._

## Proposed next

_AI: pending._

## Owner decision

Pending. Only the owner records this: `gendesign approve <this folder> <pick>`. Nothing is printed before that.
