#!/usr/bin/env python3
"""Draw how a hair-catcher pick was generated, step by step, from its real data.

    python models/hair-catcher/docs/explain.py                       # round 01 knee
    python models/hair-catcher/docs/explain.py --round 02 --pick knee

Writes docs/how-it-is-generated.png: analysis targets, the generator's
stages (points, relaxation, Voronoi, ribs, pebble holes, 3-D solid), and the
search front that chose the pick.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent
sys.path.insert(0, str(MODEL))

import model as M  # noqa: E402

PL, INK, ACC, GR = "#e9e4da", "#3b4a5a", "#c0603a", "#555555"


def stages(p):
    """Re-run the generator with snapshots: raw points, relaxed points, cells, insets, holes."""
    from scipy.spatial import Voronoi
    from shapely.geometry import Point, Polygon

    RB = M.RB
    rng = np.random.default_rng(p.seed)
    pts = []
    for _ in range(6000):  # same draw order as model.seeds
        r = (RB - 1) * np.sqrt(rng.random())
        t = rng.random() * 2 * np.pi
        q = np.array([r * np.cos(t), r * np.sin(t)])
        sp = p.spacing / np.sqrt(M._density(q[None], p.grade)[0])
        if all(np.hypot(*(q - o)) >= sp for o in pts):
            pts.append(q)
    raw = np.array(pts)
    final = M.seeds(p)
    vor = Voronoi(np.vstack([final, M._mirror(final), M._ghosts(RB + 14, 24)]))
    bore = Point(0, 0).buffer(RB - p.edge_rib + p.rib / 2, quad_segs=128)
    cells, insets = [], []
    for i in range(len(final)):
        reg = vor.regions[vor.point_region[i]]
        if -1 in reg or not reg:
            continue
        cell = Polygon(vor.vertices[reg])
        cells.append(cell)
        insets.append(cell.intersection(bore).buffer(-p.rib / 2, join_style="mitre"))
    holes = M.PebblePlate().build(p)["holes"]
    return raw, final, cells, insets, holes


def draw(round_id="01", pick="knee", out=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch
    from matplotlib.patches import Polygon as MP
    from PIL import Image
    from shapely.geometry import Point

    it = MODEL / "designs" / "pebble-plate" / "iterations" / round_id
    pd = it / "picks" / pick
    p = M.PlateParams(**json.loads((pd / "params.json").read_text()))
    stats = json.loads((pd / "stats.json").read_text())["metrics"]
    a = json.loads((MODEL / "analysis.json").read_text())
    tg = {k: v["value"] for k, v in a["targets"].items()}
    raw, final, cells, insets, holes = stages(p)
    RB = M.RB

    fig = plt.figure(figsize=(15, 16), dpi=110, facecolor="white")
    gs = fig.add_gridspec(4, 3, height_ratios=[0.5, 1, 1, 0.95], hspace=0.55, wspace=0.12)

    def head(ax, t):
        ax.set_title(t, fontsize=12.5, loc="left", fontweight="bold", color="#222", pad=8)

    def cap(ax, s):
        ax.text(0.0, -0.04, s, transform=ax.transAxes, fontsize=9, color=GR, va="top")

    def disk(ax, t, s):
        ax.add_patch(Circle((0, 0), M.FL_R, color=PL, zorder=0))
        ax.add_patch(Circle((0, 0), RB, fill=False, ls="--", lw=0.7, color="#a39b8c"))
        ax.set_xlim(-24, 24)
        ax.set_ylim(-24, 24)
        ax.set_aspect("equal")
        ax.axis("off")
        head(ax, t)
        cap(ax, s)

    # 0 analysis
    ax = fig.add_subplot(gs[0, :])
    ax.axis("off")
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 10.5)
    head(ax, "0  Analysis first: requirements → design targets → concept (no geometry yet)")
    boxes = [
        ("Drain like smooth v2", "78 cm³/s at a 5 mm head\nQ = Cd·A·√(2gh)",
         f"open area ≥ {tg['open_area_min_mm2']} mm²\n({100 * tg['open_fraction_min']:.0f}% of the bore)"),
        ("Water must not hang", "capillary length\n√(σ/ρg) = 2.7 mm", f"holes ≥ {tg['hole_min_mm']} mm"),
        ("30 N push, 10 N finger", "clamped circular plate\nRoark, D × solid²", f"plate ≥ {tg['plate_t_min_mm']} mm\n(2.2 used)"),
        ("Concept screen", "flat / cone / two-level\ndrainage binds", f"{a['chosen'].upper()}\n(nothing over air)"),
    ]
    for i, (req, how, tgt) in enumerate(boxes):
        x = 1 + i * 25
        ax.add_patch(FancyBboxPatch((x, 0), 23, 10, boxstyle="round,pad=0.2,rounding_size=1", fc="#f6f3ee", ec="#d8d0c2"))
        ax.text(x + 1, 9.2, req, fontsize=10.5, fontweight="bold", color="#222", va="top")
        ax.text(x + 1, 7.0, how, fontsize=9, color=GR, va="top")
        ax.text(x + 1, 3.4, tgt, fontsize=10, color=ACC, fontweight="bold", va="top")

    # 1-5 generator
    ax = fig.add_subplot(gs[1, 0])
    disk(ax, "1  Scatter points", f"Random points in the 32 mm bore, ≥ {p.spacing:.1f} mm apart.\nGenes: spacing; seed ({p.seed}) picks the pattern.")
    ax.scatter(raw[:, 0], raw[:, 1], s=26, color=ACC, zorder=3)

    ax = fig.add_subplot(gs[1, 1])
    disk(ax, "2  Relax (Lloyd ×12)", "Each point moves to the centre of its region,\nso cells even out. Hollow dots: mirror images\nacross the bore wall, so edge cells end at the wall.")
    ax.scatter(raw[:, 0], raw[:, 1], s=12, color="#cfc6b8", zorder=2)
    ax.scatter(final[:, 0], final[:, 1], s=26, color=ACC, zorder=3)
    mir = M._mirror(final)
    ax.scatter(mir[:, 0], mir[:, 1], s=12, facecolors="none", edgecolors=ACC, lw=0.8, zorder=3)

    ax = fig.add_subplot(gs[1, 2])
    disk(ax, "3  Voronoi cells", "Each point owns the area nearer to it\nthan to any other point. Cells become holes.")
    for c in cells:
        cc = c.intersection(Point(0, 0).buffer(RB))
        if cc.geom_type == "Polygon":
            ax.add_patch(MP(np.asarray(cc.exterior.coords), fill=False, ec=INK, lw=1.2, zorder=2))
    ax.scatter(final[:, 0], final[:, 1], s=14, color=ACC, zorder=3)

    ax = fig.add_subplot(gs[2, 0])
    disk(ax, "4  Inset = ribs", f"Shrink each cell by half a rib: {p.rib:.2f} mm ribs,\n{p.edge_rib:.2f} mm rim at the wall. Genes: rib, edge_rib.")
    for g in insets:
        for gg in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            if not gg.is_empty:
                ax.add_patch(MP(np.asarray(gg.exterior.coords), color="#8796a5", zorder=2))

    ax = fig.add_subplot(gs[2, 1])
    disk(ax, "5  Pebble holes",
         f"Shrink by R, grow back by R (R = {p.round_frac:.2f} × inradius):\n"
         f"every corner ≥ {stats.get('tightest_corner_mm', 1.29)} mm. Holes < {p.min_inscribed} mm stay solid.\n"
         f"Result: {len(holes)} holes, {stats['min_ball_mm']}–{stats['max_ball_mm']} mm. Gene: round_frac.")
    for h in holes:
        ax.add_patch(MP(np.asarray(h.exterior.coords), color=INK, zorder=2))

    ax = fig.add_subplot(gs[2, 2])
    ax.axis("off")
    sheet = pd / "preview-3d.png"
    if sheet.exists():
        im = Image.open(sheet)
        s = im.size[0] // 2
        ax.imshow(im.crop((s, 30, im.size[0], 30 + s)).crop((30, 170, s - 10, s - 150)))
    head(ax, "6  Signed-distance solid")
    cap(ax, "Exact distance to the hole outlines gives a 2.2 mm\nplate, rounded rims and a 0.8 mm fillet into the\n"
            "collar; flange, collar, lead-in stay exact. Marching\ncubes → watertight mesh, printed top-face-down.")

    # 7 search
    ax = fig.add_subplot(gs[3, 0:2])
    labels = {"00": ("#d6cfc3", "round 00 (before the analysis existed)", 22),
              "01": ("#3b4a5a", "round 01 (analysis-driven)", 38),
              "02": ("#9fb3c4", "round 02 (cold restart, 2× larger)", 22)}
    for rdir in sorted((MODEL / "designs" / "pebble-plate" / "iterations").iterdir()):
        rec = rdir / "round.json"
        if not rec.exists():
            continue
        col, lab, sz = labels.get(rdir.name, ("#bbbbbb", f"round {rdir.name}", 22))
        if rdir.name == round_id:
            col, sz = "#3b4a5a", 38
        F = np.array([t["objectives"] for t in json.loads(rec.read_text())["front"]])
        ax.scatter(F[:, 0], F[:, 1], s=sz, color=col, label=lab, zorder=3 if rdir.name == round_id else 2)
    k = json.loads((it / "round.json").read_text())["picks"][pick]["objectives"]
    import yaml

    flow_min = float(yaml.safe_load((MODEL / "requirements.yaml").read_text())["function"]["drain_flow_min_cm3_s"])
    ax.scatter([k[0]], [k[1]], s=200, facecolors="none", edgecolors=ACC, lw=2.2, zorder=4)
    ax.annotate(f"round {round_id} {pick}: {len(holes)} holes, {k[0]:.0f} cm³/s", (k[0], k[1]), xytext=(66, 4.1),
                fontsize=10, color=ACC, arrowprops=dict(arrowstyle="->", color=ACC))
    ax.axvspan(60, flow_min, color="#f3e3dc", alpha=0.6, zorder=0)
    ax.axvline(flow_min, color=ACC, ls=":", lw=1.2)
    ax.text(64, 2.0, f"fails the flow target\n(< {tg['open_area_min_mm2']} mm² open)", fontsize=9, color=ACC)
    ax.set_xlim(62, 86.5)
    ax.set_xlabel("drainage, cm³/s  →  more water through", fontsize=10)
    ax.set_ylabel("capture  →  smaller largest hole", fontsize=10)
    head(ax, "7  Search: NSGA-II evolves the 6 genes, keeps the unbeaten designs")
    ax.legend(fontsize=9, frameon=False, loc="lower right", bbox_to_anchor=(1, 0.08))
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)

    ax = fig.add_subplot(gs[3, 2])
    ax.axis("off")
    head(ax, "Why it looks like this")
    rows = [
        (f"~{np.median([stats['min_ball_mm'], stats['max_ball_mm']]):.0f} mm holes",
         f"Flow needs ≥ {tg['open_area_min_mm2']} mm² through ≥ {tg['rib_min_mm']} mm ribs;\ncapture keeps holes as small as that allows."),
        ("Even sizes", f"grade {p.grade:.2f}: capture punishes one big hole\namong small ones."),
        ("Just rounded", f"round_frac {p.round_frac:.2f}: corners ≥ {stats.get('tightest_corner_mm', 1.29)} mm, already past\n"
                         "the 0.5 mm hair hook and 0.7 mm water wedge.\nMore rounding only loses open area."),
        ("Flat, flush", "The analysis chose a flat plate: meets every\ntarget and prints with nothing over air."),
    ]
    y = 0.97
    for t, b in rows:
        ax.text(0, y, t, fontsize=10.5, fontweight="bold", color=ACC, va="top", transform=ax.transAxes)
        ax.text(0, y - 0.075, b, fontsize=9.2, color="#333", va="top", transform=ax.transAxes)
        y -= 0.075 + 0.065 * b.count("\n") + 0.13

    fig.suptitle("How the hair catcher is generated", fontsize=17, x=0.06, ha="left", y=0.995, color="#111", fontweight="bold")
    fig.text(0.06, 0.968, f"Requirements → analysis → generator → search.   Round {round_id} {pick} genes: seed {p.seed}, "
             f"spacing {p.spacing}, grade {p.grade}, rib {p.rib}, edge_rib {p.edge_rib}, round_frac {p.round_frac}",
             fontsize=10, color=GR)
    out = Path(out or HERE / "how-it-is-generated.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--round", default="01")
    ap.add_argument("--pick", default="knee")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()
    print(draw(args.round, args.pick, args.out))
