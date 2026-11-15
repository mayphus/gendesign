# Cantilever bracket

Topology optimization inside the gendesign loop: requirements → analysis → round.

A 120×40 mm plate, two Ø8 mm left bolt holes, 50 N tip load. The generator runs 2-D SIMP; genes are **volume fraction**, **filter radius (mm)**, and **load height** on the right edge. Objectives: stiffness (−compliance) and lightness (−volume).

## Run

```bash
.venv/bin/gendesign analyze models/cantilever-bracket
.venv/bin/gendesign round models/cantilever-bracket --pop 4 --gens 2 --seed 1 \
  --note "first topopt round: trade volume vs stiffness"
.venv/bin/gendesign report models/cantilever-bracket
```

Standalone (no round search): `python examples/topopt_bracket/worked_example.py --quick`

## Notes

- Mesh for rounds is coarse (30×10, 20 iters) so each gene evaluation stays cheap.
- `function.print_flat: true` (default) prints with thickness as build Z — overhang filter off.
- Set `print_flat: false` to enable the +y self-supporting projection during SIMP.
