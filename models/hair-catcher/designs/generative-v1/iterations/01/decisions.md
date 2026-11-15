# Round 01

## What changed

The owner reviewed the round 00 top sheet. The knee was the one to keep. The problems were uneven cells (one large rim opening set capture while the center was dense) and jagged strut corners. All three proposals from that review went in, plus two from the owner:

1. Openings whose inscribed circle is under 2.7 mm are filled before scoring. A pick with more than a speck of film area is rejected.
2. Fingertip deflection is a constraint, at or under 0.5 mm at 10 N. The objectives are drainage, capture, and volume.
3. Seed spacing is an explicit radial grade (density-weighted Lloyd on the exponent), and capture is penalized by half the gap between the largest cell and the median cell.
4. Exported struts get a 0.5 mm round fillet in plan, the same idea as the v2 hole lips. The fillet stays on the cone. It does not add a flat ledge.
5. The search grew to population 24 and 8 generations (216 evaluations).

Who decided: the owner, from the round 00 top views, accepting the previous AI proposals and adding the fillet and the larger run. The code searched. This note is the AI review of the new renders and scores.

## Result

216 evaluations, 24 feasible on the final front. Hypervolume on flow and capture moved from 0.61 to 0.64. Three watertight picks are distinct. A fourth candidate matched open-drain within 0.2 cm³/s and is not shown. All four meshes close after a fix for zero-length ring vertices. Nothing was printed.

Same orifice model as round 00 (Cd 0.61, 5 mm head). v2 volume is the published solid. Cone volumes include the deep skirt. Round 00 knee had no median on record; its max ball was 7.0 mm and its smallest opening was 4.3 mm.

| Pick | Open | Max ball | Median ball | Gap | Flow | Film | Fingertip, 10 N | Volume |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smooth v2 | 50.5% | 8.6 mm | 8.6 mm | 0 | 78 cm³/s | 0 | 0.04 mm | 4304 mm³ |
| round 00 knee | 60.6% | 7.0 mm | — | — | 93 cm³/s | 0 | 0.11 mm | 3794 mm³ |
| open-drain | 63.9% | 7.2 mm | 6.9 mm | 0.28 mm | 98 cm³/s | 0 | 0.34 mm | 3593 mm³ |
| knee | 59.8% | 6.3 mm | 5.4 mm | 0.89 mm | 92 cm³/s | 0 | 0.49 mm | 3656 mm³ |
| hair-snag | 46.7% | 5.3 mm | 4.8 mm | 0.53 mm | 69 cm³/s | 0 | 0.09 mm | 3988 mm³ |

hair-snag still has 66 mm² of cells between 2.7 and 4.0 mm. Those are above the film cutoff and only get partial flow credit. Its smallest opening is 3.6 mm.

## AI review of the renders and the scores

The corners are rounded. Round 00's sharp polygons are gone, and the top views read as a web rather than a cracked plate. Cell sizes within one grate are close: the gaps are 0.3 to 0.9 mm, where round 00's capture pick had a 0.24 mm crack next to a 6.2 mm hole.

The radial grade did not become a picture you can point at. The exponents landed between 0.37 and 0.49, near uniform area. open-drain is ten similar cells around one center cell. hair-snag is the same idea, smaller, with heavier struts near the rim because its flare gene is 0.47. The knee is between them. None of them is "fine in the middle, open at the rim" in a way the sheet shows on its own.

Against the round 00 knee, open-drain drains a bit more (98 vs 93 cm³/s) at a similar ball (7.2 vs 7.0) and is stiffer than this round's knee but softer than the old knee (0.34 vs 0.11 mm), because the walls are thinner. The new knee buys a smaller ball (6.3 vs 7.0) at the same flow and sits on the deflection limit: 0.49 mm of a 0.5 mm cap, strut 1.35 mm. That is the print I would not choose yet. It has no margin.

Volume did not open a fourth option. The collar and the cone dominate the solid, so the lightest grate and the most open grate are the same part.

## Proposed for the next round

1. Move the knee off the deflection line. A 1.5 mm minimum strut, or a 0.35 mm cap, would stop the balanced pick from being the one that just passes.
2. Decide whether 3.6 mm cells are allowed. hair-snag's partial-flow area is the cells between the 2.7 mm film floor and the 4.0 mm full-credit size. Raising the floor to 4.0 mm makes every opening a full drain and gives up some of the 5.3 mm capture.
3. Leave volume as a reported number, not an objective. It collapsed onto open-drain. If the center should actually be the drain, pin the grade there instead of letting the exponent sit near 0.5.
