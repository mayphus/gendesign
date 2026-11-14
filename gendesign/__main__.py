"""CLI: python -m gendesign <command> ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_topopt2d(args):
    from .topopt2d import topopt_2d

    res = topopt_2d(nelx=args.nelx, nely=args.nely, volfrac=args.volfrac, niter=args.niter, rmin=args.rmin)
    out, mesh = res.save(args.out, pixel_mm=args.pixel, thickness_mm=args.thickness)
    print("wrote", out)
    if mesh:
        print("stl", mesh)


def _cmd_topopt3d(args):
    from .topopt3d import topopt_3d

    res = topopt_3d(nelx=args.nelx, nely=args.nely, nelz=args.nelz, volfrac=args.volfrac, niter=args.niter)
    out, mesh = res.save(args.out, voxel_mm=args.voxel)
    print("wrote", out)
    if mesh:
        print("stl", mesh)


def _cmd_gyroid(args):
    from .lattice import gyroid_mesh

    size = (args.sx, args.sy, args.sz)
    mesh = gyroid_mesh(period_mm=args.period, size_mm=size, wall_t=args.wall, out_stl=args.out, n=args.n)
    print("stl", args.out, "watertight", mesh.is_watertight, "volume", round(float(mesh.volume), 1))


def _cmd_sheet(args):
    from .iterate import contact_sheet, evolution_gif, score_chart

    d = Path(args.design)
    print(contact_sheet(d, args.sheet, title=args.title))
    if args.gif:
        print(evolution_gif(d, args.gif))
    if args.chart:
        try:
            print(score_chart(d, args.chart, score_key=args.score_key))
        except Exception as e:
            print("chart skipped:", e)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m gendesign", description="Generative-design toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("topopt2d", help="2-D SIMP cantilever (or saved density + STL)")
    t.add_argument("--nelx", type=int, default=60)
    t.add_argument("--nely", type=int, default=20)
    t.add_argument("--volfrac", type=float, default=0.35)
    t.add_argument("--niter", type=int, default=60)
    t.add_argument("--rmin", type=float, default=1.5)
    t.add_argument("--pixel", type=float, default=1.0, help="element size in mm for STL export")
    t.add_argument("--thickness", type=float, default=2.0)
    t.add_argument("--out", default="out/topopt2d")
    t.add_argument("--quick", action="store_true")
    t.set_defaults(func=_cmd_topopt2d)

    t3 = sub.add_parser("topopt3d", help="small 3-D voxel SIMP cantilever")
    t3.add_argument("--nelx", type=int, default=16)
    t3.add_argument("--nely", type=int, default=8)
    t3.add_argument("--nelz", type=int, default=8)
    t3.add_argument("--volfrac", type=float, default=0.3)
    t3.add_argument("--niter", type=int, default=20)
    t3.add_argument("--voxel", type=float, default=1.0)
    t3.add_argument("--out", default="out/topopt3d")
    t3.add_argument("--quick", action="store_true")
    t3.set_defaults(func=_cmd_topopt3d)

    g = sub.add_parser("gyroid", help="TPMS gyroid sheet/block")
    g.add_argument("--period", type=float, default=10.0)
    g.add_argument("--sx", type=float, default=30)
    g.add_argument("--sy", type=float, default=20)
    g.add_argument("--sz", type=float, default=16)
    g.add_argument("--wall", type=float, default=0.8)
    g.add_argument("--n", type=int, default=40)
    g.add_argument("--out", default="out/gyroid.stl")
    g.set_defaults(func=_cmd_gyroid)

    it = sub.add_parser("iterate", help="build contact sheet / gif / score chart from a design folder")
    it.add_argument("design", help="path to designs/<name>/")
    it.add_argument("--sheet", default=None)
    it.add_argument("--gif", default=None)
    it.add_argument("--chart", default=None)
    it.add_argument("--title", default=None)
    it.add_argument("--score-key", default="score")
    it.set_defaults(func=_cmd_sheet)

    args = p.parse_args(argv)
    if getattr(args, "quick", False) and args.cmd == "topopt2d":
        args.nelx, args.nely, args.niter = 32, 12, 20
    if getattr(args, "quick", False) and args.cmd == "topopt3d":
        args.nelx, args.nely, args.nelz, args.niter = 10, 5, 5, 8
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
