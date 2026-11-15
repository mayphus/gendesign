"""Short NSGA-II rounds for the hair-catcher grate.

The code searches. An AI review of the renders and the score table
decides what changes in the next round. Each round is one folder
under designs/<name>/iterations/NN/, with decisions.md.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from gen_grate import (
    BOUNDS,
    GENE_NAMES,
    decode,
    evaluate_design,
    evaluate_vector,
    fit_from_requirements,
    render_views,
    save_plan_png,
    save_stl_pair,
    smooth_v2_reference,
)


def _knee(front):
    """Feasible point closest to the normalized utopia, or the least-violating point."""
    feas = [t for t in front if t.info.get("feasible")]
    pool = feas or list(front)
    if not pool:
        return None
    keys = ("flow_mm3_s", "capture_mm", "stiffness_N_per_mm", "volume_mm3")
    cols = []
    for k in keys:
        col = np.array([float(t.info.get(k, 0.0) or 0.0) for t in pool], dtype=float)
        # Volume is minimized; flip it so 1 is best.
        if k == "volume_mm3":
            col = -col
        lo, hi = float(np.min(col)), float(np.max(col))
        cols.append((col - lo) / (hi - lo) if hi - lo > 1e-9 else np.ones_like(col))
    norm = np.vstack(cols).T
    dist = np.linalg.norm(norm - 1.0, axis=1)
    return pool[int(np.argmin(dist))]


def _unique_picks(front):
    """Up to four distinct feasible designs: open, snag, stiff, knee."""
    feas = [t for t in front if t.info.get("feasible")]
    if not feas:
        feas = list(front)
    if not feas:
        return []

    def metric(t, key):
        v = t.info.get(key)
        return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else -1e18

    best_flow = max(metric(t, "flow_mm3_s") for t in feas)
    picks = []

    def take(name, t):
        if t is None:
            return
        if any(np.allclose(t.x, p["trial"].x) for p in picks):
            return
        picks.append({"name": name, "trial": t})

    take("open-drain", max(feas, key=lambda t: metric(t, "flow_mm3_s")))
    drainers = [t for t in feas if metric(t, "flow_mm3_s") >= 0.45 * best_flow] or feas
    take("hair-snag", max(drainers, key=lambda t: metric(t, "capture_mm")))
    take("stiff", max(drainers, key=lambda t: metric(t, "stiffness_N_per_mm")))
    take("knee", _knee(feas))
    # Fill with the next-most-crowded distinct points if the front collapsed.
    ranked = sorted(feas, key=lambda t: metric(t, "flow_mm3_s"), reverse=True)
    for t in ranked:
        if len(picks) >= 4:
            break
        take(f"alt-{len(picks)}", t)
    return picks[:4]


def _caption(info):
    ball = info.get("max_ball_mm")
    flow = info.get("flow_cm3_s")
    disp = info.get("fingertip_disp_mm")
    ball_s = f"{ball:.1f}" if isinstance(ball, float) else "?"
    flow_s = f"{flow:.1f}" if isinstance(flow, float) else "?"
    disp_s = f"{disp:.2f}" if isinstance(disp, float) else "—"
    return f"ball {ball_s} mm   flow {flow_s} cm³/s   fingertip {disp_s} mm"


def _hypervolume(front):
    """2-D hypervolume of feasible (flow, capture), normalized by fixed scales."""
    pts = []
    for t in front:
        if not t.info.get("feasible"):
            continue
        f = float(t.info.get("flow_cm3_s") or 0.0) / 80.0
        c = float(t.info.get("capture_mm") or 0.0) / 12.0
        if f > 0 and c > 0:
            pts.append((min(f, 1.5), min(c, 1.5)))
    if not pts:
        return 0.0
    ordered = sorted(pts, key=lambda p: -p[0])
    hv = 0.0
    best_y = 0.0
    prev_x = None
    for x, y in ordered:
        if y > best_y:
            if prev_x is not None:
                hv += (prev_x - x) * best_y
            prev_x = x
            best_y = y
    if prev_x is not None:
        hv += prev_x * best_y
    return float(hv)


def run_round(req: dict, out: Path, *, pop=10, gens=3, seed=7, pitch=0.18, round_index="00") -> dict:
    """One short search. Writes iterations/<round>/ and returns the summary."""
    from gendesign.search import nsga2

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fit = fit_from_requirements(req)
    round_dir = out / "iterations" / round_index
    gen_dir = round_dir / "generations"
    gen_dir.mkdir(parents=True, exist_ok=True)
    gen_rows = []

    def callback(gen, front, population):
        knee = _knee(front) or (population[0] if population else None)
        row = {
            "gen": gen,
            "n_front": len(front),
            "n_feasible_front": sum(1 for t in front if t.info.get("feasible")),
            "hypervolume": _hypervolume(front),
        }
        if knee is not None:
            row.update({k: knee.info.get(k) for k in (
                "flow_cm3_s", "capture_mm", "max_ball_mm", "open_area_pct",
                "fingertip_disp_mm", "volume_mm3", "n_openings", "feasible",
            )})
            try:
                ev = evaluate_design(decode(knee.x, fit), fit, pitch=pitch)
                png = gen_dir / f"{gen:02d}.png"
                save_plan_png(png, ev["holes"], fit, ev["design"], f"gen {gen}  " + _caption(ev["info"]))
                row["preview"] = str(png)
            except Exception as exc:
                row["preview_error"] = str(exc)
        gen_rows.append(row)
        print(
            f"  gen {gen}: front {row['n_front']} feasible {row['n_feasible_front']} "
            f"hv {row['hypervolume']:.3f} knee ball {row.get('max_ball_mm')}",
            flush=True,
        )

    x0 = []
    for exponent, strut, n_seeds, flare in (
        (0.50, 1.55, 12, 0.15),
        (0.40, 1.40, 10, 0.0),
        (0.62, 1.70, 14, 0.30),
    ):
        x0.append([n_seeds, exponent, 0.4, 0.15, strut, flare, 2.2, 0.0])

    print(f"generative round {round_index}  pop={pop} gens={gens} seed={seed}", flush=True)
    result = nsga2(
        lambda x: evaluate_vector(x, fit, pitch=pitch),
        BOUNDS, pop=pop, gens=gens, seed=seed, x0=x0, callback=callback,
    )
    picks = _unique_picks(result.front)
    pick_rows = []
    for spec in picks:
        t = spec["trial"]
        d = decode(t.x, fit)
        ev = evaluate_design(d, fit, pitch=0.12)
        folder = round_dir / "picks" / spec["name"]
        folder.mkdir(parents=True, exist_ok=True)
        prefix = f"basin-{spec['name']}"
        use, printed, use_path, print_path = save_stl_pair(ev["holes"], fit, d["thickness"], folder, prefix)
        top = folder / "preview-top.png"
        view = folder / "preview-34.png"
        plan = folder / "preview-plan.png"
        try:
            render_views(use, top, view)
        except Exception as exc:
            ev["info"]["render_error"] = str(exc)
        save_plan_png(plan, ev["holes"], fit, d, spec["name"] + "  " + _caption(ev["info"]))
        params = {name: d[name] for name in GENE_NAMES}
        params["seeds_xy"] = np.round(ev["seeds"], 3).tolist()
        (folder / "params.json").write_text(json.dumps(params, indent=2))
        ev["info"]["watertight_use"] = bool(use.is_watertight)
        ev["info"]["watertight_print"] = bool(printed.is_watertight)
        ev["info"]["volume_mesh_mm3"] = float(use.volume) if use.is_watertight else None
        ev["info"]["name"] = spec["name"]
        (folder / "stats.json").write_text(json.dumps(ev["info"], indent=2, default=str))
        (folder / "design.json").write_text(json.dumps({
            "name": spec["name"],
            "method": "generative",
            "round": round_index,
            "prefix": prefix,
            "params": {name: d[name] for name in GENE_NAMES},
            "fit": {k: v for k, v in fit.items() if not isinstance(v, (dict, list))},
        }, indent=2))
        pick_rows.append(ev["info"])
        print(
            f"  pick {spec['name']}: ball {ev['info']['max_ball_mm']:.2f} "
            f"open {ev['info']['open_area_pct']:.1f}% flow {ev['info']['flow_cm3_s']:.2f} "
            f"disp {ev['info']['fingertip_disp_mm']} watertight {use.is_watertight}",
            flush=True,
        )

    v2 = smooth_v2_reference(fit)
    sheet = _pareto_sheet(round_dir, pick_rows)
    chart = _score_chart(out, gen_rows, round_dir / "score-chart.png")
    gif = _gif(gen_dir, round_dir / "evolution.gif")

    summary = {
        "round": round_index,
        "method": "nsga2",
        "pop": pop,
        "gens": gens,
        "seed": seed,
        "pitch_search_mm": pitch,
        "n_evaluated": len(result.trials),
        "n_front": len(result.front),
        "n_feasible_front": sum(1 for t in result.front if t.info.get("feasible")),
        "hypervolume": _hypervolume(result.front),
        "generations": gen_rows,
        "picks": pick_rows,
        "smooth_v2": v2,
        "contact_sheet": str(sheet) if sheet else None,
        "score_chart": str(chart) if chart else None,
        "evolution_gif": str(gif) if gif else None,
    }
    (round_dir / "params.json").write_text(json.dumps({
        "round": round_index,
        "pop": pop,
        "gens": gens,
        "seed": seed,
        "bounds": {n: list(b) for n, b in zip(GENE_NAMES, BOUNDS)},
        "genes": list(GENE_NAMES),
    }, indent=2))
    (round_dir / "stats.json").write_text(json.dumps(summary, indent=2, default=str))
    if sheet and sheet.exists():
        # The iteration logger's preview is the Pareto sheet.
        from shutil import copy2
        copy2(sheet, round_dir / "preview.png")
    (out / f"round-{round_index}-summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def _pareto_sheet(round_dir: Path, picks: list):
    from PIL import Image, ImageDraw, ImageFont

    images = []
    labels = []
    for info in picks:
        folder = round_dir / "picks" / info["name"]
        src = folder / "preview-34.png"
        if not src.exists():
            src = folder / "preview-plan.png"
        if not src.exists():
            continue
        images.append(Image.open(src).convert("RGB"))
        disp = info.get("fingertip_disp_mm")
        disp_s = f"{disp:.2f} mm" if isinstance(disp, float) else "—"
        labels.append(
            f"{info['name']}   ball {info['max_ball_mm']:.1f} mm   "
            f"open {info['open_area_pct']:.0f}%   flow {info['flow_cm3_s']:.1f} cm3/s   "
            f"finger {disp_s}"
        )
    if not images:
        return None
    thumb_w, thumb_h = 640, 480
    label_h = 36
    sheet = Image.new("RGB", (thumb_w * len(images), thumb_h + label_h + 16), (247, 244, 239))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    for i, (im, lab) in enumerate(zip(images, labels)):
        t = im.copy()
        t.thumbnail((thumb_w - 8, thumb_h - 8))
        x = i * thumb_w + (thumb_w - t.size[0]) // 2
        y = (thumb_h - t.size[1]) // 2
        sheet.paste(t, (x, y))
        draw.text((i * thumb_w + 8, thumb_h + 6), lab, fill=(30, 30, 30), font=font)
    out = round_dir / "pareto-sheet.png"
    sheet.save(out)
    return out


def _score_chart(design_dir, gen_rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs, hv, flow = [], [], []
    for row in gen_rows:
        xs.append(row["gen"])
        hv.append(row.get("hypervolume") or 0.0)
        flow.append(row.get("flow_cm3_s") or 0.0)
    if not xs:
        return None
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
    ax.plot(xs, hv, "-o", color="#1F6B4A", label="hypervolume (flow, capture)")
    ax.set_xlabel("generation")
    ax.set_ylabel("normalized hypervolume")
    ax.set_title("AI + generative design, this round")
    ax.set_facecolor("#FBFAF8")
    fig.patch.set_facecolor("#F7F4EF")
    ax2 = ax.twinx()
    ax2.plot(xs, flow, "--s", color="#3E5966", label="knee flow (cm3/s)")
    ax2.set_ylabel("knee flow (cm³/s)")
    fig.tight_layout()
    path = Path(path)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    # Also drop a copy where the design-level chart usually lives.
    fig_copy = Path(design_dir) / "score-chart.png"
    path.replace(path)  # no-op keep
    import shutil
    shutil.copy2(path, fig_copy)
    return path


def _gif(gen_dir: Path, path: Path):
    from PIL import Image

    frames = []
    for p in sorted(gen_dir.glob("*.png")):
        im = Image.open(p).convert("RGB")
        im.thumbnail((480, 520))
        canvas = Image.new("RGB", (480, 520), (247, 244, 239))
        canvas.paste(im, ((480 - im.size[0]) // 2, (520 - im.size[1]) // 2))
        frames.append(canvas)
    if not frames:
        return None
    path = Path(path)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=700, loop=0)
    return path
