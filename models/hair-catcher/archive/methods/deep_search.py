#!/usr/bin/env python3
"""Basin guard v3 — deeper/steeper basket search (depth free, side holes).

Generational search like v2 (optimize.py), but the genome is a revolved
basket: press-fit collar (fixed fit) -> 45° shoulder (continues the lead-in)
-> side wall (lean alpha) with staggered rounded-rhombus side holes ->
conical floor (beta from horizontal) with vertical round holes.
Runs: (1) main search at the v2 ball 8.6 mm (frames saved),
      (2) same search at the 12 mm cap, (3) a depth sweep.
"""
from __future__ import annotations
import csv, json, math, sys, time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly, Circle
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deep_geom as D
from grid_seeds import grid_seeds

OUT = Path(__file__).resolve().parent
IT = OUT / "iterations_deep"
IT.mkdir(exist_ok=True)

BOUNDS = dict(
    Lc=(5.0, 9.31), t=(1.6, 2.4), Ro=(10.0, D.R_CLEAR), alpha=(0.0, D.MAX_ALPHA),
    beta=(D.MIN_BETA, D.MAX_BETA), h_slack=(0.0, 2.0), d_f=(5.0, 12.0), rho1=(0.0, 1.0),
    rho2=(0.0, 1.0), rot1=(0.0, 1.0), rot2=(0.0, 1.0), a=(2.5, 6.0), b=(2.5, 9.0), gam=(30.0, 45.0),
    rc=(0.6, 0.6), nrows=(0, 5), dN=(0, 4), v_slack=(0.0, 2.0),
)
INT = {"nrows", "dN"}
BOOL = {"center", "ring2"}


def clip(g, ball):
    for k, (lo, hi) in BOUNDS.items():
        if k in ("d_f",):
            hi = min(hi, ball)
        g[k] = float(np.clip(g[k], lo, hi))
        if k in INT:
            g[k] = int(round(g[k]))
    g["a"] = min(g["a"], ball / 2)
    bmin = g["a"] / math.tan(math.radians(g["gam"]))
    g["b"] = float(np.clip(g["b"], bmin, D.COIN_MAX_LEN / 2))
    return g


def random_genome(rng, ball):
    g = {k: rng.uniform(lo, hi) for k, (lo, hi) in BOUNDS.items()}
    g["center"] = bool(rng.random() < 0.7)
    g["ring2"] = bool(rng.random() < 0.3)
    g["N"] = 0; g["v"] = 0.0
    g["stagger"] = bool(rng.random() < 0.6)
    g["a"] = rng.uniform(2.8, ball / 2)
    return clip(g, ball)


def mutate(g, rng, ball, scale=0.12):
    c = dict(g)
    for k, (lo, hi) in BOUNDS.items():
        if rng.random() < 0.35:
            c[k] = c[k] + rng.normal(0, scale * (hi - lo + 1e-9))
    if rng.random() < 0.08:
        c["center"] = not c["center"]
    if rng.random() < 0.08:
        c["ring2"] = not c["ring2"]
    if rng.random() < 0.08:
        c["stagger"] = not c["stagger"]
    if rng.random() < 0.2:
        c["nrows"] = c["nrows"] + int(rng.choice([-1, 1]))
    return clip(c, ball)


def crossover(p, q, rng):
    return {k: (p[k] if rng.random() < 0.5 else q[k]) for k in p}


