"""Generative drain grate: a spacing field, Voronoi cells, a printable cone.

The search variables are the seed layout and the strut section, not a
hand-placed hole pattern. Seeds sit on a phyllotaxis spiral whose radius
is warped by an exponent (denser at the center or at the rim) and a
3-fold harmonic, which is a low-dimensional density field. Each seed's
cell is inset by half the local strut width. The solid is the collar
disc minus those openings, carried on a 45° cone so the part prints
flange-down with no internal floor.

Scoring uses gendesign.flow2d and gendesign.stiffness. The mesh is built
from the same openings, so the STL is the geometry that was scored.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

GENE_NAMES = (
    "n_seeds",
    "exponent",
    "phase",
    "jitter",
    "strut",
    "flare",
    "thickness",
    "harm",
)

# (name, lo, hi). n_seeds is rounded. exponent 0.5 is uniform in area.
BOUNDS = (
    (8.0, 16.0),
    (0.34, 0.78),
    (0.0, 2.0 * math.pi),
    (0.0, 0.55),
    (1.30, 2.20),
    (0.0, 0.50),
    (1.80, 2.80),
    (-0.22, 0.22),
)


def fit_from_requirements(req: dict) -> dict:
    """Measured interface plus the physics knobs. Missing keys keep defaults."""
    fit = dict(req.get("fit") or {})
    rules = dict(req.get("constraints") or {})
    phys = dict(req.get("physics") or {})
    ref = dict(req.get("reference_smooth_v2") or {})
    shrink = float(fit.get("shrink", 0.003))
    collar_od = float(fit.get("collar_od_print_mm", fit.get("collar_od_print", 35.10)))
    wall = float(fit.get("collar_wall_mm", 1.6))
    r_loc = collar_od * (1.0 + shrink) / 2.0
    flange_d = float(fit.get("flange_diameter_mm", 46.0))
    return {
        "shrink": shrink,
        "collar_od_print": collar_od,
        "collar_wall": wall,
        "r_loc": r_loc,
        "r_in": r_loc - wall,
        "r_flange": flange_d / 2.0,
        "flange_d": flange_d,
        "flange_t": float(fit.get("flange_thickness_mm", 1.6)),
        "lead_in": float(fit.get("lead_in_mm", 0.7)),
        "collar_engagement": float(fit.get("collar_engagement_mm", 10.2)),
        "max_insert": float(rules.get("max_insert_mm", 18.0)),
        "max_ball": float(rules.get("max_ball_mm", 12.0)),
        "min_strut": float(rules.get("min_strut_mm", 1.25)),
        "rim": float(rules.get("min_rim_mm", 1.35)),
        # 47° from horizontal leaves the faceted mesh under a 45° overhang.
        "cone_deg": float(rules.get("cone_angle_deg", 47.0)),
        "film_gap": float(rules.get("film_gap_mm", 2.7)),
        "film_full": float(rules.get("film_full_mm", 4.0)),
        "max_disp": float(rules.get("max_fingertip_disp_mm", 1.5)),
        "finger_N": float(rules.get("fingertip_N", phys.get("fingertip_N", 10.0))),
        "push_N": float(rules.get("hard_push_N", phys.get("hard_push_N", 30.0))),
        "head_mm": float(phys.get("head_mm", 5.0)),
        "cd": float(phys.get("cd", 0.61)),
        "E": float(phys.get("E_MPa", 2340.0)),
        "nu": float(phys.get("nu", 0.36)),
        "print_flow": float(phys.get("flow_proxy_mm3_s", 8.0)),
        "layer_h": float(phys.get("layer_h_mm", 0.20)),
        "layer_s": float(phys.get("layer_overhead_s", 1.5)),
        "v2_ball": float(ref.get("max_ball_mm", 8.6)),
        "v2_strut": float(ref.get("min_strut_mm", 1.8)),
        "v2_open_pct": float(ref.get("open_area_pct", 50.54)),
        "v2_volume": float(ref.get("volume_mm3", 4304.4)),
    }


def decode(x, fit) -> dict:
    x = np.asarray(x, dtype=float).ravel()
    d = {name: float(np.clip(x[i], BOUNDS[i][0], BOUNDS[i][1])) for i, name in enumerate(GENE_NAMES)}
    d["n_seeds"] = float(np.clip(int(round(d["n_seeds"])), 6, 18))
    d["strut"] = max(d["strut"], fit["min_strut"])
    # The cone depth plus the wall has to stay inside the measured bore.
    slope = math.tan(math.radians(fit["cone_deg"]))
    t_cap = fit["max_insert"] - fit["r_in"] * slope + fit["flange_t"] - 0.15
    d["thickness"] = float(min(d["thickness"], max(1.6, t_cap)))
    return d


def z_top(r, fit):
    r = np.asarray(r, dtype=float)
    drop = (fit["r_in"] - r) * math.tan(math.radians(fit["cone_deg"]))
    return fit["flange_t"] - drop


def z_bot(r, fit, thickness):
    return z_top(r, fit) - thickness


def insert_depth(fit, thickness) -> float:
    """Deepest point below the flange seat (z = 0)."""
    return float(-z_bot(0.0, fit, thickness))


def print_height(fit, thickness) -> float:
    return float(fit["flange_t"] - z_bot(0.0, fit, thickness))


def place_seeds(d, fit) -> np.ndarray:
    """Phyllotaxis warped by the radial density exponent and a 3-fold term."""
    n = int(d["n_seeds"])
    golden = math.pi * (3.0 - math.sqrt(5.0))
    R = fit["r_in"] - fit["rim"] - 0.3
    pts = []
    for i in range(n):
        u = (i + 0.5) / n
        r = R * (u ** d["exponent"])
        th = d["phase"] + i * golden
        r *= 1.0 + d["harm"] * math.cos(3.0 * th)
        th = th + d["jitter"] * 0.55 * math.sin(1.7 * i + d["phase"])
        r = float(np.clip(r, 0.0, R))
        pts.append((r * math.cos(th), r * math.sin(th)))
    min_sep = d["strut"] + 0.90 * fit["film_gap"]
    return _separate(np.asarray(pts, dtype=float), min_sep, R)


def _separate(seeds, min_sep, R):
    kept = []
    for p in seeds:
        r = float(np.hypot(p[0], p[1]))
        if r > R and r > 1e-9:
            p = p * (R / r)
        if all(float(np.hypot(*(p - q))) >= min_sep for q in kept):
            kept.append(p)
    if not kept:
        return np.zeros((1, 2))
    return np.asarray(kept, dtype=float)


def _local_width(d, fit, radius) -> float:
    return float(d["strut"] * (1.0 + d["flare"] * np.clip(radius / fit["r_in"], 0.0, 1.0)))


def opening_polygons(seeds, d, fit):
    """Voronoi cells inset by the local strut half-width, clipped inside the rim."""
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import voronoi_diagram

    R = fit["r_in"]
    inner = Point(0.0, 0.0).buffer(R - fit["rim"], quad_segs=16)
    seeds = np.asarray(seeds, dtype=float)
    if len(seeds) == 0:
        return []
    if len(seeds) == 1:
        w = _local_width(d, fit, 0.0)
        hole = inner.buffer(-0.5 * w)
        return [hole] if (not hole.is_empty and hole.area > 0.8) else []
    diagram = voronoi_diagram(MultiPoint(list(map(tuple, seeds))), envelope=Point(0, 0).buffer(R * 3))
    holes = []
    geoms = list(getattr(diagram, "geoms", [diagram]))
    for cell in geoms:
        if cell.is_empty or cell.geom_type != "Polygon":
            continue
        rp = cell.representative_point()
        p = np.array([rp.x, rp.y])
        i = int(np.argmin(np.sum((seeds - p) ** 2, axis=1)))
        w = _local_width(d, fit, float(np.hypot(*seeds[i])))
        eroded = cell.buffer(-0.5 * w, join_style=2, quad_segs=2)
        if eroded.is_empty:
            continue
        hole = eroded.intersection(inner)
        pieces = list(hole.geoms) if hole.geom_type == "MultiPolygon" else ([hole] if hole.geom_type == "Polygon" else [])
        for g in pieces:
            if g.area >= 0.8:
                holes.append(g.buffer(0))
    return holes


def rasterize(holes, fit, pitch: float):
    """Boolean masks of the openings on the grate disc."""
    from shapely import contains_xy
    from shapely.ops import unary_union

    R = fit["r_in"]
    xs = np.arange(-R - pitch, R + pitch * 1.5, pitch)
    X, Y = np.meshgrid(xs, xs, indexing="xy")
    rad = np.hypot(X, Y)
    domain = rad <= R + 1e-9
    void = np.zeros(domain.shape, dtype=bool)
    if holes:
        uni = unary_union(holes)
        if not uni.is_empty:
            void = np.asarray(contains_xy(uni, X, Y), dtype=bool)
    void &= domain & (rad <= (R - fit["rim"] + 1e-9))
    return void, domain, xs


def ridge_graph(seeds, d, fit):
    """Voronoi ridges clipped to the disc, with the local strut width."""
    from scipy.spatial import Voronoi

    seeds = np.asarray(seeds, dtype=float)
    R = fit["r_in"]
    nreal = len(seeds)
    if nreal == 0:
        return np.zeros((0, 2)), [], [], np.zeros(0, dtype=bool)
    th = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    ghosts = np.stack([2.8 * R * np.cos(th), 2.8 * R * np.sin(th)], axis=1)
    pts = np.vstack([seeds, ghosts]) if nreal >= 2 else np.vstack([seeds, ghosts])
    if nreal < 2:
        # One seed: a single radial member out to the rim so the plate is supported.
        w = _local_width(d, fit, 0.0)
        nodes = np.array([[0.0, 0.0], [R - 0.05, 0.0]])
        fixed = np.array([False, True])
        return nodes, [(0, 1)], [w], fixed
    try:
        vor = Voronoi(pts)
    except Exception:
        return np.zeros((0, 2)), [], [], np.zeros(0, dtype=bool)

    Rclip = R - 0.04

    def clip_seg(p, q):
        p = np.asarray(p, float)
        q = np.asarray(q, float)
        direction = q - p
        A = float(np.dot(direction, direction))
        B = float(2 * np.dot(p, direction))
        C = float(np.dot(p, p) - Rclip * Rclip)
        ts = [0.0, 1.0]
        disc = B * B - 4 * A * C
        if A > 1e-14 and disc >= 0:
            s = math.sqrt(disc)
            for t in ((-B - s) / (2 * A), (-B + s) / (2 * A)):
                if -1e-8 <= t <= 1 + 1e-8:
                    ts.append(float(np.clip(t, 0.0, 1.0)))
        ts = sorted(set(np.round(ts, 7)))
        out = []
        for t0, t1 in zip(ts, ts[1:]):
            mid = p + 0.5 * (t0 + t1) * direction
            if float(np.dot(mid, mid)) <= Rclip * Rclip + 1e-4:
                out.append((p + t0 * direction, p + t1 * direction))
        return out

    segments = []
    for (va, vb), (i, j) in zip(vor.ridge_vertices, vor.ridge_points):
        if i >= nreal and j >= nreal:
            continue
        if va >= 0 and vb >= 0:
            p, q = vor.vertices[va], vor.vertices[vb]
        else:
            finite = vb if va < 0 else va
            if finite < 0:
                continue
            p = vor.vertices[finite]
            mid = 0.5 * (pts[i] + pts[j])
            diff = pts[j] - pts[i]
            direction = np.array([-diff[1], diff[0]], dtype=float)
            nrm = float(np.linalg.norm(direction))
            if nrm < 1e-9:
                continue
            direction /= nrm
            if float(np.dot(p - mid, direction)) < 0:
                direction = -direction
            q = p + direction * (4.0 * R)
        ws = []
        if i < nreal:
            ws.append(_local_width(d, fit, float(np.hypot(*seeds[i]))))
        if j < nreal:
            ws.append(_local_width(d, fit, float(np.hypot(*seeds[j]))))
        w = float(np.mean(ws)) if ws else d["strut"]
        for a, b in clip_seg(p, q):
            if float(np.linalg.norm(b - a)) >= 0.45:
                segments.append((a, b, w))

    nodes = []

    def nid(p, tol=0.22):
        for i, q in enumerate(nodes):
            if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= tol * tol:
                return i
        nodes.append(np.asarray(p, float))
        return len(nodes) - 1

    edges, widths, seen = [], [], set()
    for a, b, w in segments:
        ia, ib = nid(a), nid(b)
        if ia == ib:
            continue
        key = (min(ia, ib), max(ia, ib))
        if key in seen:
            continue
        seen.add(key)
        edges.append(key)
        widths.append(w)
    if not nodes:
        return np.zeros((0, 2)), [], [], np.zeros(0, dtype=bool)
    nodes_a = np.asarray(nodes, float)
    fixed = np.hypot(nodes_a[:, 0], nodes_a[:, 1]) >= (R - fit["rim"] - 0.2)
    return nodes_a, edges, widths, fixed


def collar_flange_volume(fit) -> float:
    r_in, r_loc, r_fl = fit["r_in"], fit["r_loc"], fit["r_flange"]
    zt = fit["flange_t"]
    zc = -fit["collar_engagement"]
    collar = math.pi * (r_loc**2 - r_in**2) * (zt - zc)
    lead = fit["lead_in"]
    collar -= 0.5 * lead**2 * 2.0 * math.pi * (r_loc - lead / 3.0)
    flange = math.pi * (r_fl**2 - r_loc**2) * zt
    return float(collar + flange)


def evaluate_design(d, fit, seeds=None, pitch=0.16, with_mesh=False) -> dict:
    """Score one decoded design. Objectives are maximized."""
    from gendesign.flow2d import drainage_report
    from gendesign.stiffness import grillage_deflection

    if seeds is None:
        seeds = place_seeds(d, fit)
    holes = opening_polygons(seeds, d, fit)
    void, domain, _xs = rasterize(holes, fit, pitch)
    flow = drainage_report(
        void, domain, pitch,
        head_mm=fit["head_mm"], cd=fit["cd"],
        film_gap_mm=fit["film_gap"], film_full_mm=fit["film_full"],
    )
    nodes, edges, widths, fixed = ridge_graph(seeds, d, fit)
    # Drop cells from the flow dict before it lands in JSON later; keep a short copy.
    cells = flow.pop("cells")
    stiff = grillage_deflection(
        nodes, edges, widths, d["thickness"],
        E=fit["E"], nu=fit["nu"], load_N=fit["finger_N"],
        load_xy=(0.0, 0.0), load_radius_mm=5.0, fixed_mask=fixed,
    )
    wfield = stiff.pop("w_mm", None)
    solid_area = float((domain & ~void).sum()) * pitch * pitch
    grate_vol = solid_area * d["thickness"]
    volume = grate_vol + collar_flange_volume(fit)
    depth = insert_depth(fit, d["thickness"])
    height = print_height(fit, d["thickness"])
    # Linear model: a harder push is the same stiffness.
    push_disp = (fit["push_N"] / fit["finger_N"]) * stiff["max_disp_mm"] if stiff["connected"] else float("inf")
    time_s = volume / fit["print_flow"] + (height / fit["layer_h"]) * fit["layer_s"]

    violation = 0.0
    if flow["max_ball_mm"] > fit["max_ball"]:
        violation += flow["max_ball_mm"] - fit["max_ball"]
    if flow["n_openings"] < 1 or flow["max_ball_mm"] < fit["film_gap"]:
        # No opening large enough to break a water film.
        violation += fit["film_gap"] - flow["max_ball_mm"] + 0.5
    if not stiff["connected"]:
        violation += 8.0
    elif stiff["max_disp_mm"] > fit["max_disp"]:
        violation += stiff["max_disp_mm"] - fit["max_disp"]
    if depth > fit["max_insert"]:
        violation += depth - fit["max_insert"]
    if d["strut"] < fit["min_strut"] - 1e-6:
        violation += fit["min_strut"] - d["strut"]

    capture = fit["max_ball"] - flow["max_ball_mm"]
    k = float(stiff["stiffness_N_per_mm"]) if stiff["connected"] and math.isfinite(stiff["max_disp_mm"]) else 0.0
    objectives = [float(flow["flow_mm3_s"]), float(capture), float(k), float(-volume)]
    info = {
        "flow_mm3_s": flow["flow_mm3_s"],
        "flow_cm3_s": flow["flow_cm3_s"],
        "capture_mm": capture,
        "stiffness_N_per_mm": k,
        "volume_mm3": volume,
        "grate_volume_mm3": grate_vol,
        "open_area_pct": 100.0 * flow["open_area_frac"],
        "open_area_mm2": flow["open_area_mm2"],
        "max_ball_mm": flow["max_ball_mm"],
        "min_ball_mm": flow["min_ball_mm"],
        "n_openings": flow["n_openings"],
        "film_area_pct_of_open": 100.0 * flow["film_area_frac"],
        "film_area_mm2": flow["film_area_mm2"],
        "partial_area_mm2": flow["partial_area_mm2"],
        "fingertip_disp_mm": None if not stiff["connected"] else stiff["max_disp_mm"],
        "hard_push_disp_mm": None if not stiff["connected"] else push_disp,
        "connected": bool(stiff["connected"]),
        "n_beams": int(stiff["n_edges"]),
        "n_seeds_placed": int(len(seeds)),
        "strut_mm": d["strut"],
        "strut_at_rim_mm": _local_width(d, fit, fit["r_in"]),
        "thickness_mm": d["thickness"],
        "insert_depth_mm": depth,
        "print_height_mm": height,
        "print_time_proxy_s": time_s,
        "print_time_proxy_min": time_s / 60.0,
        "violation": violation,
        "feasible": violation <= 1e-8,
        "cone_deg": fit["cone_deg"],
        "objectives": objectives,
    }
    out = {
        "objectives": objectives,
        "violation": violation,
        "info": info,
        "seeds": seeds,
        "holes": holes,
        "design": d,
        "flow": flow,
        "stiff": stiff,
    }
    if with_mesh:
        out["mesh_use"], out["mesh_print"] = build_meshes(holes, fit, d["thickness"])
    # cells were only needed if a caller wants them; keep the count.
    info["n_cells_scored"] = len(cells)
    return out


def evaluate_vector(x, fit, pitch=0.16) -> dict:
    d = decode(x, fit)
    try:
        ev = evaluate_design(d, fit, pitch=pitch)
    except Exception as exc:
        return {"objectives": [-1e6, -1e6, -1e6, -1e9], "violation": 100.0, "info": {"error": str(exc), "feasible": False}}
    return {"objectives": ev["objectives"], "violation": ev["violation"], "info": ev["info"]}


def _signed_area(xy) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _densify_ring(coords, max_seg):
    coords = np.asarray(coords, float)
    if len(coords) > 1 and np.allclose(coords[0], coords[-1]):
        coords = coords[:-1]
    out = []
    n = len(coords)
    for i in range(n):
        a = coords[i]
        b = coords[(i + 1) % n]
        dist = float(np.linalg.norm(b - a))
        steps = max(1, int(math.ceil(dist / max_seg)))
        for k in range(steps):
            out.append(a + (b - a) * (k / steps))
    return np.asarray(out, float)


def _edge_key(u, v):
    return (u, v) if u < v else (v, u)


def _subdivide(tris, pts, max_edge, frozen=()):
    """Split every long edge on every triangle that uses it, so no T-junctions.

    Collinear points are added only after earcut. Earcut drops hole edges
    when the input already has collinear vertices, so rings stay coarse
    here and this pass does the refinement. `frozen` edges (the outer
    circle, which the collar shares) are not split. The returned split
    map rebuilds hole walls from the refined loops.
    """
    pts = [np.asarray(p, float) for p in pts]
    tris = [tuple(int(v) for v in t) for t in tris]
    splits = {}
    frozen_keys = {_edge_key(a, b) for a, b in frozen}

    def mid(a, b):
        key = _edge_key(a, b)
        if key not in splits:
            splits[key] = len(pts)
            pts.append(0.5 * (pts[a] + pts[b]))
        return splits[key]

    for _ in range(8):
        long = set()
        seen = set()
        for a, b, c in tris:
            for u, v in ((a, b), (b, c), (c, a)):
                key = _edge_key(u, v)
                if key in seen or key in frozen_keys:
                    seen.add(key)
                    continue
                seen.add(key)
                if float(np.linalg.norm(pts[u] - pts[v])) > max_edge:
                    long.add(key)
        if not long or len(pts) > 40000:
            break
        nxt = []
        for a, b, c in tris:
            edges = ((a, b), (b, c), (c, a))
            split = [e for e in edges if _edge_key(*e) in long]
            if len(split) == 0:
                nxt.append((a, b, c))
            elif len(split) == 1:
                u, v = split[0]
                m = mid(u, v)
                opp = next(x for x in (a, b, c) if x != u and x != v)
                nxt.append((u, m, opp))
                nxt.append((m, v, opp))
            elif len(split) == 2:
                short = next(e for e in edges if _edge_key(*e) not in long)
                u, v = short
                opp = next(x for x in (a, b, c) if x != u and x != v)
                mu, mv = mid(opp, u), mid(opp, v)
                nxt.append((opp, mu, mv))
                nxt.append((mu, u, v))
                nxt.append((mu, v, mv))
            else:
                mab, mbc, mca = mid(a, b), mid(b, c), mid(c, a)
                nxt.append((a, mab, mca))
                nxt.append((b, mbc, mab))
                nxt.append((c, mca, mbc))
                nxt.append((mab, mbc, mca))
        tris = nxt
    return tris, np.asarray(pts, float), splits


def _refined_loop(indices, splits):
    """Original ring, with every split midpoint inserted in order."""

    def chain(a, b):
        key = _edge_key(a, b)
        if key not in splits:
            return [a]
        m = splits[key]
        return chain(a, m) + chain(m, b)

    loop = []
    m = len(indices)
    for i in range(m):
        loop.extend(chain(indices[i], indices[(i + 1) % m]))
    return loop


def build_meshes(holes, fit, thickness, n_outer=168):
    """Watertight use-orientation mesh and the flange-on-bed print mesh."""
    import mapbox_earcut as earcut
    import trimesh

    R = fit["r_in"]
    theta = np.linspace(0, 2 * np.pi, n_outer, endpoint=False)
    outer = np.stack([R * np.cos(theta), R * np.sin(theta)], axis=1)

    hole_rings = []
    for h in holes:
        polys = [h] if h.geom_type == "Polygon" else list(getattr(h, "geoms", []))
        for poly in polys:
            if poly.geom_type != "Polygon" or poly.area < 0.5:
                continue
            # Keep the Voronoi vertices. Adding collinear points here makes
            # earcut drop hole edges; refinement happens after the triangulate.
            ring = _densify_ring(np.asarray(poly.exterior.coords), 1e9)
            if _signed_area(ring) > 0:
                ring = ring[::-1]
            if len(ring) >= 3:
                hole_rings.append(ring)

    chunks = [outer]
    ends = [len(outer)]
    for ring in hole_rings:
        chunks.append(ring)
        ends.append(ends[-1] + len(ring))
    boundary = np.vstack(chunks)
    frozen = []
    start = 0
    for chunk in chunks:
        m = len(chunk)
        for i in range(m):
            frozen.append((start + i, start + (i + 1) % m))
        start += m
    raw = earcut.triangulate_float64(
        np.ascontiguousarray(boundary, dtype=np.float64),
        np.asarray(ends, dtype=np.uint32),
    )
    tris = raw.reshape(-1, 3)
    n_boundary = len(boundary)
    # Only the outer circle is frozen: the collar is welded to those vertices.
    outer_frozen = frozen[:n_outer]
    tris, pts2, splits = _subdivide(tris, boundary, 0.9, outer_frozen)
    # Boundary indices are unchanged by subdivision (new points are appended).
    r = np.hypot(pts2[:, 0], pts2[:, 1])
    zt = np.asarray(z_top(r, fit), dtype=float)
    zb = zt - float(thickness)
    npts = len(pts2)
    verts = np.vstack([
        np.column_stack([pts2[:, 0], pts2[:, 1], zt]),
        np.column_stack([pts2[:, 0], pts2[:, 1], zb]),
    ])
    faces = []
    for a, b, c in tris:
        faces.append((int(a), int(b), int(c)))
        faces.append((npts + int(c), npts + int(b), npts + int(a)))

    def add_wall(indices):
        """Vertical-ish wall. Outward hint points to the right of the walk, in xy."""
        m = len(indices)
        for i in range(m):
            a = indices[i]
            b = indices[(i + 1) % m]
            pa, pb = verts[a], verts[b]
            direction = pb[:2] - pa[:2]
            # Right of the walk (into a CW hole, or outward on a CCW outer).
            hint_xy = np.array([direction[1], -direction[0]], dtype=float)
            nrm = float(np.linalg.norm(hint_xy))
            if nrm < 1e-9:
                continue
            hint = np.array([hint_xy[0], hint_xy[1], 0.0])
            ia, ib = a, b
            ja, jb = npts + a, npts + b
            # Candidate quad a, b, bot b, bot a.
            nvec = np.cross(verts[ib] - verts[ia], verts[jb] - verts[ia])
            if float(np.dot(nvec, hint)) >= 0:
                faces.append((ia, ib, jb))
                faces.append((ia, jb, ja))
            else:
                faces.append((ia, jb, ib))
                faces.append((ia, ja, jb))

    # Hole rings only. The outer cylinder is an internal face against the collar.
    offset = n_outer
    for ring in hole_rings:
        loop = _refined_loop(list(range(offset, offset + len(ring))), splits)
        add_wall(loop)
        offset += len(ring)

    # Collar + flange, sharing the two circles at r = R, z = zt(R) and z = zb(R).
    zt_rim = float(z_top(R, fit))
    zb_rim = zt_rim - float(thickness)
    zc = -float(fit["collar_engagement"])
    lead = float(fit["lead_in"])
    r_loc, r_fl = fit["r_loc"], fit["r_flange"]
    # CCW in the (r, z) plane with the material on the left. The edge from
    # the top circle back down to the bottom circle is the grate's job.
    profile = [
        (R, zb_rim),
        (R, zc),
        (r_loc - lead, zc),
        (r_loc, zc + lead),
        (r_loc, 0.0),
        (r_fl, 0.0),
        (r_fl, zt_rim),
        (R, zt_rim),
    ]
    # Vertex ids per (angle, profile index). Ends reuse the grate rings.
    prof_id = [[None] * len(profile) for _ in range(n_outer)]
    for i, th in enumerate(theta):
        c, s = math.cos(th), math.sin(th)
        # outer ring of the grate is the first n_outer boundary points, top then +npts bottom.
        prof_id[i][0] = npts + i  # bottom circle
        prof_id[i][-1] = i        # top circle
        for k in range(1, len(profile) - 1):
            rr, zz = profile[k]
            prof_id[i][k] = len(verts)
            verts = np.vstack([verts, [[rr * c, rr * s, zz]]])

    def face_hint(i, k):
        th = theta[i]
        r0, z0 = profile[k]
        r1, z1 = profile[k + 1]
        dr, dz = r1 - r0, z1 - z0
        # Outward = opposite of "left" of the walk. Left of (dr, dz) is (-dz, dr).
        out_r, out_z = dz, -dr
        # Use the radial direction at the segment midpoint angle.
        return np.array([out_r * math.cos(th), out_r * math.sin(th), out_z], dtype=float)

    for i in range(n_outer):
        j = (i + 1) % n_outer
        for k in range(len(profile) - 1):
            a = prof_id[i][k]
            b = prof_id[j][k]
            c = prof_id[j][k + 1]
            d = prof_id[i][k + 1]
            hint = face_hint(i, k)
            nvec = np.cross(verts[b] - verts[a], verts[d] - verts[a])
            if float(np.dot(nvec, hint)) >= 0:
                faces.append((a, b, d))
                faces.append((b, c, d))
            else:
                faces.append((a, d, b))
                faces.append((d, c, b))

    mesh = trimesh.Trimesh(vertices=verts, faces=np.asarray(faces, dtype=np.int64), process=False)
    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    if mesh.volume < 0:
        mesh.invert()
    printed = mesh.copy()
    # 180° about x: flange top (the highest use-z of the flange) goes to the bed.
    printed.vertices[:, 1] *= -1
    printed.vertices[:, 2] *= -1
    printed.vertices[:, 2] -= printed.vertices[:, 2].min()
    return mesh, printed


def save_stl_pair(holes, fit, thickness, directory, prefix):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    use, printed = build_meshes(holes, fit, thickness)
    use_path = directory / f"{prefix}-use.stl"
    print_path = directory / f"{prefix}-print.stl"
    use.export(use_path)
    printed.export(print_path)
    return use, printed, use_path, print_path


def render_views(mesh, path_top, path_34, title=None):
    """PyVista renders. Returns True on success."""
    import pyvista as pv

    pv.OFF_SCREEN = True
    tm = mesh.copy()
    # Center the camera on the part.
    pv_mesh = pv.wrap(tm)
    try:
        pv_mesh = pv_mesh.compute_normals(split_vertices=True, feature_angle=30)
    except Exception:
        pass
    part = dict(color="#E4E0D8", specular=0.45, specular_power=40, ambient=0.12, diffuse=0.75, smooth_shading=True)

    def plotter():
        p = pv.Plotter(off_screen=True, window_size=(1400, 1050))
        p.set_background("#ECE8E1")
        return p

    path_top, path_34 = Path(path_top), Path(path_34)
    path_top.parent.mkdir(parents=True, exist_ok=True)
    p = plotter()
    p.add_mesh(pv_mesh, **part)
    p.camera_position = [(0, 0, 120), (0, 0, 0), (0, 1, 0)]
    p.screenshot(str(path_top))
    p.close()
    p = plotter()
    p.add_mesh(pv_mesh, **part)
    p.camera_position = [(70, -78, 48), (0, 0, -4), (0, 0, 1)]
    p.screenshot(str(path_34))
    p.close()
    return True


def save_plan_png(path, holes, fit, d, caption):
    """Top-view preview used for the iteration contact sheet."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon as MplPolygon

    fig, ax = plt.subplots(figsize=(4.2, 4.6), dpi=110)
    fig.patch.set_facecolor("#F7F4EF")
    ax.set_facecolor("#F7F4EF")
    ax.add_patch(Circle((0, 0), fit["r_flange"], facecolor="#E7E2D8", edgecolor="none"))
    ax.add_patch(Circle((0, 0), fit["r_loc"], facecolor="#D5D0C6", edgecolor="none"))
    ax.add_patch(Circle((0, 0), fit["r_in"], facecolor="#4E6A78", edgecolor="none"))
    # Solid cone reads as the lighter disc; openings are the dark "water".
    ax.add_patch(Circle((0, 0), fit["r_in"] - fit["rim"], facecolor="#E6E1D6", edgecolor="none"))
    for h in holes:
        polys = [h] if h.geom_type == "Polygon" else list(getattr(h, "geoms", []))
        for poly in polys:
            xy = np.asarray(poly.exterior.coords)
            ax.add_patch(MplPolygon(xy, closed=True, facecolor="#3E5966", edgecolor="none"))
    ax.set_aspect("equal")
    lim = fit["r_flange"] + 1.2
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.axis("off")
    ax.set_title(caption, fontsize=9, color="#222", pad=6)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def smooth_v2_reference(fit, pitch=0.12) -> dict:
    """Score the published 7-hole bowl with the same orifice model and a grillage of its webs.

    The bowl is a shell. This grillage is the flat plan of the webs, so it
    understates the real dish. Flow ignores the dish too: it is the same
    sharp-orifice head used on the cones.
    """
    from gendesign.flow2d import drainage_report
    from gendesign.stiffness import grillage_deflection

    hole_d = fit["v2_ball"]
    strut = fit["v2_strut"]
    pitch_h = hole_d + strut
    hr = hole_d / 2.0
    rot = math.radians(30.0)
    R = fit["r_in"]
    xs = np.arange(-R - pitch, R + pitch, pitch)
    X, Y = np.meshgrid(xs, xs, indexing="xy")
    rad = np.hypot(X, Y)
    domain = rad <= R
    void = (X**2 + Y**2) <= hr**2
    for k in range(6):
        a = rot + k * math.pi / 3.0
        void |= (X - pitch_h * math.cos(a)) ** 2 + (Y - pitch_h * math.sin(a)) ** 2 <= hr**2
    void &= domain
    flow = drainage_report(
        void, domain, pitch,
        head_mm=fit["head_mm"], cd=fit["cd"],
        film_gap_mm=fit["film_gap"], film_full_mm=fit["film_full"],
    )
    flow.pop("cells", None)
    nodes = []
    edges = []
    widths = []

    def add_node(p):
        nodes.append(np.asarray(p, float))
        return len(nodes) - 1

    def add_edge(a, b, w=strut):
        edges.append((a, b))
        widths.append(w)

    inner_ids, outer_gap, rim_ids = [], [], []
    for k in range(6):
        a = rot + k * math.pi / 3.0
        am = a + math.pi / 6.0
        A = add_node((hr * math.cos(a), hr * math.sin(a)))
        B = add_node(((pitch_h - hr) * math.cos(a), (pitch_h - hr) * math.sin(a)))
        add_edge(A, B)
        inner_ids.append((A, B))
        gap_r = pitch_h * math.cos(math.pi / 6.0)
        E = add_node((gap_r * math.cos(am), gap_r * math.sin(am)))
        F = add_node(((R - 0.15) * math.cos(am), (R - 0.15) * math.sin(am)))
        add_edge(E, F)
        outer_gap.append(E)
        rim_ids.append(F)
    for k in range(6):
        _A, B = inner_ids[k]
        _A2, B2 = inner_ids[(k + 1) % 6]
        add_edge(B, B2)
        add_edge(B, outer_gap[k])
        add_edge(B2, outer_gap[k])
    nodes_a = np.asarray(nodes, float)
    fixed = np.zeros(len(nodes_a), dtype=bool)
    fixed[rim_ids] = True
    stiff = grillage_deflection(
        nodes_a, edges, widths, 3.0,
        E=fit["E"], nu=fit["nu"], load_N=fit["finger_N"],
        load_xy=(0.0, 0.0), load_radius_mm=5.5, fixed_mask=fixed,
    )
    stiff.pop("w_mm", None)
    return {
        "name": "smooth-v2",
        "open_area_pct_model": 100.0 * flow["open_area_frac"],
        "open_area_pct_published": fit["v2_open_pct"],
        "max_ball_mm_model": flow["max_ball_mm"],
        "max_ball_mm_published": fit["v2_ball"],
        "flow_cm3_s": flow["flow_cm3_s"],
        "flow_mm3_s": flow["flow_mm3_s"],
        "film_area_mm2": flow["film_area_mm2"],
        "fingertip_disp_mm": stiff["max_disp_mm"] if stiff["connected"] else None,
        "stiffness_N_per_mm": stiff["stiffness_N_per_mm"] if stiff["connected"] else 0.0,
        "hard_push_disp_mm": (fit["push_N"] / fit["finger_N"]) * stiff["max_disp_mm"] if stiff["connected"] else None,
        "volume_mm3_published": fit["v2_volume"],
        "strut_mm": strut,
        "thickness_mm": 3.0,
        "connected": bool(stiff["connected"]),
        "note": (
            "Same orifice head and the same beam theory as the cones. "
            "The published open area is 50.54% and the ball is 8.6 mm; "
            "the raster is a check on that. The grillage is the flat web, "
            "not the dished shell, so the real bowl is at least this stiff. "
            "Published volume is the CadQuery solid, 4304 mm3."
        ),
    }


