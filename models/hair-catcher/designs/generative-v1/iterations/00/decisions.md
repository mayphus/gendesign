# Round 00

## What changed

First generative round. The grate is no longer a hand-placed 7-hole pattern. Seeds sit on a warped phyllotaxis spiral (a radial density field plus a 3-fold harmonic). Each Voronoi cell is inset by the local strut width. The solid is a 47° cone inside the existing collar and flange, so the print has the flange on the bed and no internal floor. NSGA-II (population 10, 3 generations, 40 evaluations, seed 7) scored drainage, capture, fingertip stiffness, and volume.

## Why

The owner asked for AI + generative design, and for this first round to stay short. The starting objectives come from `requirements.yaml` and from the Voronoi A print: cells near 1 mm held a water film, so flow credit starts at the capillary length of water (2.7 mm) and is full at 4 mm. Who decided: the AI, from those requirements, before any render of this cone existed. The code only searched.

## Result

All 40 evaluations were feasible. The knee did not move: generations 0 through 3 logged the same knee (ball 7.0 mm, flow 93 cm³/s). Hypervolume went from 0.58 to 0.60. Four watertight picks:

| Pick | Open | Max ball | Min ball | Flow at 5 mm head | Film area | Fingertip at 10 N | Volume | Insert |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smooth v2 (reference, same orifice model) | 50.5% | 8.6 mm | 8.6 mm | 78 cm³/s | 0 | 0.04 mm | 4304 mm³ published | 10.2 mm |
| open-drain | 66.5% | 7.9 mm | 4.8 mm | 102 cm³/s | 0 | 0.36 mm | 3558 mm³ | 17.4 mm |
| knee | 60.6% | 7.0 mm | 4.3 mm | 93 cm³/s | 0 | 0.11 mm | 3794 mm³ | 17.9 mm |
| stiff | 48.3% | 8.1 mm | 3.1 mm | 69 cm³/s | 0 | 0.07 mm | 4020 mm³ | 17.9 mm |
| hair-snag | 47.8% | 6.2 mm | 0.24 mm | 67 cm³/s | 12.6 mm² | 0.08 mm | 4029 mm³ | 17.9 mm |

Flow is `Cd A sqrt(2gh)` with Cd = 0.61 and a 5 mm head. It ranks openings. It is not a measured drain rate. v2's deflection is the flat web of the 7-hole plan, not the dished shell, so the real bowl is at least that stiff. Volumes are not the same solid: v2 is the published CadQuery bowl; the cones include a deep skirt. Nothing was printed.

## AI review of the renders and the scores

The four 3/4 renders are the same cup. The 47° cone is about 18 mm deep, so the side view hides the grate. The top views are where the designs differ, and they differ less than the table suggests: irregular polygons, no obvious fine center or fine rim. open-drain is eight large cells. hair-snag is a denser web. stiff is thicker struts and a small cell in the middle. knee sits between open-drain and hair-snag.

The picture of hair-snag looks acceptable. The score does not. Its smallest opening is 0.24 mm and 12.6 mm² of open area is under the film cutoff. Capture only rewards a smaller *largest* ball, so those slivers do not help capture and they are the Voronoi A failure again. The search had no reason to delete them.

Stiffness is not earning its place as an objective. Every pick deflects 0.07–0.36 mm under 10 N. The limit is 1.5 mm. The stiff pick gives up about 33 cm³/s of flow, against open-drain, to buy a deflection that was already fine.

The density field did not place the big cell. hair-snag's largest opening is still 6.2 mm, sitting next to a crack. And three generations did not move the knee, so a longer run of this same spiral would mostly repeat these layouts.

## Proposed for the next round

1. Repair openings under 2.7 mm out of the solid before scoring, and reject a pick that still has film area. That is the Voronoi A lesson, and this round violated it on the capture pick.
2. Make fingertip deflection a constraint (keep it under about 0.5 mm) instead of a fourth objective. Search drainage, capture, and volume.
3. Drive cell size with an explicit radial grade, and penalize a large gap between the biggest cell and the median, so one stray opening cannot set capture. Keep the next search short until that repair is in. Show top views on the contact sheet; the 3/4 view cannot show this tradeoff.
