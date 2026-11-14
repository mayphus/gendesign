---
name: gendesign
description: Generative design for a physical part. Requirements, a named method, a measured print. Read models/<name>/SKILL.md. Nothing here starts a print.
---

# gendesign

The goal is a working physical object. An agent and the code share one loop. A saved design JSON rebuilds the geometry; the bench decides whether it worked.

`models/hair-catcher` and `models/drybox-adapter` are worked examples. Methods live in the `gendesign` package. Planned methods are in [ROADMAP.md](ROADMAP.md).

## Loop

1. Requirements, with units. Do not invent a fit-critical dimension.
2. Analysis: loads, flow, or fit — whichever actually decides the part.
3. Generate / optimize with a named method. Save the winner as `designs/<name>/design.json`.
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

`test.md`: printed?, settings, measured dims vs designed, fit/function, photos, failure notes, next change.
A design-level `test.md` is fine when the print is not one search round.
Known records: `models/hair-catcher/designs/voronoi-a/test.md`,
`models/drybox-adapter/designs/v9-8.85/test.md`.

## Commands

```bash
pip install -e .
pip install -r requirements.txt
gendesign topopt2d --quick --out out/topopt2d
python models/hair-catcher/generate.py
python models/drybox-adapter/generate.py
python examples/gyroid_shell/run.py
```

`python -m gendesign` is the same CLI. Version C scripts run from `models/hair-catcher/legacy-C/`. CadQuery generates the guard and the adapter; the `gendesign` commands do not need it.
