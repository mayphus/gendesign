#!/usr/bin/env python3
"""A small gyroid block, written as STL + a mid-slice preview PNG."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gendesign.lattice import gyroid_mesh  # noqa: E402
from gendesign.evaluate import evaluate_mesh  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stl = out / "gyroid.stl"
    mesh = gyroid_mesh(period_mm=8.0, size_mm=(24, 16, 16), wall_t=0.8, out_stl=stl, n=36)
    import trimesh
    exported = trimesh.load(str(stl))
    assert mesh.is_watertight and exported.is_watertight, "gyroid mesh is not watertight"
    ev = evaluate_mesh(exported)
    print("wrote", stl, "volume_mm3", round(ev["volume_mm3"], 1), "watertight", ev["watertight"])
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        # slice preview via voxel midplane of the implicit field would need a rerun;
        # instead, a 2-D gyroid picture:
        k = 2 * np.pi / 8.0
        xs = np.linspace(0, 24, 240)
        ys = np.linspace(0, 16, 160)
        X, Y = np.meshgrid(xs, ys)
        Z = 8.0
        from gendesign.lattice import gyroid
        F = gyroid(k * X, k * Y, k * Z)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
        ax.contourf(X, Y, F, levels=12, cmap="bone")
        ax.set_aspect("equal")
        ax.set_title("gyroid mid-slice (z=8 mm)")
        fig.tight_layout()
        fig.savefig(out / "gyroid-slice.png")
        plt.close(fig)
        print("preview", out / "gyroid-slice.png")
    except Exception as e:
        print("preview skipped:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
