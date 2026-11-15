---
name: Basin hair catcher
description: >-
  Washbasin drain insert, the main gendesign example. Read before analyzing,
  running a round, or reviewing a pick of this model.
---

# Basin hair catcher

The loop and its rules: [SKILL.md](../../SKILL.md). Current state: [REPORT.md](REPORT.md).

## Analysis (in `model.py: analyze`)

- Drainage binds: open area from `A = Q / (Cd sqrt(2 g h))`, Q = `function.drain_flow_min_cm3_s`. The 78 cm³/s is smooth v2 under the same model, not a measured tap rate.
- Hole floor 4.0 mm: water holds a film under the 2.7 mm capillary length (Voronoi A held water in ~1 mm cells).
- Plate: clamped circular plate, D scaled by solid fraction². Fingertip 10 N ≤ 0.5 mm; hard push 30 N ≤ `physics.allowable_MPa` (20, a guess). Structure is second to bind.
- Concepts: flat plate (chosen), cone (fallback if holes must go under ~5 mm), two-level (rejected: bridges or vaults, and less flow).

## Evaluators (in `model.py`)

`drainage` (objective, and the flow target as a constraint), `capture` (objective: ball margin minus half the max-median gap), `structure` (constraint), `print-rules` (rib, rim, hole floor). Missing: corner rounding. `gendesign.corners` measures hair snag and corner water; add it before claiming a rounder hole is better.

## Measure

Hole 35 mm confirmed. Collar 35.10 mm printed OD. Flange Ø46 × 1.6 mm assumed. Straight bore ~100 mm is the owner's estimate. Printed collars shrink: confirm the press-fit with a test, not CAD.

## Lessons

- **Voronoi A** (printed 2026-11-12): strong hair catch, but water hung in the fine cells. Source of the 4 mm floor.
- **pebble-c**: the fine layer bridges ~189 mm² over air. **pebble-d** vaults it but pushes fine cells toward 2.8 mm. **pebble-e** drops the second layer: nothing over air.
- **generative-v1 round 03**: the owner ruled that smoothness is not an objective; rounding must come from a functional score.
- **pebble-plate rounds 00–01**: with drainage as the only area pressure, `round_frac` sits at its lower bound. The holes go polygonal until a corner score pushes back.