def local_search(g, ball, max_depth, rng, rounds=3, log=None, tag="", gen=0):
    """Memetic step: coordinate pattern search on the current best."""
    m, _ = D.evaluate(dict(g), ball, max_depth)
    best_s, best_g, best_m = m["score"], dict(g), m
    for r in range(rounds):
        improved = False
        for k, (lo, hi) in BOUNDS.items():
            if lo == hi:
                continue
            steps = [-1, 1] if k in INT else [-(hi - lo) * f for f in (0.08, 0.02, 0.005)] + \
                                               [(hi - lo) * f for f in (0.08, 0.02, 0.005)]
            for st in steps:
                c = dict(best_g); c[k] = c[k] + st
                c = clip(c, ball)
                mm, _ = D.evaluate(c, ball, max_depth)
                if log is not None:
                    log.append(dict(gen=gen, run=tag, **mm))
                if mm["score"] > best_s + 1e-7:
                    best_s, best_g, best_m = mm["score"], c, mm; improved = True
        for k in ("center", "ring2", "stagger"):
            c = dict(best_g); c[k] = not c[k]
            mm, _ = D.evaluate(c, ball, max_depth)
            if mm["score"] > best_s + 1e-7:
                best_s, best_g, best_m = mm["score"], c, mm; improved = True
        if not improved:
            break
    return best_s, best_g, best_m


def run_ga(ball, max_depth, seed, pop=96, gens=24, n_seed=1500, tag="", log=None):
    rng = np.random.default_rng(seed)
    allrows, best_hist = [], []
    cands = [random_genome(rng, ball) for _ in range(n_seed)] + grid_seeds(ball)
    scored = []
    for g in cands:
        m, L = D.evaluate(g, ball, max_depth)
        scored.append((m["score"], g, m))
        if log is not None:
            log.append(dict(gen=0, run=tag, **m))
    scored.sort(key=lambda x: -x[0])
    best_hist.append(scored[0])
    for gen in range(1, gens + 1):
        elite = scored[:8]
        parents = scored[:pop]
        kids = [e[1] for e in elite]
        while len(kids) < pop:
            i, j = rng.integers(0, len(parents), 2)
            p = parents[min(i, j)][1]
            if rng.random() < 0.5:
                q = parents[int(rng.integers(0, len(parents)))][1]
                child = crossover(p, q, rng)
            else:
                child = dict(p)
            kids.append(mutate(child, rng, ball, scale=0.12 * (1 - 0.6 * gen / gens)))
        new = []
        for g in kids:
            m, L = D.evaluate(g, ball, max_depth)
            new.append((m["score"], g, m))
            if log is not None:
                log.append(dict(gen=gen, run=tag, **m))
        scored = sorted(new + scored[:8], key=lambda x: -x[0])
        # dedupe
        seen, uniq = set(), []
        for s in scored:
            key = round(s[0], 5)
            if key in seen:
                continue
            seen.add(key); uniq.append(s)
        scored = uniq
        ls = local_search(scored[0][1], ball, max_depth, rng, log=log, tag=tag, gen=gen)
        if ls[0] > scored[0][0]:
            scored.insert(0, ls)
        best_hist.append(scored[0])
    return best_hist, scored


# ---------------------------------------------------------------- drawing
def _section_polys(g, L):
    P = L["P"]
    body = [P["O5"], P["O4"], P["O3"], P["O2"], P["O1"], (D.R_FLANGE, 0),
            (D.R_FLANGE, D.FLANGE_T), (D.R_IN, D.FLANGE_T), P["Ij"], P["I3"], P["I4"], P["I5"]]
    return np.array(body, float)


