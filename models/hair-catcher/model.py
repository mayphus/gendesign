"""Hair catcher for gendesign: analysis first, then the pebble-plate generator.

`analyze(req)` derives the design targets from requirements.yaml (open area
from the orifice equation, hole floor from the capillary length, plate
thickness from the fingertip and hard-push loads) and screens three concepts
against them. The flat plate wins because drainage, not structure, binds.

One flat plate, flush with the basin, with Voronoi cells opened into smooth
pebble-shaped holes. It prints top-face-down with no bridges and no
overhangs. Fit (flange, collar, lead-in) is fixed; the grate is searched.

    gendesign round models/hair-catcher --pop 12 --gens 4
    python models/hair-catcher/generate.py --design designs/pebble-e/design.json

The generator reproduces designs/pebble-e exactly (seed 3, spacing 6.8).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from gendesign.field import (
    mesh_field,
    mesh_report,
    mx,
    polygon_field,
    print_orientation,
    smax,
    smin,
    unsupported_area,
)
from gendesign.flow2d import capillary_transmission, orifice_flow
from gendesign.process import Evaluator, Generator

# ------------------------------------------------------------------ fit (mm)
# Installed coordinates: z = 0 is the basin surface, the collar goes down.
FL_R, FL_T = 23.0, 1.6          # flange Ø46 x 1.6 (seat assumed, not calipered)
C_OD, C_ID = 35.21 / 2, 32.0 / 2  # CAD collar; prints ~35.10 after 0.3% PLA shrink
Z_BOT, LEAD = -8.6, 0.7         # collar depth, 45° lead-in
RB = C_ID                       # bore radius the plate fills


@dataclass
class PlateParams:
    seed: int = 3
    spacing: float = 6.8      # nominal seed spacing (mm); sets the cell size
    grade: float = 0.15       # cells shrink toward the rim by about this fraction
    rib: float = 2.0          # rib width between openings (mm)
    edge_rib: float = 1.2     # material between outer openings and the bore (mm)
    round_frac: float = 0.8   # corner radius as a fraction of each cell's inradius
    plate_t: float = 2.2      # plate thickness inside the bore (mm)
    min_inscribed: float = 3.5  # cells smaller than this are left solid


BOUNDS = {  # searched genes; the rest stay at their defaults
    "seed": (0, 400),
    "spacing": (5.6, 8.6),
    "grade": (0.0, 0.4),
    "rib": (1.8, 2.6),
    "edge_rib": (1.35, 2.0),
    "round_frac": (0.5, 0.95),
}


# ------------------------------------------------------------------ 2-D layout
def _ghosts(r, n):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[r * np.cos(t), r * np.sin(t)]


def _mirror(pts):
    r = np.hypot(pts[:, 0], pts[:, 1])[:, None]
    return pts * (2 * RB - r) / np.maximum(r, 1e-6)


def _density(p, grade):
    r = np.hypot(p[:, 0], p[:, 1]) / RB
    return (1 + grade * r ** 2) ** 2


def seeds(p: PlateParams):
    """Graded Poisson-disc, then weighted Lloyd, mirrored across the bore wall."""
    from scipy.spatial import cKDTree

    rng = np.random.default_rng(int(p.seed))
    pts = []
    for _ in range(6000):
        r = (RB - 1.0) * np.sqrt(rng.random())
        t = rng.random() * 2 * np.pi
        q = np.array([r * np.cos(t), r * np.sin(t)])
        sp = p.spacing / np.sqrt(_density(q[None], p.grade)[0])
        if all(np.hypot(*(q - o)) >= sp for o in pts):
            pts.append(q)
    pts = np.array(pts)
    S = 80000
    sr = RB * np.sqrt(rng.random(S))
    st = rng.random(S) * 2 * np.pi
    samp = np.c_[sr * np.cos(st), sr * np.sin(st)]
    w = _density(samp, p.grade)
    for _ in range(12):
        G = np.vstack([_mirror(pts), _ghosts(RB + 14, 24)])
        _, idx = cKDTree(np.vstack([pts, G])).query(samp)
        n = len(pts)
        sw = np.bincount(idx, weights=w, minlength=n + len(G))[:n]
        sx = np.bincount(idx, weights=w * samp[:, 0], minlength=n + len(G))[:n]
        sy = np.bincount(idx, weights=w * samp[:, 1], minlength=n + len(G))[:n]
        has = sw > 0
        pts = np.where(has[:, None], np.c_[sx, sy] / np.where(has, sw, 1)[:, None], pts)
    return pts + rng.normal(0, 0.25, pts.shape)


def openings(pts, p: PlateParams):
    """Exact pebble outlines (shapely): inset each cell by half a rib, then open it."""
    import shapely
    from shapely.geometry import Point, Polygon
    from scipy.spatial import Voronoi

    vor = Voronoi(np.vstack([pts, _mirror(pts), _ghosts(RB + 14, 24)]))
    bore = Point(0, 0).buffer(RB - p.edge_rib + p.rib / 2, quad_segs=128)
    holes = []
    for i in range(len(pts)):
        reg = vor.regions[vor.point_region[i]]
        if -1 in reg or not reg:
            continue
        inset = Polygon(vor.vertices[reg]).intersection(bore).buffer(-p.rib / 2, join_style="mitre")
        if inset.is_empty:
            continue
        R = p.round_frac * shapely.maximum_inscribed_circle(inset).length
        peb = inset.buffer(-R, quad_segs=32).buffer(R, quad_segs=64)
        if peb.is_empty:
            continue
        if peb.geom_type == "MultiPolygon":
            peb = max(peb.geoms, key=lambda g: g.area)
        if 2 * shapely.maximum_inscribed_circle(peb).length >= p.min_inscribed:
            holes.append(peb)
    return holes


def layout_stats(holes):
    import shapely

    if not holes:
        return {"n": 0}
    ins = sorted(round(2 * shapely.maximum_inscribed_circle(h).length, 2) for h in holes)
    eq = sorted(round(2 * np.sqrt(h.area / np.pi), 2) for h in holes)
    gaps = [holes[i].distance(holes[j]) for i in range(len(holes)) for j in range(i + 1, len(holes))]
    gaps = [g for g in gaps if g < 3.5] or [99.0]
    edge = min(RB - max(np.hypot(*np.array(h.exterior.coords).T)) for h in holes)
    return {
        "n": len(holes),
        "inscribed": {"min": ins[0], "median": float(np.median(ins)), "max": ins[-1], "all": ins},
        "equiv": {"min": eq[0], "median": float(np.median(eq)), "max": eq[-1]},
        "rib_min": round(min(gaps), 2),
        "rib_median": round(float(np.median(gaps)), 2),
        "edge_min": round(float(edge), 2),
        "open_mm2": round(sum(h.area for h in holes)),
        "open_pct": round(100 * sum(h.area for h in holes) / (np.pi * RB ** 2), 1),
    }



# ------------------------------------------------------------------ analysis (before any geometry)
def _plate_deflection(P, a, t, E, nu, solid_frac):
    """Clamped circular plate, central load: w = P a^2 / (16 pi D).

    A perforated plate is softer. D is scaled by solid_frac^2, a
    conservative bending-dominated estimate for a web of ribs.
    """
    import math

    D = E * t ** 3 / (12 * (1 - nu ** 2)) * max(solid_frac, 1e-3) ** 2
    return P * a ** 2 / (16 * math.pi * D)


def _plate_stress(P, a, t, nu, solid_frac, r0=5.0):
    """Peak bending stress under a fingertip patch of radius r0, clamped edge.

    Roark: sigma = 3P/(2 pi t^2) * ((1+nu) ln(a/r0) + 1). The web carries it
    on solid_frac of the section, so the rib stress is divided by that.
    """
    import math

    return 3 * P / (2 * math.pi * t ** 2) * ((1 + nu) * math.log(a / r0) + 1) / max(solid_frac, 1e-3)


def analyze(req):
    """Turn requirements into design targets, then screen concepts against them.

    Nothing here draws a part. Every target says which requirement and which
    equation it came from, so a later test can correct the right thing.
    """
    import math

    from gendesign.flow2d import capillary_length_mm

    c, phys, fn = req.constraints or {}, req.section("physics"), req.section("function")
    cd, head, g = float(phys.get("cd", 0.61)), float(phys.get("head_mm", 5.0)), 9810.0
    E, nu = float(phys.get("E_MPa", 2340)), float(phys.get("nu", 0.36))
    allow = float(phys.get("allowable_MPa", 20.0))
    q_min = float(fn.get("drain_flow_min_cm3_s", 78.0))
    P_tip, P_hard = float(c.get("fingertip_N", 10.0)), float(c.get("hard_push_N", 30.0))
    w_max = float(c.get("max_fingertip_disp_mm", 0.5))
    rib_min, rim_min = float(c.get("min_strut_mm", 1.5)), float(c.get("min_rim_mm", 1.35))
    floor = float(c.get("opening_floor_mm", 4.0))
    ball = float(c.get("max_ball_mm", 12.0))
    bore = math.pi * RB ** 2

    v = math.sqrt(2 * g * head)
    a_req = q_min * 1000 / (cd * v)
    phi_req = a_req / bore
    lc = capillary_length_mm()
    solid = 1 - phi_req
    t_stiff = (P_tip * RB ** 2 * 12 * (1 - nu ** 2) / (16 * math.pi * E * w_max * solid ** 2)) ** (1 / 3)
    t_strength = math.sqrt(3 * P_hard / (2 * math.pi * allow) * ((1 + nu) * math.log(RB / 5.0) + 1) / solid)
    t_min = max(t_stiff, t_strength, 1.2)
    t_plate = PlateParams().plate_t
    w_at = _plate_deflection(P_tip, RB, t_plate, E, nu, solid)
    s_at = _plate_stress(P_hard, RB, t_plate, nu, solid)

    # Smallest hole that reaches phi_req in a flat plate with min ribs:
    # hexagonal cells, hole inscribed d, pitch d + w -> open fraction
    # (d/(d+w))^2 of the active disk inside the rim.
    active = ((RB - rim_min) / RB) ** 2
    need = phi_req / active
    d_flat = rib_min * math.sqrt(need) / (1 - math.sqrt(need)) if need < 1 else float("inf")
    cone = 1 / math.cos(math.radians(float(c.get("cone_angle_deg", 47.0))))
    need_cone = phi_req / (active * cone)
    d_cone = max(floor, rib_min * math.sqrt(need_cone) / (1 - math.sqrt(need_cone)))
    margin = min(w_max / w_at, allow / s_at)
    binds = "binds" if margin < 1 else ("is close" if margin < 1.5 else "has margin")

    targets = {
        "open_area_min_mm2": {"value": round(a_req), "from": "function.drain_flow_min_cm3_s, physics.cd, physics.head_mm",
                              "how": f"A = Q / (Cd sqrt(2 g h)) = {q_min} cm³/s / ({cd} x {v:.0f} mm/s)"},
        "open_fraction_min": {"value": round(phi_req, 3), "from": "open_area_min_mm2 / bore area",
                              "how": f"{a_req:.0f} / {bore:.0f} mm²"},
        "hole_min_mm": {"value": floor, "from": "constraints.opening_floor_mm; capillary length",
                        "how": f"water holds a film under {lc:.2f} mm (sqrt(sigma / rho g)); full flow from {floor} mm"},
        "hole_max_mm": {"value": ball, "from": "constraints.max_ball_mm", "how": "hard cap; smaller is better capture"},
        "plate_t_min_mm": {"value": round(t_min, 2), "from": "constraints.fingertip_N, hard_push_N, max_fingertip_disp_mm; physics.E_MPa",
                           "how": f"stiffness t >= {t_stiff:.2f} (clamped plate, D x solid²); strength t >= {t_strength:.2f} "
                                  f"at {P_hard:.0f} N, {allow:.0f} MPa allowable"},
        "rib_min_mm": {"value": rib_min, "from": "constraints.min_strut_mm", "how": "print rule"},
        "rim_min_mm": {"value": rim_min, "from": "constraints.min_rim_mm", "how": "print rule"},
    }
    checks = [
        f"At the {t_plate} mm plate and {100 * phi_req:.0f}% open: fingertip deflection {w_at:.3f} mm "
        f"(limit {w_max}), hard-push rib stress {s_at:.1f} MPa (allowable {allow:.0f}). Structure {binds}: "
        f"{margin:.2f}x on the tighter of the two, so the plate stays at {t_plate} mm (minimum {t_min:.2f}).",
        f"Drainage binds: {a_req:.0f} mm² of open area is {100 * phi_req:.0f}% of the bore.",
        f"A flat plate with {rib_min} mm ribs reaches that with holes of about {d_flat:.1f} mm inscribed "
        f"(hexagonal estimate, ±15%). A {c.get('cone_angle_deg', 47)}° cone has {cone:.2f}x the area, so holes can drop to the {d_cone:.1f} mm floor.",
    ]
    concepts = [
        {"name": "flat plate", "verdict": "chosen" if d_flat <= ball else "rejected",
         "why": f"Prints top-down with nothing over air and sits flush. Meets the flow target with ~{d_flat:.1f} mm holes; "
                "drainage is the active constraint, so the search should spend its freedom on open area, not thickness."},
        {"name": "cone", "verdict": "fallback",
         "why": f"{cone:.2f}x the grate area: holes down to the {d_cone:.1f} mm floor for the same flow. Costs ~18 mm of insert depth and runs "
                "the underside at the 45° overhang limit. Use it if the owner wants holes under the flat-plate size."},
        {"name": "two-level", "verdict": "rejected",
         "why": "The fine layer catches more hair but lowers flow, and it bridges (pebble-c: ~189 mm² over air) or needs "
                "vaults (pebble-d). Not needed while the flow target is met by one layer."},
    ]
    open_q = [
        "No tap flow was given. The flow target is smooth v2's 78 cm³/s under the same orifice model; "
        "a measured tap rate should replace it (function.drain_flow_min_cm3_s).",
        "No largest acceptable hole was given beyond the 12 mm cap. Capture is maximized, not bounded.",
        f"allowable_MPa {allow:.0f} is a layer-line PLA guess, not a test.",
    ]
    return {"targets": targets, "checks": checks, "concepts": concepts,
            "chosen": next(c_["name"] for c_ in concepts if c_["verdict"] == "chosen"),
            "generator": "pebble-plate", "open_questions": open_q}


# ------------------------------------------------------------------ generator
class PebblePlate(Generator):
    name = "pebble-plate"

    def bounds(self):
        return list(BOUNDS.values())

    def params_from_x(self, x):
        kw = {k: float(v) for k, v in zip(BOUNDS, x)}
        kw["seed"] = int(round(kw["seed"]))
        return PlateParams(**{k: (round(v, 3) if isinstance(v, float) else v) for k, v in kw.items()})

    def build_from_params(self, params):
        """Exact rebuild of a saved pick or design (no rounding through the genes)."""
        return self.build(PlateParams(**params))

    def x_from_params(self, params):
        return [float(params[k]) for k in BOUNDS]

    def generate(self, x, requirements=None):
        return self.build(self.params_from_x(x))

    def build(self, p: PlateParams):
        holes = openings(seeds(p), p)
        return {"params": asdict(p), "holes": holes, "layout": layout_stats(holes)}


# ------------------------------------------------------------------ evaluators
def _phys(req, key, default):
    return float((req.section("physics") or {}).get(key, default))


def _con(req, key, default):
    return float((req.constraints or {}).get(key, default))


class Drainage(Evaluator):
    """Orifice flow through every hole at a fixed head, discounted for water film."""

    name = "drainage"
    objectives = ("drainage_cm3_s",)

    def evaluate(self, design, req):
        import shapely

        cd = float(req.calibrated("drainage.cd", _phys(req, "cd", 0.61)))
        head = float(req.calibrated("drainage.head_mm", _phys(req, "head_mm", 5.0)))
        gap, full = _con(req, "film_gap_mm", 2.7), _con(req, "film_full_mm", 4.0)
        q = 0.0
        for h in design["holes"]:
            ins = 2 * shapely.maximum_inscribed_circle(h).length
            q += orifice_flow(h.area, head, cd=cd, transmission=capillary_transmission(ins, gap, full))
        lay = design["layout"]
        target = float((req.analysis.get("targets", {}).get("open_area_min_mm2") or {}).get("value", 0))
        flow_min = float(req.section("function").get("drain_flow_min_cm3_s", 0))
        violation = max(0.0, flow_min - q / 1000.0) / max(flow_min, 1.0)
        return {
            "objectives": [q / 1000.0],
            "violation": violation,
            "metrics": {"flow_cm3_s": round(q / 1000.0, 1), "open_pct": lay.get("open_pct"), "holes": lay.get("n"),
                        "open_mm2": lay.get("open_mm2"), "open_area_target_mm2": target},
            "uncertainties": {"drainage": f"Orifice model, Cd {cd}, {head} mm head. Ranks designs; not a timed drain."},
        }


class Capture(Evaluator):
    """Smaller largest hole catches more; one stray big hole is penalized."""

    name = "capture"
    objectives = ("capture_mm",)

    def evaluate(self, design, req):
        lay = design["layout"]
        if not lay.get("n"):
            return {"objectives": [-99.0], "violation": 10.0, "metrics": {}}
        ball = _con(req, "max_ball_mm", 12.0)
        mx_, med = lay["inscribed"]["max"], lay["inscribed"]["median"]
        score = (ball - mx_) - 0.5 * (mx_ - med)
        return {
            "objectives": [score],
            "violation": max(0.0, mx_ - ball),
            "metrics": {"max_ball_mm": mx_, "median_ball_mm": med, "min_ball_mm": lay["inscribed"]["min"]},
            "uncertainties": {"capture": "Largest inscribed circle stands in for hair capture. No hair test yet."},
        }


class Structure(Evaluator):
    """Fingertip deflection and hard-push stress, clamped perforated plate (analysis model)."""

    name = "structure"
    objectives = ()

    def evaluate(self, design, req):
        c, phys = req.constraints or {}, req.section("physics")
        lay = design["layout"]
        solid = 1 - lay.get("open_pct", 0) / 100
        t = design["params"]["plate_t"]
        E = float(req.calibrated("structure.E_MPa", phys.get("E_MPa", 2340)))
        nu = float(phys.get("nu", 0.36))
        w = _plate_deflection(float(c.get("fingertip_N", 10)), RB, t, E, nu, solid)
        s = _plate_stress(float(c.get("hard_push_N", 30)), RB, t, nu, solid)
        allow = float(phys.get("allowable_MPa", 20.0))
        v = max(0.0, w - float(c.get("max_fingertip_disp_mm", 0.5))) + max(0.0, s - allow) / allow
        return {
            "objectives": [],
            "violation": v,
            "metrics": {"fingertip_mm": round(w, 3), "hard_push_MPa": round(s, 1)},
            "uncertainties": {"structure": "Closed-form clamped plate, D scaled by solid fraction². Not FEA; ranks and screens."},
        }


class PrintRules(Evaluator):
    """Hard limits from requirements.yaml: rib, rim, opening floor, hole count."""

    name = "print-rules"
    objectives = ()

    def evaluate(self, design, req):
        lay = design["layout"]
        if not lay.get("n"):
            return {"objectives": [], "violation": 10.0, "metrics": {"feasible": False}}
        v = 0.0
        v += max(0.0, _con(req, "min_strut_mm", 1.5) - lay["rib_min"])
        v += max(0.0, _con(req, "min_rim_mm", 1.35) - lay["edge_min"])
        v += max(0.0, _con(req, "opening_floor_mm", 4.0) - lay["inscribed"]["min"])
        v += max(0.0, 6 - lay["n"]) * 0.5
        return {
            "objectives": [],
            "violation": v,
            "metrics": {"rib_min_mm": lay["rib_min"], "edge_min_mm": lay["edge_min"], "feasible": v <= 0},
            "uncertainties": {"stiffness": "Flat 2.2 mm plate; fingertip stiffness is not modeled in this round."},
        }


# ------------------------------------------------------------------ 3-D export and preview
def plate_field(holes, p: PlateParams, h):
    """Signed-distance field of the plate, flange and collar (<0 in material)."""
    K_TOP, K_BOT = 0.6, 0.9
    xs = np.arange(-23.45, 23.45 + 1e-9, h)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Rr = np.hypot(X, Y)
    hf = polygon_field(X, Y, holes, near=Rr < RB + 0.5)
    zs = np.arange(-8.9, 0.3 + 1e-9, h)
    F = np.empty((len(xs), len(xs), len(zs)), np.float32)
    for k, z in enumerate(zs):
        plate = mx(smax(z, hf, K_TOP), smax(-p.plate_t - z, hf, K_BOT), Rr - (RB + 0.3))
        flange = mx(z, -FL_T - z, Rr - FL_R, (RB + 0.1) - Rr)
        collar = mx(Rr - C_OD, RB - Rr, z + 1.0, Z_BOT - z)
        U = smin(np.minimum(flange, collar), plate, 0.8)
        lead = ((Rr - C_OD) + (Z_BOT + LEAD - z)) / np.sqrt(2)
        E = np.minimum(mx(Rr - FL_R, z, -FL_T - z), mx(Rr - C_OD, z, Z_BOT - z, lead))
        F[:, :, k] = np.maximum(U, E)
    return F, xs, zs


class HairCatcher:
    default_design = "pebble-plate"

    def generator(self, req):
        return PebblePlate()

    def evaluators(self, req):
        return [Drainage(), Capture(), Structure(), PrintRules()]

    def analyze(self, req):
        return analyze(req)

    def export(self, design, out_dir, h=0.1, target_faces=300_000):
        """installed.stl, print.stl (top face on the bed) and a mesh report."""
        from pathlib import Path

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        p = PlateParams(**design["params"])
        F, xs, zs = plate_field(design["holes"], p, h)
        ovh = unsupported_area(F, zs, h, height=8.6)
        m = mesh_field(F, (xs[0], xs[0], zs[0]), h, target_faces=target_faces)
        del F
        m.export(out / "installed.stl")
        mp = print_orientation(m)
        mp.export(out / "print.stl")
        sec = m.section(plane_origin=[0, 0, -4.5], plane_normal=[0, 0, 1])
        rr = np.hypot(*sec.vertices[:, :2].T)
        rep = mesh_report(mp)
        rep.update(collar_OD=round(float(2 * rr.max()), 3), collar_ID=round(float(2 * rr.min()), 3),
                   grid_mm=h, unsupported={k: v for k, v in ovh.items() if k != "per_layer_mm2"})
        return rep

    def preview(self, design, png):
        """Top view: flange, bore and the pebble holes, to scale."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, Polygon as MPoly

        fig, ax = plt.subplots(figsize=(4, 4), dpi=150)
        ax.add_patch(Circle((0, 0), FL_R, color="#e9e4da"))
        ax.add_patch(Circle((0, 0), RB, fill=False, ls="--", lw=0.6, color="#b9b2a5"))
        for hole in design["holes"]:
            ax.add_patch(MPoly(np.asarray(hole.exterior.coords), closed=True, color="#3b4a5a"))
        ax.set_xlim(-FL_R - 1, FL_R + 1)
        ax.set_ylim(-FL_R - 1, FL_R + 1)
        ax.set_aspect("equal")
        ax.axis("off")
        lay = design["layout"]
        if lay.get("n"):
            ax.set_title(f"{lay['n']} holes, {lay['inscribed']['min']}–{lay['inscribed']['max']} mm, "
                         f"{lay['open_pct']}% open", fontsize=8)
        fig.tight_layout()
        fig.savefig(png)
        plt.close(fig)
        return png


MODEL = HairCatcher()
