---
name: Basin hair catcher
description: >-
  Washbasin drain insert: hair catcher (Voronoi A/B/C) or toy-blocking
  guard (smooth v2). Read before resizing or searching this model.
---

# Basin hair catcher

Worked example in gendesign. Loop, print rule, and iteration record: [SKILL.md](../../SKILL.md).

Press-fit waste insert. Two jobs, two architectures: Voronoi A/B/C catch
hair; default **smooth v2** lets hair through and blocks an 8.6 mm ball
(search cap was 12 mm). Do not score a catcher on the toy-ball limit, or
the bowl on "catch every hair."

## Measure

Caliper the clear hole (~35 mm De40 here), seat width, clear depth, proud
height, and the largest object that must not fall in. Collar print OD
35.10 mm (CAD 35.21, 0.3% PLA shrink). Flange Ø46 × 1.6 mm was **assumed,
not measured**. v2 is 10.2 mm deep and flush; do not exceed 18 mm without
a new depth. Deep v3 needs ~35 mm of straight bore, which was not measured.
Printed collars shrink — confirm a press-fit with a test, not CAD alone.
Min strut 1.8 mm, min rim 1.2 mm, flange on the bed, overhang ≤ 50°.

## Lessons

- **A** printed 2026-11-12 (`designs/voronoi-a/test.md`): water hung in the small cells and the fine level webbed. Openings ~1–2 mm, some struts < 1.2 mm. That print is why B exists.
- **B** larger cells: openings ~4.6–7.4 mm, struts ~2 mm, still ~27% straight-through. There is no separate "organic A + B drainage" winner.
- **C** rounded pebbles and branching struts: best-looking catcher, fine level ~5.6 mm. Scripts, metrics, and preview are in `legacy-C/`; run them from that folder. Still a hair catcher, not a toy guard.
- **Smooth v2** (default): 50.54% open, 8.6 mm throat, 1.8 mm struts, ~4304 mm³, 45° lead-in, no supports. `generate.py` must stay within ~1% of those stats. Fit-only changes: edit `design.json`, do not re-search.
- **Deep v3**: ~86% open if the bore is deep enough, harder to clean, look was poor. Only beats v2 under ~27 mm of usable depth. Experimental.
- Plate SIMP shows load paths on a flat grate. It is not the toy-guard shape.

## Commands

```bash
python models/hair-catcher/generate.py
python models/hair-catcher/optimize.py --method smooth --quick   # also: deep, grid, voronoi, topopt
```