def draw_frame(g, m, L, path, title):
    fig = plt.figure(figsize=(15, 6.6), dpi=110)
    fig.patch.set_facecolor("#F7F4EF")
    # --- section
    ax = fig.add_axes([0.03, 0.10, 0.30, 0.78])
    body = _section_polys(g, L)
    for sgn in (1, -1):
        pts = body.copy(); pts[:, 0] *= sgn
        ax.add_patch(MPoly(pts, closed=True, fc="#D9D3C7", ec="#3B3B3B", lw=1.0))
    # drain walls (assumed)
    for sgn in (1, -1):
        ax.add_patch(MPoly([(sgn * D.R_LOC, 0), (sgn * 26, 0), (sgn * 26, -D.KNOWN_BORE_DEPTH),
                            (sgn * D.PIPE_ID / 2, -D.KNOWN_BORE_DEPTH), (sgn * D.PIPE_ID / 2, -40),
                            (sgn * 26, -40)][::1] if False else
                           [(sgn * D.R_LOC, 0), (sgn * 26, 0), (sgn * 26, -40), (sgn * D.PIPE_ID / 2, -40),
                            (sgn * D.PIPE_ID / 2, -D.KNOWN_BORE_DEPTH), (sgn * D.R_LOC, -D.KNOWN_BORE_DEPTH)],
                           closed=True, fc="#B9C0C8", ec="none", alpha=0.45))
    P = L["P"]
    for th, zc in L["side"]:
        if abs(math.cos(th)) > 0.97:
            sgn = 1 if math.cos(th) > 0 else -1
            ax.add_patch(MPoly([(sgn * (P["I3"][0] - 1), zc - g["b"]), (sgn * (P["O3"][0] + .5), zc - g["b"]),
                                (sgn * (P["O3"][0] + .5), zc + g["b"]), (sgn * (P["I3"][0] - 1), zc + g["b"])],
                               fc="#F7F4EF", ec="none", alpha=0.9))
    for x, y, r in L["floor"]:
        if abs(y) < 1e-6:
            ax.add_patch(MPoly([(x - r, P["O5"][1] - 1), (x + r, P["O5"][1] - 1), (x + r, 0), (x - r, 0)],
                               fc="#F7F4EF", ec="none", alpha=0.0))
    ax.axhline(D.FLANGE_T, color="#888", lw=0.6, ls=":")
    ax.set_xlim(-27, 27); ax.set_ylim(-40, 6); ax.set_aspect("equal")
    ax.set_title("half-section (grey = assumed drain, Ø32 below 10.2 mm)", fontsize=9)
    ax.tick_params(labelsize=7)
    # --- top view
    ax2 = fig.add_axes([0.34, 0.10, 0.26, 0.78])
    ax2.add_patch(Circle((0, 0), D.R_FLANGE, fc="#E6E1D7", ec="#555"))
    ax2.add_patch(Circle((0, 0), D.R_IN, fc="#D9D3C7", ec="#555"))
    ax2.add_patch(Circle((0, 0), P["I4"][0], fc="#CFC8BA", ec="#777", ls="--"))
    for x, y, r in L["floor"]:
        ax2.add_patch(Circle((x, y), r, fc="#2E3238", ec="none"))
    for th, zc in L["side"]:
        rr = D.r_inner_side(P, zc)
        ax2.plot([rr * math.cos(th), D.r_outer_side(P, zc) * math.cos(th)],
                 [rr * math.sin(th), D.r_outer_side(P, zc) * math.sin(th)], color="#2E3238", lw=3)
    ax2.set_xlim(-24, 24); ax2.set_ylim(-24, 24); ax2.set_aspect("equal"); ax2.axis("off")
    ax2.set_title("top: floor holes (black), side holes (ticks)", fontsize=9)
    # --- unrolled side wall
    ax3 = fig.add_axes([0.62, 0.40, 0.36, 0.48])
    if L["side"]:
        ol = D.hole_outline(g["a"], g["b"], g["gam"], g["rc"], 6)
        zc0 = [zc for _, zc in L["side"]]
        for th, zc in L["side"]:
            rr = D.r_inner_side(P, zc)
            for shift in (0, 2 * math.pi, -2 * math.pi):
                cx = (th + shift) * rr
                ax3.add_patch(MPoly(np.c_[cx + ol[:, 0], zc + ol[:, 1]], fc="#2E3238", ec="none"))
        circ = 2 * math.pi * D.r_inner_side(P, max(zc0))
        ax3.set_xlim(-2, circ + 2)
        ax3.set_ylim(min(zc0) - g["b"] - 3, max(zc0) + g["b"] + 3)
        ax3.set_aspect("equal")
    ax3.set_title("side wall, unrolled at inner surface (mm)", fontsize=9)
    ax3.tick_params(labelsize=7)
    txt = (f"open {m['open_mm2']:.0f} mm²  ({m['open_area_pct']:.1f}% of Ø32 disc)   "
           f"floor {m['floor_mm2']:.0f} / side {m['side_mm2']:.0f} mm²\n"
           f"max ball {m['max_ball_mm']:.2f} mm   min strut {m['min_strut_mm']} mm   depth {m['depth_mm']:.1f} mm\n"
           f"holes: {m['n_floor']} floor Ø{m['floor_hole_d']:.2f} + {m['n_side']} side ({m['rows']} rows × {m['N']})  "
           f"side hole {2*m['a']:.1f}×{2*m['b']:.1f} roof {m['gam']:.0f}°\n"
           f"wall lean {m['alpha']:.1f}°, floor cone {m['beta']:.1f}°, t {m['t']:.2f}, collar {m['Lc']:.2f}   "
           f"est. mass {m['mass_g_est']:.1f} g\n"
           f"drain est. (5 mm water): clean {m['q_clean_lpm']:.1f} L/min, floor matted {m['q_floor_blocked_lpm']:.1f} L/min"
           f"   score {m['score']:.3f}  {'OK' if m['feasible'] else 'INFEASIBLE '+m['reasons']}")
    fig.text(0.62, 0.06, txt, fontsize=8.6, family="monospace", va="bottom")
    fig.suptitle(title, fontsize=13, x=0.03, ha="left")
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def contact_sheet(paths, out, cols=4):
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = ims[0].size
    cw = 560; ch = int(cw * h / w)
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * cw + 16, rows * ch + 16), (244, 240, 234))
    for i, im in enumerate(ims):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((cw - 8, ch - 8), Image.Resampling.LANCZOS), (8 + c * cw, 8 + r * ch))
    sheet.save(out)


