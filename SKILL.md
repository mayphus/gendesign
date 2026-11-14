---
name: Generative design
description: Requirements through a measured physical part. Read models/<name>/SKILL.md. Nothing here starts a print.
---

# Generative design

The goal is a working physical object. A CAD file is a step, not the result.
Read the model skill for what already failed on the bench. Function comes
first; looks still matter.

## Loop

1. Requirements, with units. Do not invent a fit-critical dimension.
2. Analysis: loads, flow, or fit — whichever actually decides the part.
3. Generate / optimize. Save the winner as `designs/<name>/design.json`.
4. Printability and a slice estimate. Re-slice for a real time.
5. Print only after the owner's go.
6. Physical test. Measure and photograph.
7. Write `test.md` and feed that result into the next design.

## Design rules

- No flat internal floors or ledges over air. Use 45° cones or chamfers.
- Flat face on the bed. No supports unless that model says so.
- 100% infill on small parts.
- Never start a print without the owner's go.
- Each iteration: renders plus a one-line critique. After a print, a `test.md`.

## Iteration record

```
models/<name>/designs/<design>/design.json
models/<name>/designs/<design>/iterations/NN/
    params.json  stats.json  critique.md  preview.png  test.md
```

`test.md` (or the same fields in the iteration JSON): printed?, settings,
measured dims vs designed, fit/function, photos, failure notes, next change.
A design-level `test.md` is fine when the print is not one search round.
Known records: `models/hair-catcher/designs/voronoi-a/test.md`,
`models/drybox-adapter/designs/v9-8.85/test.md`.

## Layout and commands

```
gendesign/   examples/   models/<name>/   models/hair-catcher/legacy-C/   templates/model/
```

```bash
pip install -r requirements.txt
python models/hair-catcher/generate.py
python models/drybox-adapter/generate.py
python -m gendesign topopt2d --quick --out out/topopt2d
python examples/gyroid_shell/run.py
```

Version C scripts run from `models/hair-catcher/legacy-C/`. CadQuery generates
the guard and the adapter; `gendesign` examples do not need it.
