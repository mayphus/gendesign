# Worked example: bolted cantilever bracket (2-D SIMP)

Self-contained review case for topology optimization / generative design.

## 1. Problem setup

| Item | Value |
|---|---|
| Design space | 120 × 40 mm rectangle (review thickness 5 mm) |
| Mesh | 60 × 20 Q4 elements (or `--quick`: 30 × 10) |
| Material | Steel, E = 200 GPa, ν = 0.3, σ_y ≈ 250 MPa (reference only) |
| Supports | Two Ø8 mm bolt holes on the left; perimeter nodes fixed |
| Load | 50 N downward at mid-height of the right edge |
| Volume target | 30% of the design-space area |

Hole interiors are forced void; a thin washer ring around each bolt is forced solid so mounting pads survive.

## 2. Formulation

Minimize compliance \(c = \mathbf{U}^\top \mathbf{K}(\boldsymbol{\rho})\,\mathbf{U}\) subject to mean density ≤ 0.30, with SIMP \(E(\rho)=E_{\min}+\rho^p(E_0-E_{\min})\), \(p=3\), a density filter, and an optimality-criteria update. Yield is **not** constrained here; a stress-constrained variant would add \(\max\sigma_{\mathrm{vm}}\le\sigma_{\mathrm{allow}}\).

## 3. Run

```bash
# from repo root, with deps installed (numpy/scipy/matplotlib)
python examples/topopt_bracket/worked_example.py --quick
python examples/topopt_bracket/worked_example.py
```

Writes `out/density.png`, `out/result_annotated.png`, `out/stats.json`, `out/density.npy`.

The solver lives in [`gendesign/topopt2d.py`](../../gendesign/topopt2d.py); the worked script sets geometry, bolt BCs, load, and material.

For the same problem inside the analyze → round loop (NSGA over volfrac / rmin / load height), see [`models/cantilever-bracket/`](../../models/cantilever-bracket/).

## 4. Expected result

A truss-like bracket: solid pads at the two bolts, a compression member from the upper bolt toward the load, a tension member from the lower bolt, and a mostly empty interior. Intermediate gray densities fade as SIMP pushes toward 0/1.

## 5. Manufacturability

The density filter (`r_min` ≈ 3 mm) enforces a minimum member width. Print the plate flat on the bed (build direction = thickness) so the 2-D members need no overhang supports.
