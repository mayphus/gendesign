# Models

Generative designs for 3D-printed parts. The goal is a working physical
object. A saved design JSON rebuilds the geometry; it does not finish the job.

**Loop:** requirements → analysis (loads, flow, or fit) → generate/optimize
→ printability and slice → print, only on the owner's go → physical test →
measure and photograph → feed that back into the next design.

Read [SKILL.md](SKILL.md) for the loop and the iteration record. Read
`models/<name>/SKILL.md` for one part. **Nothing in this repo starts a print
on its own.**

## Models

| | | |
|---|---|---|
| [Hair catcher / basin guard](models/hair-catcher/) | [![smooth v2](models/hair-catcher/docs/preview-34.png)](models/hair-catcher/) | Default **smooth v2**: a 7-hole bowl that lets hair through and blocks an 8.6 mm ball. Voronoi A was printed and drained poorly; B is the drainage revision. C and v2 have no recorded bench test. |
| [Drybox adapter](models/drybox-adapter/) | [![v9 section](models/drybox-adapter/docs/v9_section_compare.png)](models/drybox-adapter/) | v9 pocket for a PTFE insert (default P = 8.85 mm). Printed holes come out ~0.1–0.2 mm undersized — measure and test-fit. |

Physical notes: [`models/hair-catcher/designs/voronoi-a/test.md`](models/hair-catcher/designs/voronoi-a/test.md),
[`models/drybox-adapter/designs/v9-8.85/test.md`](models/drybox-adapter/designs/v9-8.85/test.md).

The original two-level Voronoi **version C** that used to sit at the repo
root lives in [`models/hair-catcher/legacy-C/`](models/hair-catcher/legacy-C/)
(scripts, metrics, and preview). It has not been test-printed. Run
`search.py`, `build.py`, and `render.py` from that folder.

## Setup and commands

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
python models/hair-catcher/generate.py          # smooth v2 STL + STEP + stats
python models/drybox-adapter/generate.py        # v9, P=8.85
python generate_all.py                          # both defaults into out/
python models/hair-catcher/optimize.py --method smooth --quick
python models/drybox-adapter/optimize.py --quick
python -m gendesign topopt2d --quick --out out/topopt2d
python examples/gyroid_shell/run.py
```

CadQuery / OCP generates the basin guard and the adapter. The `gendesign`
examples run on numpy, scipy, scikit-image, trimesh, and matplotlib alone.
Slice estimates here are stand-ins unless the note says Bambu Studio or
OrcaSlicer. Re-slice for a real time.

## Design rules

- Function first, but looks matter.
- No flat internal floors or ledges over air — use 45° cones or chamfers.
- Flat face on the bed; no supports unless the model says so.
- 100% infill on small parts.
- Never start a print without the owner's go.
- After a print, write `test.md`: printed?, settings, measured dims vs
  designed, fit/function, photos, failure notes, next change.

## Layout

```
SKILL.md                        loop, rules, iteration record
gendesign/                      SIMP, lattices, search, evaluation, iteration logs
examples/                       runnable topopt bracket + gyroid
models/<name>/                  SKILL.md, requirements, optimize, generate, designs/, docs/
models/hair-catcher/legacy-C/   original public version C (scripts, metrics, preview)
templates/model/                starter for a new part
```

Code is MIT (see [LICENSE](LICENSE)).