def rebuild(design: dict, out_dir, preview=False):
    """Rebuild a saved generative design.json into STL (+ optional renders)."""
    req = design.get("requirements") or {}
    fit = design.get("fit") or fit_from_requirements(req if req else {"fit": {}, "constraints": {}, "physics": {}})
    # Prefer the fit block stored on the design; fill anything missing from defaults.
    base = fit_from_requirements({"fit": {}, "constraints": {}, "physics": {}})
    base.update({k: v for k, v in fit.items() if not isinstance(v, dict)})
    fit = base
    params = design.get("params") or design.get("design") or {}
    x = [float(params[name]) for name in GENE_NAMES]
    d = decode(x, fit)
    ev = evaluate_design(d, fit, pitch=0.14, with_mesh=False)
    prefix = design.get("prefix") or "basin_guard_gen"
    use, printed, use_path, print_path = save_stl_pair(ev["holes"], fit, d["thickness"], out_dir, prefix)
    files = {"use_stl": str(use_path), "print_stl": str(print_path)}
    if preview:
        top = Path(out_dir) / f"{prefix}-preview-top.png"
        view = Path(out_dir) / f"{prefix}-preview-34.png"
        render_views(use, top, view)
        files["preview_top"] = str(top)
        files["preview_34"] = str(view)
    report = {"measure": ev["info"], "watertight_use": bool(use.is_watertight), "watertight_print": bool(printed.is_watertight)}
    (Path(out_dir) / "rebuild-stats.json").write_text(json.dumps(report, indent=2, default=str))
    return files, report
