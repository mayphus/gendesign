---
name: Drybox adapter
description: >-
  PTFE bowden-insert pocket that presses into a filament-dryer wall
  grommet. Fit problem: sweep pocket size, then test-fit.
---

# Drybox adapter

Worked example in gendesign. Loop, print rule, and iteration record: [SKILL.md](../../SKILL.md).

Revolved grommet: flared mouth, PTFE pocket, 45° cone floor (no flat ledge
over the bore), filament through-hole, barbed stem. Default **v9, P = 8.85 mm**.

## Measure

Caliper the insert across the lands that enter the pocket (one pin was
~8.7 mm), the dryer-wall hole, and — after a test print — the printed
pocket. Printed holes come out ~0.1–0.2 mm undersized, so a pocket drawn
at the pin size often will not accept it. That is why v9 is 8.85 mm, not
8.7. On one dryer the insert went straight into the wall hole, so this
adapter may be unnecessary. Check that before printing coupons.

## Lessons

Parameter sweep only. v9 geometry stays fixed; change P. Try about pin,
pin + 0.15 mm, and pin + 0.25 mm, print at 100% infill with no supports,
and test the real insert. Too tight: +0.05–0.10 mm. Rattles: go down.
Do not pick a winner from CAD volume. Topology optimization does not help
this fit. The bench note is `designs/v9-8.85/test.md`.

## Commands

```bash
python models/drybox-adapter/generate.py                 # P=8.85
python models/drybox-adapter/generate.py -P 8.9 -o out/drybox
python models/drybox-adapter/optimize.py --quick
python models/drybox-adapter/optimize.py --pockets 8.7 8.8 8.85 8.9
```

Section: `docs/v9_section_compare.png`. Saved design: `designs/v9-8.85/design.json`.
