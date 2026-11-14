#!/usr/bin/env python3
"""Cantilever bracket via 2-D SIMP. Writes density.png + an extruded STL."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gendesign.topopt2d import topopt_2d  # noqa: E402
from gendesign.evaluate import evaluate_mesh, overhang_report  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true")
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    args = p.parse_args()
    if args.quick:
        nelx, nely, niter = 32, 12, 18
    else:
        nelx, nely, niter = 60, 20, 60
    res = topopt_2d(nelx=nelx, nely=nely, volfrac=0.35, niter=niter, rmin=1.5)
    out, mesh = res.save(args.out, pixel_mm=1.0, thickness_mm=3.0)
    print("density + stats ->", out)
    if mesh:
        ev = evaluate_mesh(mesh)
        print("stl", mesh, "volume_mm3", round(ev["volume_mm3"], 1), "overhang", ev["overhang"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
