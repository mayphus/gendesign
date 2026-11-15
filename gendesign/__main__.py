"""CLI: gendesign <command> ...  (python -m gendesign is the same entry point)."""
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


def _cmd_analyze(args):
    from .loop import analyze

    a = analyze(args.model)
    for k, t in a.get("targets", {}).items():
        print(f"  {k:22s} {t.get('value')}")
    print("concept:", a.get("chosen"), "| wrote", Path(args.model) / "analysis.md")


def _cmd_round(args):
    from .loop import run_round

    it = run_round(
        args.model, design=args.design, pop=args.pop, gens=args.gens, seed=args.seed,
        picks=args.picks, export=not args.no_export, from_round=args.from_round, note=args.note,
    )
    print("wrote", it)
    print("next: the AI reviews picks.png and fills decisions.md; the owner approves a pick.")


def _cmd_status(args):
    import json

    from .loop import status

    s = status(args.model)
    if args.json:
        print(json.dumps(s, indent=2))
        return
    print(f"{s['model']}: requirements {'ok' if s['requirements_ok'] else s['requirement_errors']}, "
          f"model.py {'yes' if s['has_model_py'] else 'no'}")
    for d in s["designs"]:
        rs = d["rounds"]
        pending = [r["round"] for r in rs if not r["reviewed"]]
        approved = [f"{r['round']}/{a}" for r in rs for a in r["approved"]]
        span = rs[0]['round'] if len(rs) == 1 else f"{rs[0]['round']}–{rs[-1]['round']}" if rs else ""
        rounds = f"{len(rs)} round{'s' if len(rs) != 1 else ''} ({span})" if rs else ""
        if pending:
            rounds += f", review pending: {', '.join(pending)}"
        if approved:
            rounds += f", approved: {', '.join(approved)}"
        tests = f"  tests: {len(d['tests'])}" if d["tests"] else ""
        print(f"  {d['design']}: {rounds or 'no rounds'}{tests}")
    if not s.get("analysis"):
        print("  no analysis.json: run `gendesign analyze` before a round")


def _cmd_generate(args):
    import json

    from .loop import generate

    out, rep = generate(args.model, args.source, args.out)
    print("wrote", out)
    print(json.dumps({k: rep[k] for k in ("mesh", "mesh_problems", "genes_outside_bounds")}, indent=1))


def _cmd_report(args):
    from .loop import report

    print("wrote", report(args.model))


def _cmd_approve(args):
    from .loop import approve

    print("recorded", approve(args.iteration, args.pick, note=args.note))


def _cmd_feedback(args):
    import json

    from .loop import record_feedback

    print(json.dumps(record_feedback(args.test_md), indent=2))


def _cmd_new(args):
    import shutil

    src = Path(__file__).resolve().parent.parent / "templates" / "model"
    dst = Path(args.dest)
    if dst.exists():
        raise SystemExit(f"{dst} exists")
    shutil.copytree(src, dst)
    for f in dst.rglob("*"):
        if f.is_file() and f.suffix in {".md", ".py", ".yaml"}:
            f.write_text(f.read_text().replace("example-model", dst.name))
    print("created", dst, "- fill requirements.yaml with measured numbers, then model.py")


def main(argv=None):
    p = argparse.ArgumentParser(prog="gendesign", description="AI + generative design: requirements, analysis, search, review, owner go, test feedback")
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

    an = sub.add_parser("analyze", help="requirements -> design targets -> concept (before any geometry)")
    an.add_argument("model", help="models/<name>/")
    an.set_defaults(func=_cmd_analyze)

    r = sub.add_parser("round", help="run one search round of a model and write iterations/NN/")
    r.add_argument("model", help="models/<name>/ (has requirements.yaml and model.py)")
    r.add_argument("--design", default=None, help="designs/<name>/ to write into (default from model.py)")
    r.add_argument("--pop", type=int, default=12)
    r.add_argument("--gens", type=int, default=4)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--picks", type=int, default=3)
    r.add_argument("--from", dest="from_round", default=None, help="seed the search with an earlier round (iterations/NN) or a design.json")
    r.add_argument("--note", default="", help="what changed and why (goes into decisions.md)")
    r.add_argument("--no-export", action="store_true", help="skip meshing the picks")
    r.set_defaults(func=_cmd_round)

    st = sub.add_parser("status", help="designs, rounds, review state, approvals and tests of a model")
    st.add_argument("model")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=_cmd_status)

    gn = sub.add_parser("generate", help="rebuild a pick or saved design to print files through the model")
    gn.add_argument("model")
    gn.add_argument("source", help="a pick folder, its params.json, or a design.json")
    gn.add_argument("-o", "--out", default=None)
    gn.set_defaults(func=_cmd_generate)

    rp = sub.add_parser("report", help="write models/<name>/REPORT.md for review")
    rp.add_argument("model")
    rp.set_defaults(func=_cmd_report)

    ap = sub.add_parser("approve", help="owner only: record the go for one pick of a round")
    ap.add_argument("iteration", help="designs/<name>/iterations/NN")
    ap.add_argument("pick")
    ap.add_argument("--note", default="")
    ap.set_defaults(func=_cmd_approve)

    fb = sub.add_parser("feedback", help="parse calibrate:/requirement: lines of a test.md into feedback.json")
    fb.add_argument("test_md")
    fb.set_defaults(func=_cmd_feedback)

    nw = sub.add_parser("new", help="start a model folder from templates/model")
    nw.add_argument("dest", help="models/<name>")
    nw.set_defaults(func=_cmd_new)

    args = p.parse_args(argv)
    if getattr(args, "quick", False) and args.cmd == "topopt2d":
        args.nelx, args.nely, args.niter = 32, 12, 20
    if getattr(args, "quick", False) and args.cmd == "topopt3d":
        args.nelx, args.nely, args.nelz, args.niter = 10, 5, 5, 8
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