def main():
    t0 = time.time()
    log = []
    V2 = D.v2_reference()
    # ---- main run at the v2 ball (8.6 mm) ----
    hist86, final86 = run_ga(8.6, 35.0, 20261114, tag="ball8.6", log=log)
    rows = []
    frames = []
    for gi, (s, g, m) in enumerate(hist86):
        m2, L = D.evaluate(g, 8.6, 35.0)
        p = IT / f"iter_{gi:02d}.png"
        draw_frame(g, m2, L, p, f"v3 deep basket — generation {gi:02d} best (ball ≤ 8.6 mm, depth ≤ 35 mm)")
        frames.append(p)
        rows.append(dict(gen=gi, kind="generation_best", run="ball8.6", **m2))
    contact_sheet(frames, IT / "contact-sheet.png")
    ims = [Image.open(p).convert("P", palette=Image.Palette.ADAPTIVE, colors=240) for p in frames]
    ims[0].save(IT / "evolution.gif", save_all=True, append_images=ims[1:], duration=700, loop=0)
    best86 = hist86[-1]
    # ---- 12 mm cap ----
    hist12, _ = run_ga(12.0, 35.0, 20261115, tag="ball12", log=log)
    for gi, (s, g, m) in enumerate(hist12):
        rows.append(dict(gen=gi, kind="generation_best", run="ball12", **m))
    best12 = hist12[-1]
    m12, L12 = D.evaluate(best12[1], 12.0, 35.0)
    draw_frame(best12[1], m12, L12, IT / "best_cap12.png", "v3 deep basket — best at the 12 mm cap (not built)")
    # ---- depth sweep ----
    sweep = []
    for ball in (8.6, 12.0):
        for md in (15.0, 18.0, 21.0, 24.0, 26.0, 28.0, 30.0, 32.0, 35.0):
            h, _ = run_ga(ball, md, 777 + int(md * 10) + int(ball * 1000), pop=64, gens=18, n_seed=800,
                          tag=f"sweep_b{ball}_d{md}", log=log)
            s, g, m = h[-1]
            sweep.append(dict(ball_limit=ball, max_depth=md, **m, genome=json.dumps(g)))
            print(f"sweep ball {ball} depth<={md}: feas {m['feasible']} open {m['open_mm2']} mm2 depth {m['depth_mm']}", flush=True)
    # ---- CSVs ----
    keys = list(rows[0].keys())
    with open(IT / "iterations.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    lkeys = list(log[0].keys())
    with open(IT / "all_candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=lkeys); w.writeheader(); w.writerows(log)
    skeys = list(sweep[0].keys())
    with open(IT / "depth_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=skeys); w.writeheader(); w.writerows(sweep)
    # ---- evolution chart ----
    fig, ax = plt.subplots(2, 2, figsize=(12, 8.4), dpi=130)
    fig.patch.set_facecolor("#F7F4EF")
    r86 = [r for r in rows if r["run"] == "ball8.6"]; r12 = [r for r in rows if r["run"] == "ball12"]
    a = ax[0, 0]
    a.plot([r["gen"] for r in r86], [r["open_mm2"] for r in r86], "-o", color="#1F6B4A", label="ball ≤ 8.6 total")
    a.plot([r["gen"] for r in r86], [r["side_mm2"] for r in r86], "--", color="#1F6B4A", alpha=.6, label="ball ≤ 8.6 side only")
    a.plot([r["gen"] for r in r12], [r["open_mm2"] for r in r12], "-s", color="#B5562B", label="ball ≤ 12 total")
    a.axhline(V2["open_mm2"], color="#555", ls=":", label=f"v2 {V2['open_mm2']:.0f} mm²")
    a.set_title("Best open area by generation"); a.set_xlabel("generation"); a.set_ylabel("open mm²"); a.legend(fontsize=8)
    a = ax[0, 1]
    a.plot([r["gen"] for r in r86], [r["depth_mm"] for r in r86], "-o", color="#1F6B4A", label="ball ≤ 8.6")
    a.plot([r["gen"] for r in r12], [r["depth_mm"] for r in r12], "-s", color="#B5562B", label="ball ≤ 12")
    a.axhline(10.21, color="#555", ls=":", label="v2 10.21 mm")
    a.set_title("Depth into drain of the generation best"); a.set_xlabel("generation"); a.set_ylabel("mm"); a.legend(fontsize=8)
    a = ax[1, 0]
    feas = [r for r in log if r["feasible"] and r["run"] in ("ball8.6", "ball12")]
    for run, col in (("ball8.6", "#1F6B4A"), ("ball12", "#B5562B")):
        pts = [(r["depth_mm"], r["open_mm2"]) for r in feas if r["run"] == run]
        if pts:
            a.scatter(*zip(*pts), s=5, alpha=.25, color=col, label=f"feasible {run}")
    a.scatter([10.21], [V2["open_mm2"]], marker="*", s=180, color="k", label="v2")
    a.set_title("All feasible candidates"); a.set_xlabel("depth mm"); a.set_ylabel("open mm²"); a.legend(fontsize=8)
    a = ax[1, 1]
    for ball, col in ((8.6, "#1F6B4A"), (12.0, "#B5562B")):
        ss = [s for s in sweep if s["ball_limit"] == ball and s["feasible"]]
        a.plot([s["max_depth"] for s in ss], [s["open_mm2"] for s in ss], "-o", color=col, label=f"ball ≤ {ball} total")
        a.plot([s["max_depth"] for s in ss], [s["q_floor_blocked_lpm"] for s in ss], "--", color=col, alpha=.7,
               label=f"ball ≤ {ball}: L/min w/ floor matted")
    a.scatter([10.21], [V2["open_mm2"]], marker="*", s=180, color="k", label="v2 open mm²")
    a.set_title("Depth sweep: best open area for each depth limit"); a.set_xlabel("max depth allowed (mm)")
    a.set_ylabel("open mm²  /  L/min"); a.legend(fontsize=7)
    for a in ax.flat:
        a.set_facecolor("#FBFAF8"); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(IT / "evolution-chart.png", facecolor=fig.get_facecolor()); plt.close(fig)
    res = dict(best86=dict(genome=best86[1], metrics=D.evaluate(best86[1], 8.6, 35.0)[0]),
               best12=dict(genome=best12[1], metrics=m12), v2=V2, sweep=sweep,
               n_eval=len(log), elapsed_s=round(time.time() - t0, 1))
    (IT / "search-result.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: res[k] for k in ("best86", "best12", "v2", "n_eval", "elapsed_s")}, indent=1, default=float))


if __name__ == "__main__":
    main()
