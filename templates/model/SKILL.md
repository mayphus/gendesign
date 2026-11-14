---
name: (Model name)
description: >-
  One line: the part, the job, and when to read this skill.
---

# (Model name)

Worked example in gendesign. Loop, print rule, and iteration record: [SKILL.md](../../SKILL.md).

What the part does, in two or three lines. Name the default saved design.

## Measure

Fit-critical dimensions, how to take them, and which numbers were only assumed.

## Lessons

- What you tried, what you kept, and why it failed or won. Point at `designs/` and `requirements.yaml`.

## Commands

```bash
python models/<name>/generate.py
python models/<name>/optimize.py --quick
```

Save each round under `designs/<design>/iterations/NN/` with renders and a one-line critique. After a print, add `test.md` (printed?, settings, measured vs designed, fit/function, photos, failure notes, next change). Never start a print without the owner's go.
