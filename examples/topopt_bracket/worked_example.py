#!/usr/bin/env python3
"""Worked example: 2-D topology optimization of a bolted cantilever bracket.

Problem (plane stress, steel plate)
-----------------------------------
  Design space : 120 mm × 40 mm rectangle (extruded thickness t = 5 mm for review)
  Mesh         : 60 × 20 Q4 elements (2 mm / element)  — use --quick for 30 × 10
  Material     : steel, E = 200 GPa, ν = 0.3, σ_y ≈ 250 MPa (yield for reference only)
  Supports     : two bolt holes on the left edge (Ø8 mm), node DOFs fixed on hole
                 perimeters; hole interiors are forced void; a thin washer ring is
                 forced solid so the optimizer keeps mounting pads
  Load         : F = 50 N downward at the mid-height of the right edge
  Target       : volume fraction volfrac = 0.30 (keep ≤ 30% of the design-space area)

Formulation (SIMP + OC)
-----------------------
  minimize   compliance  c = Uᵀ K(ρ) U
  subject to  (1/N) Σ ρ_e ≤ volfrac
              0 < ρ_min ≤ ρ_e ≤ 1
  with       E(ρ) = E_min + ρ^p (E₀ − E_min),  p = 3
             density filter radius r_min ≈ 1.5 elements (≈ 3 mm) for min feature size

  Linear-elastic FEA → element sensitivities → optimality-criteria density update.
  Absolute E and F scale compliance but not the optimal *shape* for this linear
  problem, so the solver uses E₀ = 1 and |F| = 1 for numerical stability while
  the physical steel / 50 N values are documented above for review.
  Yield is *not* enforced here (compliance-only). A stress-constrained variant
  would add max(σ_vm(ρ)) ≤ σ_allow as a constraint (e.g. via MMA / P-norm).

Expected result (qualitative)
-----------------------------
  Material concentrates into a truss-like bracket: solid pads around the two bolts,
  a compression strut from the upper bolt toward the load, a tension tie from the
  lower bolt toward the load, and a sparse or empty interior. The right edge keeps
  a small pad where the load is applied. Gray intermediate densities fade as the
  SIMP penalty pushes the field toward 0/1.

Manufacturability
-----------------
  r_min ≈ 3 mm sets a minimum member width for FDM/SLA. Print with the plate flat
  on the bed (extrusion direction = thickness) so the 2-D topology needs no
  overhang supports; avoid standing the thin members vertically.

Run
---
  python examples/topopt_bracket/worked_example.py --quick
  python examples/topopt_bracket/worked_example.py          # finer mesh, more iters
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gendesign.topopt2d import topopt_2d, _save_density_image  # noqa: E402


# --- physical problem definition ------------------------------------------------
L_MM, H_MM = 120.0, 40.0
THICKNESS_MM = 5.0
E_PA = 200e9  # steel Young's modulus
NU = 0.3
SIGMA_Y_PA = 250e6  # yield, reference only (not constrained)
F_N = 50.0  # downward tip load
VOLFRAC = 0.30
BOLT_D_MM = 8.0
BOLT_CX_MM = 10.0  # hole centers from left edge
BOLT_CY_MM = (10.0, 30.0)  # lower / upper
WASHER_EXTRA_MM = 3.0  # solid ring outside bolt radius


def _node_index(nelx: int, nely: int, ix: int, iy: int) -> int:
    """Node (ix, iy) with ix in [0, nelx], iy in [0, nely]; numbering matches topopt2d."""
    return ix * (nely + 1) + iy


def _element_centers(nelx: int, nely: int):
    dx, dy = L_MM / nelx, H_MM / nely
    xs = (np.arange(nelx) + 0.5) * dx
    ys = (np.arange(nely) + 0.5) * dy
    X, Y = np.meshgrid(xs, ys)  # (nely, nelx)
    return X, Y, dx, dy


def bolt_masks(nelx: int, nely: int):
    """Passive void (hole) and passive solid (washer) element masks."""
    X, Y, _, _ = _element_centers(nelx, nely)
    r_hole = BOLT_D_MM / 2.0
    r_washer = r_hole + WASHER_EXTRA_MM
    void = np.zeros((nely, nelx), dtype=bool)
    solid = np.zeros((nely, nelx), dtype=bool)
    for cy in BOLT_CY_MM:
        r = np.hypot(X - BOLT_CX_MM, Y - cy)
        void |= r <= r_hole
        solid |= (r > r_hole) & (r <= r_washer)
    solid &= ~void
    return solid, void


def bolt_fixed_dofs(nelx: int, nely: int):
    """Fix UX, UY on nodes that lie on either bolt-hole circumference (approx)."""
    dx, dy = L_MM / nelx, H_MM / nely
    r_hole = BOLT_D_MM / 2.0
    # band around the hole edge so several nodes get clamped
    band = 0.6 * max(dx, dy)
    fixed = []
    for ix in range(nelx + 1):
        for iy in range(nely + 1):
            x, y = ix * dx, iy * dy
            for cy in BOLT_CY_MM:
                r = abs(np.hypot(x - BOLT_CX_MM, y - cy) - r_hole)
                if r <= band:
                    n = _node_index(nelx, nely, ix, iy)
                    fixed.append((n, 0))
                    fixed.append((n, 1))
    # unique
    return list({(n, d) for n, d in fixed})


def tip_load(nelx: int, nely: int):
    """Single downward nodal force at mid-height of the right edge (unit load)."""
    n = _node_index(nelx, nely, nelx, nely // 2)
    return [(n, 1, -1.0)]


def annotate_setup_image(density: np.ndarray, path: Path, nelx: int, nely: int):
    """Density plot with bolt circles and load arrow for review."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyArrowPatch

    fig, ax = plt.subplots(figsize=(9, 3.2), dpi=140)
    ax.imshow(
        1.0 - density,
        cmap="gray",
        origin="lower",
        extent=[0, L_MM, 0, H_MM],
        vmin=0,
        vmax=1,
        aspect="equal",
    )
    for cy in BOLT_CY_MM:
        ax.add_patch(
            Circle((BOLT_CX_MM, cy), BOLT_D_MM / 2, fill=False, ec="#c0392b", lw=1.4)
        )
        ax.add_patch(
            Circle(
                (BOLT_CX_MM, cy),
                BOLT_D_MM / 2 + WASHER_EXTRA_MM,
                fill=False,
                ec="#2980b9",
                lw=0.9,
                ls="--",
            )
        )
    ax.add_patch(
        FancyArrowPatch(
            (L_MM + 2, H_MM / 2 + 8),
            (L_MM + 2, H_MM / 2 - 2),
            arrowstyle="-|>",
            mutation_scale=14,
            color="#c0392b",
            lw=1.5,
        )
    )
    ax.text(L_MM + 4, H_MM / 2, f"{F_N:.0f} N", color="#c0392b", va="center", fontsize=9)
    ax.set_xlim(-2, L_MM + 18)
    ax.set_ylim(-2, H_MM + 2)
    ax.set_xlabel("mm")
    ax.set_ylabel("mm")
    ax.set_title(f"SIMP bracket  volfrac={VOLFRAC:.0%}  steel E={E_PA/1e9:.0f} GPa")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quick", action="store_true", help="coarse 30×10 mesh, ~25 iters")
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    args = p.parse_args()

    if args.quick:
        nelx, nely, niter = 30, 10, 25
    else:
        nelx, nely, niter = 60, 20, 60

    solid, void = bolt_masks(nelx, nely)
    fixed = bolt_fixed_dofs(nelx, nely)
    loads = tip_load(nelx, nely)
    # filter radius ~3 mm in element units
    rmin = max(1.5, 3.0 / (L_MM / nelx))

    print("=== Bolted cantilever bracket (SIMP) ===")
    print(f"domain     {L_MM:.0f}×{H_MM:.0f} mm, t={THICKNESS_MM:.0f} mm")
    print(f"mesh       {nelx}×{nely}  rmin={rmin:.2f} elem  volfrac={VOLFRAC}")
    print(f"material   E={E_PA/1e9:.0f} GPa  ν={NU}  σ_y≈{SIGMA_Y_PA/1e6:.0f} MPa (ref)")
    print(f"load       {F_N:.0f} N down at right mid-edge")
    print(f"supports   {len(fixed)//2} nodes on two Ø{BOLT_D_MM:.0f} mm bolt holes")
    print(f"passive    solid={int(solid.sum())}  void={int(void.sum())} elements")
    print()

    # Unit E and F keep OC / compliance well-conditioned; topology is unchanged
    # vs physical E=200 GPa and F=50 N for this linear compliance problem.
    res = topopt_2d(
        nelx=nelx,
        nely=nely,
        volfrac=VOLFRAC,
        penal=3.0,
        rmin=rmin,
        niter=niter,
        E0=1.0,
        Emin=1e-9,
        nu=NU,
        passive_solid=solid,
        passive_void=void,
        fixed=fixed,
        loads=loads,
        verbose=True,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "density.npy", res.density)
    _save_density_image(res.density, out / "density.png")
    annotate_setup_image(res.density, out / "result_annotated.png", nelx, nely)

    stats = {
        "problem": "bolted_cantilever_bracket_2d",
        "L_mm": L_MM,
        "H_mm": H_MM,
        "thickness_mm": THICKNESS_MM,
        "E_Pa": E_PA,
        "E0_solver": 1.0,
        "nu": NU,
        "sigma_y_Pa": SIGMA_Y_PA,
        "F_N": F_N,
        "F_solver": -1.0,
        "volfrac": VOLFRAC,
        "nelx": nelx,
        "nely": nely,
        "rmin_elem": rmin,
        "rmin_mm": rmin * (L_MM / nelx),
        "final_compliance": res.compliance[-1] if res.compliance else None,
        "final_volume": res.volume[-1] if res.volume else None,
        "iters": res.info.get("iters"),
        "formulation": "min compliance s.t. volume ≤ volfrac (SIMP p=3, OC update)",
        "expected_shape": (
            "truss-like members from upper/lower bolt pads to the loaded right edge; "
            "bolt washers remain solid; interior mostly void"
        ),
        "manufacturability": (
            f"min feature ≈ {rmin * (L_MM / nelx):.1f} mm from density filter; "
            "print flat (thickness = build Z) to avoid overhangs on 2-D members"
        ),
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=2))

    print()
    print(f"wrote {out / 'density.png'}")
    print(f"wrote {out / 'result_annotated.png'}")
    print(f"wrote {out / 'stats.json'}")
    print(f"final vol={res.volume[-1]:.3f}  compliance={res.compliance[-1]:.4e}")
    print()
    print("Expected shape: bolt pads + diagonal compression/tension struts to the tip load.")
    print(stats["manufacturability"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
