"""Round 03: rounding is allowed, and it is not rewarded.

The layout is the round 02 knee. The search may change strut width, how
square the strut section is, and how much the junction notch is filled.
None of those parameters appear in the objectives. The objectives are the
orifice flow after corner water is removed, how small the largest opening
is, how little a fiber can hook a corner, and how low the plane-stress
peak is. If a round junction wins, it wins on one of those.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KNEE_PARAMS = HERE.parent / "designs" / "generative-v1" / "iterations" / "02" / "picks" / "knee" / "params.json"

# strut, blend (junction fillet, mm), profile (0 square, 1 round capsule)
BOUNDS = (
    (1.50, 2.10),
    (0.05, 2.20),
    (0.0, 1.0),
)
GENE_NAMES = ("strut", "blend", "profile")


def _smax(a, b, k):
    k = float(k)
    if k < 1e-4:
        return np.maximum(a, b)
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return (1.0 - h) * b + h * a + k * h * (1.0 - h)


def _segments(seeds, fit, strut, flare=0.05):
    from gen_grate import ridge_graph

    d = {"strut": strut, "flare": flare, "n_seeds": len(seeds), "exponent": 0.4, "phase": 0.0,
         "jitter": 0.0, "thickness": 2.29, "harm": 0.0}
    nodes, edges, widths, _fixed = ridge_graph(seeds, d, fit)
    if len(edges) == 0:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0)
    a = np.array([nodes[i] for i, _j in edges])
    b = np.array([nodes[j] for _i, j in edges])
    return a, b, np.asarray(widths, float) / 2.0


def plan_field(xs, seeds, fit, strut, blend, profile, flare=0.05):
    """Signed field, positive in the solid. blend and profile are shape, not score."""
    a, b, radii = _segments(seeds, fit, strut, flare)
    n = len(xs)
    X, Y = np.meshgrid(xs, xs, indexing="xy")
    xy = np.column_stack([X.ravel(), Y.ravel()])
    if len(radii) == 0:
        field = np.full(xy.shape[0], -1.0)
    else:
        acc = None
        q = float(np.clip(profile, 0.0, 1.0))
        for i in range(len(radii)):
            ab = b[i] - a[i]
            L = float(np.hypot(ab[0], ab[1]))
            if L < 1e-6:
                continue
            t_hat = ab / L
            n_hat = np.array([-t_hat[1], t_hat[0]])
            rel = xy - a[i]
            along = rel @ t_hat
            perp = rel @ n_hat
            r = float(radii[i])
            along_c = np.clip(along, 0.0, L)
            d_cap = np.hypot(along - along_c, perp)
            qx = np.abs(along - L / 2.0) - L / 2.0
            qy = np.abs(perp) - r
            d_box = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0)
            # Both fields are positive inside the strut. The box SDF is already
            # a distance to the rectangle; the capsule is radius minus distance
            # to the centerline.
            f = (1.0 - q) * (-d_box) + q * (r - d_cap)
            acc = f if acc is None else _smax(acc, f, blend)
        field = acc if acc is not None else np.full(xy.shape[0], -1.0)
    rxy = np.hypot(xy[:, 0], xy[:, 1])
    R = fit["r_in"]
    rim = np.minimum(rxy - (R - fit["rim"]), (R + 0.4) - rxy)
    field = _smax(field, rim, blend)
    field = np.where(rxy > R + 0.3, -1.0, field)
    return field.reshape(n, n), X, Y


def _hole_rings(xs, field, fit):
    from skimage.measure import find_contours

    pitch = float(xs[1] - xs[0])
    X, Y = np.meshgrid(xs, xs, indexing="xy")
    rad = np.hypot(X, Y)
    void = (rad < fit["r_in"] - 0.15) & (field < 0.0)
    contours = find_contours(void.astype(float), 0.5)
    rings = []
    for c in contours:
        if len(c) < 8:
            continue
        x = xs[0] + c[:, 1] * pitch
        y = xs[0] + c[:, 0] * pitch
        # Drop the outer boundary of the void mask, which is the rim circle.
        if np.hypot(x, y).mean() > fit["r_in"] - fit["rim"] - 0.4:
            continue
        rings.append(np.column_stack([x, y]))
    return rings, void


def evaluate_shape(x, seeds, fit, pitch=0.42):
    from gendesign.corners import corner_proxies
    from gendesign.flow2d import drainage_report
    from gendesign.stress2d import plane_stress_peak
    from scipy.ndimage import distance_transform_edt

    strut, blend, profile = [float(v) for v in x]
    R = fit["r_in"]
    xs = np.arange(-R - pitch, R + pitch * 1.5, pitch)
    field, X, Y = plan_field(xs, seeds, fit, strut, blend, profile)
    rad = np.hypot(X, Y)
    domain = rad <= R
    rings, void = _hole_rings(xs, field, fit)
    flow = drainage_report(
        void, domain, pitch,
        head_mm=fit["head_mm"], cd=fit["cd"],
        film_gap_mm=fit["film_gap"], film_full_mm=fit["film_full"],
    )
    cells = flow.pop("cells")
    corners = corner_proxies(rings)
    open_area = max(flow["open_area_mm2"], 1.0)
    retained = min(corners["retained_mm2"], open_area * 0.5)
    flow_net = flow["flow_mm3_s"] * max(0.0, 1.0 - retained / open_area)
    solid = domain & (field >= 0.0)
    # Strut width from the distance transform, away from the rim ring.
    web = solid & (rad < R - fit["rim"] - 0.4)
    edt = distance_transform_edt(web) * pitch
    from skimage.morphology import skeletonize
    sk = skeletonize(web)
    widths = 2.0 * edt[sk]
    # The thinnest few pixels are skeleton spurs. The 20th percentile is the strut.
    min_strut = float(np.percentile(widths, 20)) if widths.size else 0.0
    support = solid & (rad > R - fit["rim"])
    stress = plane_stress_peak(
        solid, pitch, E=fit["E"], nu=fit["nu"], thickness_mm=2.29,
        load_N=fit["finger_N"], support=support, load_radius_px=4.0 / pitch,
    )
    p95 = float(stress["p95_MPa"]) if stress["ok"] else 1e6
    capture = fit["max_ball"] - flow["max_ball_mm"]
    release = -float(corners["snag"])
    relief = -p95
    violation = 0.0
    if not stress["ok"]:
        violation += 5.0
    if flow["n_openings"] < 1 or flow["min_ball_mm"] < fit["opening_floor"] - 0.45:
        violation += fit["opening_floor"] - flow["min_ball_mm"] + 0.5
    if flow["max_ball_mm"] > fit["max_ball"]:
        violation += flow["max_ball_mm"] - fit["max_ball"]
    if min_strut < fit["min_strut"] - 0.05:
        violation += fit["min_strut"] - min_strut
    info = {
        "strut": strut,
        "blend": blend,
        "profile": profile,
        "flow_mm3_s": flow_net,
        "flow_cm3_s": flow_net / 1000.0,
        "flow_gross_cm3_s": flow["flow_cm3_s"],
        "retained_mm2": corners["retained_mm2"],
        "snag": corners["snag"],
        "tightest_radius_mm": corners["tightest_radius_mm"],
        "capture_mm": capture,
        "hair_release": release,
        "stress_p95_MPa": p95,
        "stress_relief": relief,
        "max_ball_mm": flow["max_ball_mm"],
        "min_ball_mm": flow["min_ball_mm"],
        "open_area_pct": 100.0 * flow["open_area_frac"],
        "n_openings": flow["n_openings"],
        "min_strut_mm": min_strut,
        "feasible": violation <= 1e-8,
        "violation": violation,
        "n_cells_scored": len(cells),
        "objectives": [flow_net, capture, release, relief],
    }
    return {
        "objectives": info["objectives"],
        "violation": violation,
        "info": info,
        "field": field,
        "xs": xs,
        "rings": rings,
    }


def holes_for_mesh(xs, field, fit):
    from shapely.geometry import Polygon

    rings, _void = _hole_rings(xs, field, fit)
    holes = []
    for ring in rings:
        if len(ring) < 8:
            continue
        poly = Polygon(ring).simplify(0.25).buffer(0)
        if poly.is_empty or poly.area < 2.0:
            continue
        if poly.geom_type == "MultiPolygon":
            holes.extend([g for g in poly.geoms if g.area >= 2.0])
        elif poly.geom_type == "Polygon":
            holes.append(poly)
    return holes


def render_closeup(mesh, path, focus=(6.0, 2.5, -4.0)):
    import pyvista as pv

    pv.OFF_SCREEN = True
    p = pv.Plotter(off_screen=True, window_size=(1100, 900))
    p.set_background("#ECE8E1")
    m = pv.wrap(mesh)
    try:
        m = m.compute_normals(split_vertices=True, feature_angle=35)
    except Exception:
        pass
    p.add_mesh(m, color="#E4E0D8", specular=0.45, specular_power=40, smooth_shading=True)
    f = np.array(focus, float)
    p.camera_position = [(f[0] + 14, f[1] - 16, f[2] + 12), f, (0, 0, 1)]
    p.screenshot(str(path))
    p.close()


class GrateGenerator:
    """Round-02 knee layout. Strut, blend, and profile are free. They are not objectives."""

    name = "voronoi-grate"

    def __init__(self, seeds, fit):
        self.seeds = seeds
        self.fit = fit

    def bounds(self):
        return BOUNDS

    def generate(self, x, requirements):
        ev = evaluate_shape(x, self.seeds, self.fit, pitch=0.48)
        info = ev["info"]
        info["objectives"] = ev["objectives"]
        info["params"] = {"strut": float(x[0]), "blend": float(x[1]), "profile": float(x[2])}
        return {"params": info["params"], "info": info}


class _Score(Evaluator):
    def __init__(self, name, key, uncertainty, constraint=False):
        self.name = name
        self.key = key
        self._uncertainty = uncertainty
        self.constraint = constraint

    def evaluate(self, design, requirements):
        info = design["info"]
        if self.constraint:
            return {
                "objectives": [],
                "violation": info.get("violation") or 0.0,
                "metrics": info,
                "uncertainties": {self.name: self._uncertainty},
            }
        return {
            "objectives": [info[self.key]],
            "violation": 0.0,
            "metrics": {"feasible": info.get("feasible", True), self.key: info[self.key],
                        "blend": info.get("blend"), "profile": info.get("profile")},
            "uncertainties": {self.name: self._uncertainty},
        }


def grate_evaluators():
    return [
        _Score("drainage", "flow_mm3_s", "Orifice model at a fixed head, minus corner water. Not a measured drain."),
        _Score("capture", "capture_mm", "Largest opening versus the ball limit. Not a hair simulation."),
        _Score("hair-release", "hair_release", "Corners tighter than 0.5 mm can hook a fiber. Proxy, not a pull test."),
        _Score("stress", "stress_relief", "Plane-stress peak under an in-plane 10 N patch. Not plate bending."),
        _Score("printability", "violation", "Openings under 4 mm or struts under 1.5 mm are infeasible.", constraint=True),
    ]


def run_round(req, out, pop=12, gens=4, seed=5):
    from gendesign.process import run as process_run
    from gendesign.requirements import Requirements, validate_mapping
    from gen_grate import fit_from_requirements, render_views

    out = Path(out)
    errors = validate_mapping(req)
    if errors:
        raise SystemExit("requirements: " + "; ".join(errors))
    requirements = Requirements(
        name=str(req.get("name") or ""),
        units=str(req.get("units") or ""),
        purpose=str(req.get("purpose") or ""),
        constraints=req.get("constraints") or {},
        raw=req,
    )
    fit = fit_from_requirements(req)
    params = json.loads(KNEE_PARAMS.read_text())
    seeds = np.asarray(params["seeds_xy"], float)
    thickness = float(params["thickness"])
    round_dir = out / "iterations" / "03"
    (round_dir / "generations").mkdir(parents=True, exist_ok=True)

    print(f"round 03 via gendesign.process  pop={pop} gens={gens} seed={seed}", flush=True)
    result = process_run(
        GrateGenerator(seeds, fit),
        grate_evaluators(),
        requirements,
        method="nsga2",
        pop=pop,
        gens=gens,
        seed=seed,
        x0=[[1.57, 0.08, 0.0], [1.57, 1.6, 1.0], [1.70, 0.9, 0.6], [1.90, 0.3, 0.2]],
    )
    result.save(round_dir / "result.json")
    feas = [t for t in result.trials if t.info.get("feasible")]
    front = [t for t in result.front if t.info.get("feasible")] or list(result.front)

    def knee_of(pool):
        if not pool:
            return None
        keys = ("flow_mm3_s", "capture_mm", "hair_release", "stress_relief")
        cols = []
        for k in keys:
            col = np.array([float(t.info.get(k, -1e6) or -1e6) for t in pool])
            span = float(col.max() - col.min())
            cols.append((col - col.min()) / span if span > 1e-9 else np.zeros_like(col))
        dist = np.linalg.norm(np.vstack(cols).T - 1.0, axis=1)
        return pool[int(np.argmin(dist))]

    picks = []

    def take(name, t):
        if t is None:
            return
        if any(np.allclose(t.x, p["trial"].x, atol=0.05) for p in picks):
            return
        picks.append({"name": name, "trial": t})

    take("knee", knee_of(front))
    take("low-stress", min(feas or front, key=lambda t: t.info.get("stress_p95_MPa", 1e9)))
    take("easy-clean", max(feas or front, key=lambda t: -t.info.get("snag", 1e9)))
    take("open-drain", max(feas or front, key=lambda t: t.info.get("flow_mm3_s", -1e9)))

    # Did rounding show up on the front, and on which score?
    def corr(key):
        if len(feas) < 5:
            return None
        b = np.array([t.info["blend"] for t in feas])
        y = np.array([float(t.info.get(key, 0.0) or 0.0) for t in feas])
        if b.std() < 1e-6 or y.std() < 1e-9:
            return 0.0
        return float(np.corrcoef(b, y)[0, 1])

    analysis = {
        "n_feasible": len(feas),
        "blend_mean_feasible": float(np.mean([t.info["blend"] for t in feas])) if feas else None,
        "blend_mean_front": float(np.mean([t.info["blend"] for t in front if "blend" in t.info])) if front else None,
        "profile_mean_front": float(np.mean([t.info.get("profile", 0) for t in front if "blend" in t.info])) if front else None,
        "corr_blend_flow": corr("flow_mm3_s"),
        "corr_blend_capture": corr("capture_mm"),
        "corr_blend_release": corr("hair_release"),
        "corr_blend_stress_relief": corr("stress_relief"),
        "corr_profile_stress_relief": None,
    }
    if len(feas) >= 5:
        p = np.array([t.info["profile"] for t in feas])
        y = np.array([t.info["stress_relief"] for t in feas])
        analysis["corr_profile_stress_relief"] = float(np.corrcoef(p, y)[0, 1]) if p.std() > 1e-6 else 0.0

    rows = []
    for spec in picks:
        t = spec["trial"]
        # Rebuild on a finer grid for the mesh and the reported numbers.
        ev = evaluate_shape(t.x, seeds, fit, pitch=0.28)
        holes = holes_for_mesh(ev["xs"], ev["field"], fit)
        folder = round_dir / "picks" / spec["name"]
        folder.mkdir(parents=True, exist_ok=True)
        use, printed = build_from(holes, fit, thickness, folder, f"basin-{spec['name']}")
        ev["info"]["watertight_use"] = bool(use.is_watertight)
        ev["info"]["watertight_print"] = bool(printed.is_watertight)
        ev["info"]["name"] = spec["name"]
        ev["info"]["volume_mesh_mm3"] = float(use.volume) if use.is_watertight else None
        try:
            render_views(use, folder / "preview-top.png", folder / "preview-34.png")
            render_closeup(use, folder / "preview-junction.png")
        except Exception as exc:
            ev["info"]["render_error"] = str(exc)
        (folder / "stats.json").write_text(json.dumps(ev["info"], indent=2, default=str))
        (folder / "params.json").write_text(json.dumps({
            "strut": float(t.x[0]), "blend": float(t.x[1]), "profile": float(t.x[2]),
            "layout": "round-02-knee",
        }, indent=2))
        rows.append(ev["info"])
        print(
            f"  {spec['name']}: blend {ev['info']['blend']:.2f} profile {ev['info']['profile']:.2f} "
            f"ball {ev['info']['max_ball_mm']:.2f} min {ev['info']['min_ball_mm']:.2f} "
            f"flow {ev['info']['flow_cm3_s']:.1f} snag {ev['info']['snag']:.2f} "
            f"retain {ev['info']['retained_mm2']:.1f} stress {ev['info']['stress_p95_MPa']:.1f} "
            f"wt {use.is_watertight}",
            flush=True,
        )

    summary = {"round": "03", "analysis": analysis, "picks": rows, "pop": pop, "gens": gens}
    (round_dir / "stats.json").write_text(json.dumps(summary, indent=2, default=str))
    (round_dir / "params.json").write_text(json.dumps({
        "layout": "round-02 knee seeds, fixed",
        "genes": list(GENE_NAMES),
        "bounds": {n: list(b) for n, b in zip(GENE_NAMES, BOUNDS)},
        "objectives": ["net drainage", "capture", "hair release", "stress relief"],
        "note": "blend and profile are free parameters and are not in the objectives",
    }, indent=2))
    _sheet(round_dir, rows)
    print("analysis", json.dumps(analysis, indent=2))
    return summary


def build_from(holes, fit, thickness, folder, prefix):
    from gen_grate import build_meshes

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    use, printed = build_meshes(holes, fit, thickness, n_outer=120)
    use.export(folder / f"{prefix}-use.stl")
    printed.export(folder / f"{prefix}-print.stl")
    return use, printed


def _sheet(round_dir, rows):
    from PIL import Image, ImageDraw, ImageFont

    images, labels = [], []
    for info in rows:
        src = round_dir / "picks" / info["name"] / "preview-top.png"
        if not src.exists():
            continue
        images.append(Image.open(src).convert("RGB"))
        labels.append(
            f"{info['name']}  blend {info['blend']:.2f}  ball {info['max_ball_mm']:.1f}  "
            f"stress {info['stress_p95_MPa']:.0f}"
        )
    if not images:
        return
    w = 560
    sheet = Image.new("RGB", (w * len(images), w + 40), (247, 244, 239))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    for i, (im, lab) in enumerate(zip(images, labels)):
        t = im.copy()
        t.thumbnail((w - 16, w - 16))
        sheet.paste(t, (i * w + (w - t.size[0]) // 2, (w - t.size[1]) // 2))
        draw.text((i * w + 10, w + 8), lab, fill=(30, 30, 30), font=font)
    sheet.save(round_dir / "pareto-sheet.png")
    sheet.save(round_dir / "preview.png")
