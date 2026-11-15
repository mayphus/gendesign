# Round 02

## What changed

The owner reviewed round 01: even cells, rounded corners, no film. All three proposals went in.

1. Minimum strut is 1.5 mm. The 0.5 mm fingertip cap stays a constraint.
2. The opening floor is 4.0 mm, so every kept cell is a full drain. The 2.7 mm film length is still the physics cutoff underneath that.
3. Volume is reported, not searched. The objectives are drainage and capture. The grade is pinned: a seed stays at the center, and the other cells get smaller toward the rim. The exponent only sets how strong that grade is.

Who decided: the owner, from the round 01 top sheet. The code searched (population 28, 10 generations, 308 evaluations). This note is the AI review of the new renders, the scores, and the print mesh.

## Result

26 designs on the final front, all feasible. Hypervolume on flow and capture went from 0.56 to 0.63. Three watertight picks. Nothing was printed.

| Pick | Open | Max ball | Smallest cell | Flow | Film | Fingertip, 10 N | Strut | Volume |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smooth v2 | 50.5% | 8.6 mm | 8.6 mm | 78 cm³/s | 0 | 0.04 mm | 1.8 mm | 4304 mm³ |
| round 01 knee | 59.8% | 6.3 mm | 4.3 mm | 92 cm³/s | 0 | 0.49 mm | 1.35 mm | 3656 mm³ |
| open-drain | 69.4% | 8.8 mm | 8.7 mm | 107 cm³/s | 0 | 0.26 mm | 1.51 mm | 3550 mm³ |
| knee | 60.1% | 7.1 mm | 4.5 mm | 92 cm³/s | 0 | 0.11 mm | 1.57 mm | 3802 mm³ |
| hair-snag | 50.6% | 5.8 mm | 4.1 mm | 78 cm³/s | 0 | 0.08 mm | 1.93 mm | 3978 mm³ |

The strut floor did what it was asked. The round 01 knee sat at 0.49 mm of a 0.50 mm cap. This knee is at 0.11 mm, with a 1.57 mm strut. Flow is the same 92 cm³/s. The ball went from 6.3 mm to 7.1 mm because every cell now has to clear 4.0 mm and the walls are thicker. No pick has film area, and none has a partial-flow cell in the score.

## AI review

The knee is the one I would keep. It is a center cell (the largest ball, 7.1 mm, and the most area) with smaller openings around it (down to 4.5 mm). The rim cells are long wedges, so in the photo they can look bigger than the center even though a ball does not agree. open-drain barely grades at all: six cells, 8.7 to 8.8 mm, the most water, and almost the v2 ball. hair-snag matches v2's flow with a 5.8 mm ball and 1.9 mm struts. Corners stay rounded. The 3/4 view of the knee is still the deep cone, about 17 mm of insert under the flange.

## Print checks on the knee mesh

Not a slicer run, and not a print.

- Overhang. The cone is 47° from horizontal, so the designed underside is 43° from vertical, inside a 45° rule. On the print mesh, about 22 mm² of faces sit a degree or two past 45°, and about 2.5 mm² past 50°. That is facet noise on the cone, not a flat ledge. A slicer preview is the check that would settle it.
- First layer. About 900 mm² of downward face sits on the bed. The flange annulus is about 860 mm², so the contact is the full ring, not a knife edge. The openings are inside that ring and are not on the bed.
- A1 mini. The part is 46 mm across and 17 mm tall. The machine bed is 180 mm. It fits. The collar is still the existing 35.10 mm press-fit target for a measured 35 mm hole. The flange diameter, 46 mm, was assumed and has never been calipered. The insert is 17.9 mm. The straight depth of the bore was not measured, and smooth v2 only used 10 mm.

## Are we close to a print candidate?

Close on the grate, not cleared to print. The knee is the candidate I would take into a fit check: film-free, every cell a full drain, deflection at 0.11 mm against a 0.5 mm cap, strut 1.57 mm. I would not start a print until someone calipers the seat and the straight bore depth, and until a slicer preview confirms the cone does not ask for supports. The orifice flow and the grillage are still ranking models, not a measured drain or a shell test.

## Proposed for the next round

1. If the rim wedges still look like the big holes, shorten them. The ball numbers already say the center is larger. The photo argues.
2. Stop searching cell count on this knee unless a tighter than 7 mm ball is required. The open pick is a different product (an 8.8 mm throat).
3. The next useful step is measurement, not another generation: seat diameter, straight bore depth, then a slicer preview of the print STL. No print until those exist.

## Owner measurement, same day

The owner confirmed the drain hole at 35 mm. The press-fit collar stays 35.10 mm. He also said the bore is deep enough, about 100 mm, so there is no 10 mm insert cap. That depth is his estimate, not a saved caliper reading. The round 02 knee, 17.9 mm under the flange on the 47° cone, is the chosen design. It is well under ~100 mm. Round 03 was not run. The flange seat is still unmeasured. Nothing was printed.

Print STL: `iterations/02/picks/knee/basin-knee-print.stl` (flange on the bed).
