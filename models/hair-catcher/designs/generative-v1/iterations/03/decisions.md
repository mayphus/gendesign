# Round 03

## What changed, and why

The owner said the round 02 knee looks angular, and then corrected the process: do not add smoothness as an objective. If a round junction is actually better, the functional scores have to say so. If they do not, the models are too crude.

The layout stays the round 02 knee. Three shape parameters are free and are not in the score: strut width, junction blend (how much the notch between struts is filled), and profile (square section versus a round capsule). The search was population 12, 4 generations, 60 evaluations.

The beam grillage is not the structural score here. A plane-stress solve on the raster of the grate holds the rim and pulls a patch at the center, in x and in y. The score is the 95th percentile von Mises stress in the web, away from the loaded patch. A re-entrant corner raises that peak. This is a membrane proxy for the push, not an out-of-plane plate, and it is not a safety check.

Hair release is the sum, over tight corners, of how far the measured radius sits below 0.5 mm. Water retention is an area assigned to opening wedges tighter than 0.7 mm. Both radii are measured on the boundary. The blend parameter is not an input to either one. Net drainage is the orifice flow after that retained area is taken out of the open area. Capture is still the ball-limit margin. Constraints stay: openings at least 4.0 mm, strut at least 1.5 mm, no film cell.

## Did rounding emerge?

Yes, on the scores, and only partly in the picture.

Across the 60 feasible evaluations, junction blend correlates with:

| Score | Correlation with blend |
|---|---:|
| Stress relief (lower peak is better) | +0.74 |
| Hair release (less snag is better) | +0.71 |
| Capture (smaller largest opening) | +0.55 |
| Net drainage | −0.65 |

Stress and hair release push the blend up. Drainage pushes it down, because a filled notch is material that is not an opening. Capture moves with blend too: the largest hole gets smaller, which this objective treats as better capture. Profile (square versus round section) only correlates +0.21 with stress relief. The front's mean blend is 0.97 mm. The knee went to 2.14 mm, at the top of the range, with profile 0.54.

The sharp end of the same layout (blend 0.19, square profile) is the open-drain pick: more flow (85 vs 74 cm³/s), higher stress (3.1 vs 1.8 MPa), and a higher snag score.

| Pick | Blend | Profile | Max ball | Smallest | Net flow | Snag | Retained | Stress p95 | Strut |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| smooth v2 | — | round holes | 8.6 mm | 8.6 mm | 78 cm³/s | — | — | — | 1.8 mm |
| round 02 knee | 0.5 mm plan fillet | polygon | 7.1 mm | 4.5 mm | 92 cm³/s | — | — | beam, not this model | 1.57 mm |
| open-drain (sharp end) | 0.19 | 0.00 | 7.0 mm | 4.7 mm | 85 cm³/s | 221 | 44 mm² | 3.1 MPa | 1.56 mm |
| knee | 2.14 | 0.54 | 6.8 mm | 4.3 mm | 74 cm³/s | 191 | 36 mm² | 1.8 MPa | 1.56 mm |

The knee mesh is watertight. About 26 mm² of the print mesh sits just past a 45° overhang, the same facet band as the round 02 cone. Nothing was printed.

## What the renders show

The top view of the knee is rounder at the holes than the sharp open-drain pick. The 3/4 view and the junction close-up are not. The struts are still a cone slab: flat sides, a square lip, facets where the wall meets the cone. The models that moved the blend only see the plan. They cannot see the vertical edge a finger or a hair meets in that close-up, so they had no reason to round it. v2 looks organic because the lip itself is filleted in 3D. This search did not have that shape in a way the scores can feel.

The low-stress candidate (blend 2.19) dropped a cell to 3.8 mm on the fine raster, under the 4.0 mm floor. The coarse search grid let it through. It is not a pick.

## Proposed next

1. Score the lip, not only the plan. A bending stress, or a fiber at the vertical edge, is what would have a reason to round the face in the close-up. The plane-stress model will keep spending blend on the notch and leaving the lip square.
2. Keep drainage in the front. It is the objective that refuses an arbitrarily large blend. The knee is already at the top of the blend range, and flow is down to 74 cm³/s from 92 on the round 02 knee.
3. Judge the 4 mm floor on the export grid. The low-stress point passed the search and failed the fine raster.
