#!/usr/bin/env python3
"""Rebuild the winning 7-hole bowl as exact smooth CAD (CadQuery).

Same fit and pattern as the search winner; all visible sharp corners rounded
where printable. Flange seating face stays flat; collar lead-in stays a 45°
chamfer. High-res STL + STEP, then measure, render, slice (no print).
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
from scipy.ndimage import distance_transform_edt, label


from dataclasses import dataclass, asdict, field

OUT = Path(__file__).resolve().parent


@dataclass
class Params:
    """All dimensions in millimetres unless noted."""
    shrink: float = 0.003
    collar_od_print: float = 35.10
    collar_wall: float = 1.6
    flange_diameter: float = 46.0
    flange_thickness: float = 1.6
    lead_in: float = 0.7
    insert_depth: float = 10.21
    dish_depth: float = 9.2
    thickness: float = 3.0
    hole_diameter: float = 8.60
    strut_width: float = 1.80
    hole_rotation_deg: float = 30.0
    fillet_hole_lip: float = 0.60
    fillet_flange_top_outer: float = 0.60
    fillet_bowl_to_flange: float = 0.80
    fillet_bowl_to_collar: float = 0.80
    stl_linear: float = 0.02
    stl_angular: float = 0.03

    @property
    def r_loc(self) -> float:
        return self.collar_od_print * (1.0 + self.shrink) / 2.0

    @property
    def r_in(self) -> float:
        return self.r_loc - self.collar_wall

    @property
    def r_flange(self) -> float:
        return self.flange_diameter / 2.0

    @property
    def hole_r(self) -> float:
        return self.hole_diameter / 2.0

    @property
    def pitch(self) -> float:
        return self.hole_diameter + self.strut_width


# active parameter set (module-level, so the original helpers keep working)
P = Params()


def apply_params(p: Params | None = None):
    """Refresh the module-level geometry constants from a Params object."""
    global P, SHRINK, LOC_OD_PRINT, R_LOC, COLLAR_WALL, R_IN, R_FLANGE
    global FLANGE_T, LEADIN, INSERT, DISH, THICK, HOLE_D, HOLE_R, STRUT, PITCH
    global HOLE_ROT_DEG, F_HOLE_LIP, F_FLANGE_TOP_OUTER, F_BOWL_TO_FLANGE
    global F_BOWL_TO_COLLAR, STL_LINEAR, STL_ANGULAR
    if p is not None:
        P = p
    SHRINK = P.shrink
    LOC_OD_PRINT = P.collar_od_print
    COLLAR_WALL = P.collar_wall
    R_LOC = P.r_loc
    R_IN = P.r_in
    R_FLANGE = P.r_flange
    FLANGE_T = P.flange_thickness
    LEADIN = P.lead_in
    INSERT = P.insert_depth
    DISH = P.dish_depth
    THICK = P.thickness
    HOLE_D = P.hole_diameter
    HOLE_R = P.hole_r
    STRUT = P.strut_width
    PITCH = P.pitch
    HOLE_ROT_DEG = P.hole_rotation_deg
    F_HOLE_LIP = P.fillet_hole_lip
    F_FLANGE_TOP_OUTER = P.fillet_flange_top_outer
    F_BOWL_TO_FLANGE = P.fillet_bowl_to_flange
    F_BOWL_TO_COLLAR = P.fillet_bowl_to_collar
    STL_LINEAR = P.stl_linear
    STL_ANGULAR = P.stl_angular
    return P


# ----- fixed fit (De40, reused) -----
SHRINK = 0.003
LOC_OD_PRINT = 35.10
R_LOC = LOC_OD_PRINT * (1.0 + SHRINK) / 2.0  # 17.60265
COLLAR_WALL = 1.6
R_IN = R_LOC - COLLAR_WALL                   # 16.00265
R_FLANGE = 23.0
FLANGE_T = 1.6
LEADIN = 0.7

# ----- winner geometry -----
INSERT = 10.21
DISH = 9.2
THICK = 3.0
HOLE_D = 8.60
HOLE_R = HOLE_D / 2.0
STRUT = 1.80
PITCH = HOLE_D + STRUT                       # 10.40
# orientation matches the winner's roughly 22.5–30° ring; 30° is symmetric
HOLE_ROT_DEG = 30.0

# ----- fillet / chamfer radii (mm), all reported -----
F_HOLE_LIP = 0.60        # hole top + bottom lips. 0.8 mm would leave only
                         # 0.2 mm of land on a 1.8 mm strut (0.60+0.60=1.20,
                         # 0.60 mm land remains — printable, hair-friendly).
F_FLANGE_TOP_OUTER = 0.60
F_BOWL_TO_FLANGE = 0.80  # convex lip where the 49° bowl meets the flange top
F_BOWL_TO_COLLAR = 0.80  # concave cove under the bowl at the collar ID
# lead-in remains a 0.70 mm 45° CHAMFER, not a fillet
# flange SEAT (z=0, r=R_LOC..R_FLANGE) stays sharp/flat

# tessellation
STL_LINEAR = 0.02        # mm
STL_ANGULAR = 0.03       # rad ≈ 1.7°


def ztop(r: float) -> float:
    r = min(max(r, 0.0), R_IN)
    return FLANGE_T - DISH * (1.0 - (r / R_IN) ** 2)


def zbot(r: float) -> float:
    return ztop(r) - THICK


def hole_centers():
    rot = math.radians(HOLE_ROT_DEG)
    pts = [(0.0, 0.0, HOLE_R)]
    for k in range(6):
        a = rot + k * math.pi / 3.0
        pts.append((PITCH * math.cos(a), PITCH * math.sin(a), HOLE_R))
    return pts


def _parabola_pts(zfun, r0, r1, n=36):
    rs = np.linspace(r0, r1, n)
    return [(float(r), float(zfun(r))) for r in rs]


def _fillet_top_bowl_flange():
    """2-D fillet between flange top (z=FLANGE_T, r>=R_IN) and the bowl
    tangent (~49°). Returns (tangent on bowl, center, tangent on flange)."""
    theta = math.atan(2.0 * DISH / R_IN)  # rim slope from horizontal
    R = F_BOWL_TO_FLANGE
    # center: down from flange, slightly outward of R_IN
    cr = R_IN + R * math.tan(theta / 2.0)
    cz = FLANGE_T - R
    # tangent on flange (horizontal)
    t_fl = (cr, FLANGE_T)
    # tangent on bowl: center minus R * n2, n2=(sin θ, -cos θ)
    t_bowl = (cr - R * math.sin(theta), cz + R * math.cos(theta))
    mid = (cr - R * math.sin(theta / 2.0), cz + R * math.cos(theta / 2.0))
    return t_bowl, mid, t_fl, (cr, cz), theta


def _fillet_underside_bowl_collar():
    """Concave cove at (R_IN, zbot(R_IN)) between vertical collar ID and
    the bowl underside (49°). Center is in the drain void."""
    theta = math.atan(2.0 * DISH / R_IN)
    R = F_BOWL_TO_COLLAR
    v = (R_IN, zbot(R_IN))
    # material normals: collar ID -> +r; bowl bottom -> up-and-in-ish
    # For a CONCAVE corner the fillet center sits in the void (left of the
    # wall and below the bowl).
    # Offset collar ID (r = R_IN - R) and offset bowl (into the void).
    # Bowl bottom unit normal pointing into VOID (down and out): (sin θ, -cos θ)
    # Void is below the bottom surface.
    n_void = (math.sin(theta), -math.cos(theta))
    # Offset of vertical wall into the void: r = R_IN - R
    cr = R_IN - R
    # (C - V) · n_void = R  (C is in the void, distance R from bowl)
    # (cr - R_IN)*sinθ + (cz - v[1])*(-cosθ) = R
    # (-R)*sinθ - (cz - v[1])*cosθ = R
    # -(cz - v[1])*cosθ = R + R sinθ
    # cz - v[1] = -(R*(1+sinθ))/cosθ
    cz = v[1] - R * (1.0 + math.sin(theta)) / math.cos(theta)
    # Actually let me use the two-line formula more carefully.
    # Line 1: r = R_IN (vertical). Void is r < R_IN. Offset: r = R_IN - R. Yes cr = R_IN - R.
    # Line 2: bowl tangent through V, angle θ (dz/dr = tan θ). Void is below.
    # Offset of line 2 into the void by R.
    # I'll recompute cz so distance to the tangent line is R.
    # Tangent line: z - v[1] = tanθ * (r - R_IN)
    #   z - tanθ * r = v[1] - tanθ * R_IN
    # Dist from point (cr,cz) to this line should be R.
    # Line: -tanθ * r + z - (v[1]-tanθ*R_IN) = 0
    # a=-tanθ, b=1, c= -(v[1]-tanθ*R_IN)
    # |a cr + b cz + c| / sqrt(a^2+b^2) = R
    a, b = -math.tan(theta), 1.0
    c = -(v[1] - math.tan(theta) * R_IN)
    # cz is unknown; take the sign that puts C below the bowl (void)
    # a*cr + cz + c = -R * sqrt(a^2+1)   (below: the line value decreases as z decreases)
    cz = -R * math.hypot(a, b) - a * cr - c
    t_wall = (R_IN, cz)  # vertical tangent (same z as center)
    # tangent on bowl: from C, move +R along the bowl's void-normal? 
    # Closest point on the tangent line.
    # Or: C + R * n_material_bottom, etc.
    # Vector from C to V, etc. I'll compute the tangent point as the
    # projection onto the line.
    # Line point V, dir (cosθ, sinθ)
    d = (math.cos(theta), math.sin(theta))
    vc = (v[0] - cr, v[1] - cz)
    proj = vc[0] * d[0] + vc[1] * d[1]
    t_bowl = (v[0] - proj * d[0], v[1] - proj * d[1])
    # midpoint of the arc (from wall tangent to bowl tangent), the void side:
    # average of unit vectors from C to the two tangent points, scaled to R
    def unit_from_c(p):
        vx, vy = p[0] - cr, p[1] - cz
        n = math.hypot(vx, vy) or 1.0
        return (cr + R * vx / n, cz + R * vy / n)
    # mid angle
    a1 = math.atan2(t_wall[1] - cz, t_wall[0] - cr)
    a2 = math.atan2(t_bowl[1] - cz, t_bowl[0] - cr)
    # walk the shorter arc; for a cove it should be the one in the void (r < R_IN, z < v[1])
    # pick mid that's in the void
    mid_cands = []
    da = (a2 - a1)
    # unwrap
    for da_try in (da, da + 2 * math.pi, da - 2 * math.pi):
        am = a1 + da_try / 2
        mid_cands.append((cr + R * math.cos(am), cz + R * math.sin(am), abs(da_try)))
    mid_cands.sort(key=lambda p: (0 if p[0] < R_IN else 1, p[2]))
    mid = (mid_cands[0][0], mid_cands[0][1])
    return t_bowl, mid, t_wall, (cr, cz)


def build_solid():
    t_bowl_top, mid_top, t_fl, c_top, theta = _fillet_top_bowl_flange()
    t_bowl_bot, mid_bot, t_wall, c_bot = _fillet_underside_bowl_collar()
    print("top fillet:", "bowl tan", t_bowl_top, "fl", t_fl, "center", c_top, "theta_deg", math.degrees(theta))
    print("underside fillet:", "bowl tan", t_bowl_bot, "wall", t_wall, "center", c_bot)
    print("ztop(0)", ztop(0), "zbot(0)", zbot(0), "zbot(R_IN)", zbot(R_IN))

    # Walk the profile counterclockwise, x = r >= 0, in the XZ plane.
    # Start at the axis on the bowl top, go out, around the flange, down the
    # collar, back along the bowl bottom, close on the axis.
    r_top_end = t_bowl_top[0]
    if r_top_end <= 0.2 or r_top_end >= R_IN:
        raise RuntimeError(f"top bowl tangent r out of range: {r_top_end}")
    top_pts = _parabola_pts(ztop, 0.0, r_top_end, n=40)

    r_bot_start = t_bowl_bot[0]
    if r_bot_start <= 0.2 or r_bot_start >= R_IN:
        raise RuntimeError(f"bot bowl tangent r out of range: {r_bot_start}")
    bot_pts = _parabola_pts(zbot, r_bot_start, 0.0, n=40)  # inward to axis

    wp = cq.Workplane("XZ")
    r0, z0 = top_pts[0]
    wp = wp.moveTo(r0, z0)
    wp = wp.spline(top_pts[1:], includeCurrent=True)
    # top lip fillet: threePointArc through mid to flange tangent
    wp = wp.threePointArc(mid_top, t_fl)
    # flange top, flat, to the outer fillet start
    wp = wp.lineTo(R_FLANGE - F_FLANGE_TOP_OUTER, FLANGE_T)
    # 90° quarter-circle, convex, down to the outer wall
    # center (R_FLANGE - F, FLANGE_T - F); mid at 45°
    mid_fo = (
        (R_FLANGE - F_FLANGE_TOP_OUTER) + F_FLANGE_TOP_OUTER * math.cos(math.pi / 4),
        (FLANGE_T - F_FLANGE_TOP_OUTER) + F_FLANGE_TOP_OUTER * math.sin(math.pi / 4),
    )
    # Wait: quarter from (R_FL-F, FT) to (R_FL, FT-F), convex (outside).
    # Center C=(R_FL-F, FT-F). From C, start is UP (0, F), end is RIGHT (F, 0).
    # Mid at 45°: C + F*(cos45, sin45) = (R_FL-F+0.707F, FT-F+0.707F)
    mid_fo = (
        R_FLANGE - F_FLANGE_TOP_OUTER + F_FLANGE_TOP_OUTER * math.cos(math.pi / 4),
        FLANGE_T - F_FLANGE_TOP_OUTER + F_FLANGE_TOP_OUTER * math.sin(math.pi / 4),
    )
    wp = wp.threePointArc(mid_fo, (R_FLANGE, FLANGE_T - F_FLANGE_TOP_OUTER))
    wp = wp.lineTo(R_FLANGE, 0.0)                       # outer wall to the seat
    wp = wp.lineTo(R_LOC, 0.0)                          # FLAT seating face
    wp = wp.lineTo(R_LOC, -INSERT + LEADIN)             # collar OD
    wp = wp.lineTo(R_LOC - LEADIN, -INSERT)             # 45° lead-in chamfer
    wp = wp.lineTo(R_IN, -INSERT)                       # collar bottom
    wp = wp.lineTo(t_wall[0], t_wall[1])                # up the ID to the cove
    wp = wp.threePointArc(mid_bot, t_bowl_bot)          # cove onto the bowl bottom
    wp = wp.spline(bot_pts[1:], includeCurrent=True)
    wp = wp.close()
    body = wp.revolve(360)
    return body, dict(theta_deg=math.degrees(theta), t_bowl_top=t_bowl_top,
                      t_fl=t_fl, t_bowl_bot=t_bowl_bot, t_wall=t_wall)


def cut_holes(body, holes):
    zmin, zmax = -INSERT - 2.0, FLANGE_T + 2.0
    h = zmax - zmin
    for x, y, r in holes:
        cyl = (
            cq.Workplane("XY")
            .transformed(offset=(x, y, zmin))
            .circle(r)
            .extrude(h)
        )
        body = body.cut(cyl)
    return body


def _edge_info(edge):
    typ = edge.geomType()
    bbox = edge.BoundingBox()
    mid = ((bbox.xmin + bbox.xmax) / 2, (bbox.ymin + bbox.ymax) / 2, (bbox.zmin + bbox.zmax) / 2)
    length = edge.Length()
    rad = None
    try:
        # circle?
        c = edge._geomAdaptor()  # may fail
    except Exception:
        pass
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle
        ad = BRepAdaptor_Curve(edge.wrapped)
        if ad.GetType() == GeomAbs_Circle:
            rad = ad.Circle().Radius()
    except Exception:
        rad = None
    return typ, mid, length, rad


def _is_hole_lip(edge, holes):
    typ, mid, length, rad = _edge_info(edge)
    if typ in ("LINE",):
        return False
    if typ == "CIRCLE" and rad is not None and rad > HOLE_R + 1.0:
        return False  # flange / collar rings
    for x, y, r in holes:
        rxy = math.hypot(mid[0] - x, mid[1] - y)
        # complete lip: midpoint on the hole axis, long closed curve
        if rxy < 0.6 and length > 18:
            return True
        # split fragments that still lie on the hole cylinder
        if abs(rxy - r) < 0.7 and 2.0 < length < 25:
            rho = math.hypot(x, y)
            if (abs(mid[2] - ztop(max(rho, HOLE_R * 0.3))) < 4.0
                    or abs(mid[2] - zbot(max(rho, HOLE_R * 0.3))) < 4.0):
                return True
    return False


def fillet_hole_lips(body, holes, radius=F_HOLE_LIP):
    """Fillet the (generally B-spline) intersection of each hole with the bowl."""
    class HoleLipSelector(cq.Selector):
        def filter(self, objectList):
            out = []
            for o in objectList:
                if _is_hole_lip(o, holes):
                    typ, mid, length, rad = _edge_info(o)
                    print(f"  pick {typ:8} len={length:6.2f} mid=({mid[0]:7.2f},{mid[1]:7.2f},{mid[2]:7.2f})")
                    out.append(o)
            return out

    picked_n = len(HoleLipSelector().filter(body.edges().vals()))
    print(f"selected {picked_n} hole-lip edges")
    if picked_n == 0:
        return body, 0
    try:
        def _edge_key(edge):
            typ, mid, length, _rad = _edge_info(edge)
            return (typ, round(length, 2), tuple(round(float(c), 2) for c in mid))

        before = {_edge_key(o) for o in body.edges().vals()}
        body2 = body.edges(HoleLipSelector()).fillet(radius)
        print(f"filleted {picked_n} hole-lip edges at R={radius} in one op")
        # Second pass: underside lips the first selector missed. Blend edges
        # created by the fillet above are new B-splines; filleting those again
        # fails ("BRep_API: command not done") and does not change the solid.
        class Leftover(cq.Selector):
            def filter(self, objectList):
                out = []
                for o in objectList:
                    if _edge_key(o) not in before:
                        continue
                    typ, mid, length, rad = _edge_info(o)
                    if typ != "BSPLINE" or length < 8:
                        continue
                    for x, y, r in holes:
                        rxy = math.hypot(mid[0] - x, mid[1] - y)
                        rho = math.hypot(x, y)
                        if rxy < 3.8 and abs(mid[2] - zbot(max(rho, 0.3))) < 2.5:
                            print(f"  leftover {typ:8} len={length:6.2f} mid=({mid[0]:7.2f},{mid[1]:7.2f},{mid[2]:7.2f})")
                            out.append(o)
                            break
                return out
        n2 = len(Leftover().filter(body2.edges().vals()))
        if n2:
            try:
                body2 = body2.edges(Leftover()).fillet(radius)
                print(f"filleted {n2} leftover underside lips")
                picked_n += n2
            except Exception as e:
                print("leftover fillet failed (lips may already be blended):", e)
        return body2, picked_n
    except Exception as e:
        print("batch fillet failed:", e)

    # try slightly smaller, then one at a time
    for rad in (radius, 0.50, 0.45):
        ok = 0
        body_try = body
        # pick once
        class _One(cq.Selector):
            def __init__(self, target):
                self.target = target
            def filter(self, objectList):
                typ_t, mid_t, len_t, _ = _edge_info(self.target)
                out = []
                for o in objectList:
                    typ, mid, length, rad_ = _edge_info(o)
                    if typ == typ_t and abs(length - len_t) < 0.05 and all(
                        abs(a - b) < 0.05 for a, b in zip(mid, mid_t)
                    ):
                        out.append(o)
                return out
        current = body
        targets = [o for o in current.edges().vals() if _is_hole_lip(o, holes)]
        print(f"  one-by-one at R={rad}, {len(targets)} targets")
        for i, t in enumerate(targets):
            try:
                current = current.edges(_One(t)).fillet(rad)
                ok += 1
            except Exception as ex:
                print(f"    fail {i}: {ex}")
        if ok:
            print(f"  filleted {ok}/{len(targets)} at R={rad}")
            return current, ok
    print("hole-lip fillet gave up")
    return body, 0


def export_cad(body, out_dir=None, prefix="basin_guard_smooth"):
    out_dir = Path(out_dir) if out_dir else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    use_step = out_dir / f"{prefix}-use.step"
    print_step = out_dir / f"{prefix}-print.step"
    use_stl = out_dir / f"{prefix}-use.stl"
    print_stl = out_dir / f"{prefix}-print.stl"

    cq.exporters.export(body, str(use_step))
    print("wrote", use_step, "size", use_step.stat().st_size)

    # High-res tessellation
    # cadquery export stl tolerance args
    cq.exporters.export(
        body, str(use_stl),
        tolerance=STL_LINEAR,
        angularTolerance=STL_ANGULAR,
    )
    print("wrote", use_stl, "size", use_stl.stat().st_size)

    # print orientation: flange top on the bed
    # z_print = z_top_max - z_use, then shift to z=0
    solid = body.val()
    bb = solid.BoundingBox()
    # Use a tight box: the flange top should be at FLANGE_T; after the outer
    # fillet the max z is still FLANGE_T.
    z_bed = FLANGE_T
    body_print = body.rotate((0, 0, 0), (1, 0, 0), 180)
    # after 180° about X, z -> -z, y -> -y. Flange top goes to -FLANGE_T.
    body_print = body_print.translate((0, 0, z_bed))
    # now flange top at z=0, collar in +z. Confirm.
    bb2 = body_print.val().BoundingBox()
    print("print bbox", bb2.xmin, bb2.xmax, bb2.ymin, bb2.ymax, bb2.zmin, bb2.zmax)
    # if zmin is slightly off 0 due to fillet being below? fillet on top outer
    # is at z<=FLANGE_T, after flip z>=0. Seat was z=0, becomes z=FLANGE_T.
    if abs(bb2.zmin) > 1e-4:
        body_print = body_print.translate((0, 0, -bb2.zmin))
        bb2 = body_print.val().BoundingBox()
        print("print bbox shifted", bb2.zmin, bb2.zmax)

    cq.exporters.export(body_print, str(print_step))
    cq.exporters.export(
        body_print, str(print_stl),
        tolerance=STL_LINEAR,
        angularTolerance=STL_ANGULAR,
    )
    print("wrote", print_stl, "size", print_stl.stat().st_size)
    return use_stl, print_stl, use_step, print_step


def measure_stl(path, holes):
    tm = trimesh.load(str(path))
    print("mesh", path.name, "faces", len(tm.faces), "watertight", tm.is_watertight,
          "volume", tm.volume, "bounds", tm.bounds, "extents", tm.extents)
    # Raster several z-slices through the throat (vertical cylinders: mid-bowl)
    px = 0.06
    L = 2 * R_FLANGE + 2
    n = int(round(L / px))
    c = (np.arange(n) + 0.5) * px - (n * px) / 2
    X, Y = np.meshgrid(c, c, indexing="xy")
    R = np.hypot(X, Y)
    inner = R < R_IN
    pts2 = np.stack([X.ravel(), Y.ravel()], 1)

    def raster(z):
        sec = tm.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if sec is None:
            return None
        poly, tf = sec.to_2D()
        # 3D = tf @ 2D, so 2D coords are not world. Invert.
        # For a pure Z slice, tf is a translation. World = 2D + (tx,ty) or vice versa.
        # We'll test points by transforming world xy to the path frame.
        inv = np.linalg.inv(tf)
        xyh = np.c_[pts2, np.zeros(len(pts2)), np.ones(len(pts2))]
        loc = (inv @ xyh.T).T[:, :2]
        from shapely.geometry import Point
        solid = np.zeros(len(pts2), dtype=bool)
        for P in poly.polygons_full:
            # contains in path frame
            # This can be slow; use matplotlib or prepared
            try:
                from shapely import contains_xy
                solid |= contains_xy(P, loc[:, 0], loc[:, 1])
            except Exception:
                prep = None
                from shapely.prepared import prep as sprep
                pp = sprep(P)
                solid |= np.fromiter((pp.contains(Point(x, y)) for x, y in loc),
                                     dtype=bool, count=len(loc))
        return solid.reshape(X.shape)

    # pick z values through the grate for each ring
    zs = []
    for x, y, r in holes:
        rho = math.hypot(x, y)
        zs.append(0.5 * (ztop(rho) + zbot(rho)))
    zs = sorted(set(round(z, 2) for z in zs))
    # also a couple of extras
    zs = zs + [-9.0, -5.0, -2.0, 0.8]
    results = []
    max_ins_all = 0.0
    min_ins_throats = []
    open_fracs = []
    for z in zs:
        try:
            solid = raster(z)
        except Exception as e:
            print("  slice", z, "failed", e)
            continue
        if solid is None:
            continue
        void = (~solid) & inner
        if not void.any():
            continue
        edt = distance_transform_edt(void) * px
        lab, nlab = label(void)
        ins = []
        for k in range(1, nlab + 1):
            mk = lab == k
            area = mk.sum() * px * px
            if area < 2:
                continue
            ins.append(float(2 * edt[mk].max()))
        of = float(void.sum() / inner.sum())
        if ins:
            results.append(dict(z=z, n=len(ins), max_d=max(ins), min_d=min(ins), open=of, ds=[round(d, 3) for d in sorted(ins)]))
            max_ins_all = max(max_ins_all, max(ins))
            # throats: slices that clearly show ~7 openings
            if len(ins) >= 6:
                min_ins_throats.extend(ins)
                open_fracs.append(of)
        print(f"  z={z:6.2f}  openings={0 if not ins else len(ins)}  "
              f"d={('—' if not ins else f'{min(ins):.3f}–{max(ins):.3f}')}  open={of*100:.1f}%")

    # geometric throat (cylinders, fillets don't shrink mid-plane)
    geo_max = HOLE_D
    geo_strut = STRUT
    # measure strut geometrically too
    hs = hole_centers()
    gaps = []
    for i, (x, y, r) in enumerate(hs):
        for x2, y2, r2 in hs[i + 1:]:
            gaps.append(math.hypot(x - x2, y - y2) - r - r2)
    geo_strut = min(gaps) if gaps else STRUT

    # open area of 7 circles in the disc (analytical, mid-plane throat)
    geo_open = 7 * math.pi * HOLE_R ** 2 / (math.pi * R_IN ** 2)

    meas = dict(
        faces=int(len(tm.faces)),
        watertight=bool(tm.is_watertight),
        volume_mm3=float(tm.volume),
        bounds=tm.bounds.tolist(),
        extents=tm.extents.tolist(),
        slices=results,
        max_sphere_mm_sliced=float(max_ins_all),
        max_sphere_mm=float(geo_max),
        min_strut_mm=float(geo_strut),
        open_area_frac=float(geo_open),
        open_area_pct=round(geo_open * 100, 2),
        open_area_frac_sliced=float(np.mean(open_fracs)) if open_fracs else None,
    )
    return meas, tm


def render(tm_use, out_top, out_34):
    import pyvista as pv
    pv.OFF_SCREEN = True
    mesh = pv.wrap(tm_use)
    mesh = mesh.compute_normals(split_vertices=True, feature_angle=30)
    PART = dict(color="#E6E3DC", specular=0.55, specular_power=50,
                ambient=0.08, diffuse=0.72, smooth_shading=True)

    def plotter():
        p = pv.Plotter(off_screen=True, window_size=(1800, 1350), lighting="none")
        p.set_background("#ECE8E1", top="#FBFAF8")
        p.add_light(pv.Light(position=(70, -90, 160), focal_point=(0, 0, 0), intensity=0.95))
        p.add_light(pv.Light(position=(-120, 40, 80), focal_point=(0, 0, 0), intensity=0.40))
        p.add_light(pv.Light(position=(40, 80, 40), focal_point=(0, 0, -4), intensity=0.25))
        p.add_light(pv.Light(light_type="headlight", intensity=0.28))
        p.enable_anti_aliasing("ssaa")
        try:
            p.enable_ssao(radius=1.2, bias=0.015, kernel_size=128)
        except Exception:
            pass
        return p

    def drain(p):
        FT = FLANGE_T
        RB = 17.85
        ceramic = pv.Disc(inner=24.2, outer=70, c_res=240).translate((0, 0, FT))
        waste_top = pv.Cylinder(center=(0, 0, FT / 2), direction=(0, 0, 1),
                                radius=24.2, height=FT, resolution=240, capping=False)
        seat = pv.Disc(inner=RB, outer=24.2, c_res=240)
        bore = pv.Cylinder(center=(0, 0, -20), direction=(0, 0, 1),
                           radius=RB, height=40, resolution=240, capping=False)
        items = [
            (ceramic, dict(color="#CBC6BC", specular=0.4, specular_power=30, ambient=0.25)),
            (waste_top, dict(color="#BFC4CA", specular=0.9, specular_power=60, ambient=0.2)),
            (seat, dict(color="#C7CCD1", specular=0.9, specular_power=60, ambient=0.2)),
            (bore, dict(color="#4A4E54", specular=0.3, ambient=0.2)),
        ]
        for g, kw in items:
            p.add_mesh(g.triangulate(), **kw)

    p = plotter()
    drain(p)
    p.add_mesh(mesh, **PART)
    p.camera_position = [(0, 0, 115), (0, 0, 0), (0, 1, 0)]
    p.screenshot(str(out_top))
    p.close()

    p = plotter()
    drain(p)
    p.add_mesh(mesh, **PART)
    p.camera_position = [(46, -66, 52), (0, 0, -1), (0, 0, 1)]
    p.screenshot(str(out_34))
    p.close()
    print("renders", out_top, out_34)


def slice_stl(stl_path):
    ini = OUT / "slicer-a1mini-pla-basic.ini"
    gcode = OUT / "basin_guard_v2_smooth-print.gcode"
    cmd = ["prusa-slicer", "--load", str(ini), "--export-gcode",
           "--output", str(gcode), str(stl_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode:
        print("slicer stderr:", r.stderr[-2000:])
    text = ""
    if gcode.exists():
        import re
        g = gcode.read_text(errors="ignore")
        def grab(pat, default="—"):
            m = re.search(pat, g)
            return m.group(1) if m else default
        fil_mm = grab(r"; filament used \[mm\] = ([0-9.]+)")
        fil_g = grab(r"; filament used \[g\] = ([0-9.]+)")
        fil_cm3 = grab(r"; filament used \[cm3\] = ([0-9.]+)")
        time_s = grab(r"; estimated printing time \(normal mode\) = ([^\n]+)")
        layers = g.count(";LAYER_CHANGE")
        zs = [float(x) for x in re.findall(r";Z:([0-9.]+)", g)]
        zmax = max(zs) if zs else 0
        text = (
            "Basin toy guard v2 SMOOTH — slice estimate\n"
            "==========================================\n"
            "Slicer:    PrusaSlicer 2.9.2 CLI (stand-in for OrcaSlicer / Bambu Studio)\n"
            "Profile:   slicer-a1mini-pla-basic.ini (A1 mini, PLA Basic, 0.20 mm, no supports)\n"
            f"File:      {stl_path.name}  (flange top on the bed)\n\n"
            f"{gcode.name}\n"
            f"  filament: {float(fil_mm)/1000:.3f} m / {fil_cm3} cm3 / {fil_g} g\n"
            f"  time:     {time_s} (normal mode)\n"
            f"  layers:   {layers} (Z 0.2 .. {zmax:.1f} mm)\n"
            "  supports: none requested. Nothing was sent to the printer.\n"
        )
    else:
        text = f"Slice failed (exit {r.returncode}). Nothing was sent to the printer.\n{r.stderr[-1500:]}"
    (OUT / "slice-report-smooth.txt").write_text(text)
    print(text)
    return text




def analytical_stats():
    geo_open = 7 * math.pi * HOLE_R ** 2 / (math.pi * R_IN ** 2)
    return dict(
        max_sphere_mm=float(HOLE_D),
        min_strut_mm=float(STRUT),
        open_area_frac=float(geo_open),
        open_area_pct=round(geo_open * 100, 2),
        insert_depth_mm=float(INSERT),
        dish_h_mm=float(DISH),
        thick_mm=float(THICK),
        collar_od_print=float(LOC_OD_PRINT),
        collar_id=float(2 * R_IN),
        flange_diameter=float(2 * R_FLANGE),
    )


def generate(params: Params | None = None, out_dir=None, prefix="basin_guard_smooth",
             preview=False, slice_print=False, measure_slices=False):
    """Build the smooth bowl guard. Returns (files dict, stats dict)."""
    apply_params(params)
    out_dir = Path(out_dir) if out_dir else Path("out") / prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    holes = hole_centers()
    body, meta = build_solid()
    body = cut_holes(body, holes)
    body, nfil = fillet_hole_lips(body, holes)
    use_stl, print_stl, use_step, print_step = export_cad(body, out_dir=out_dir, prefix=prefix)
    cad_vol = float(body.val().Volume())
    stats = analytical_stats()
    stats.update(theta_deg=meta["theta_deg"], hole_lips_filleted=nfil, volume_mm3_cad=round(cad_vol, 1))
    try:
        import trimesh
        tm = trimesh.load(str(use_stl))
        stats["volume_mm3"] = round(float(tm.volume), 1)
        stats["watertight"] = bool(tm.is_watertight)
        stats["faces"] = int(len(tm.faces))
    except Exception as e:
        tm = None
        stats["volume_note"] = f"trimesh measure failed: {e}"
        stats["volume_mm3"] = stats["volume_mm3_cad"]
    if measure_slices and tm is not None:
        meas, tm = measure_stl(use_stl, holes)
        stats["slices"] = meas
    if preview and tm is not None:
        try:
            render(tm, out_dir / f"{prefix}-preview-top.png", out_dir / f"{prefix}-preview-34.png")
            stats["preview_top"] = str(out_dir / f"{prefix}-preview-top.png")
            stats["preview_34"] = str(out_dir / f"{prefix}-preview-34.png")
        except Exception as e:
            stats["preview_error"] = str(e)
    if slice_print:
        # never sends a job to a printer
        global OUT
        prev = OUT
        OUT = out_dir
        try:
            slice_stl(print_stl)
        except Exception as e:
            stats["slice_error"] = str(e)
        finally:
            OUT = prev
    files = dict(use_stl=str(use_stl), print_stl=str(print_stl),
                 use_step=str(use_step), print_step=str(print_step))
    report = dict(params=asdict(P), fillets_mm=dict(
        hole_lips=F_HOLE_LIP, flange_top_outer=F_FLANGE_TOP_OUTER,
        bowl_to_flange_top_lip=F_BOWL_TO_FLANGE,
        bowl_to_collar_underside_cove=F_BOWL_TO_COLLAR,
        collar_lead_in_chamfer=LEADIN, flange_seat="flat (no fillet)",
    ), geometry=dict(insert=INSERT, dish=DISH, thick=THICK, hole_d=HOLE_D,
                     strut=STRUT, pitch=PITCH, hole_rot_deg=HOLE_ROT_DEG,
                     theta_deg=meta["theta_deg"]),
           measure=stats, files=files)
    (out_dir / f"{prefix}-stats.json").write_text(json.dumps(report, indent=2))
    return files, report


def params_from_mapping(d: dict) -> Params:
    known = {f.name for f in Params.__dataclass_fields__.values()}
    # accept a few aliases used in design.json files
    alias = {
        "LOC_OD_PRINT": "collar_od_print",
        "collar_od": "collar_od_print",
        "R_FLANGE": None,  # derived
        "FLANGE_T": "flange_thickness",
        "FLANGE_D": "flange_diameter",
        "COLLAR_WALL": "collar_wall",
        "SHRINK": "shrink",
        "LEADIN": "lead_in",
        "INSERT": "insert_depth",
        "DISH": "dish_depth",
        "THICK": "thickness",
        "HOLE_D": "hole_diameter",
        "STRUT": "strut_width",
        "HOLE_ROT_DEG": "hole_rotation_deg",
        "F_HOLE_LIP": "fillet_hole_lip",
        "F_FLANGE_TOP_OUTER": "fillet_flange_top_outer",
        "F_BOWL_TO_FLANGE": "fillet_bowl_to_flange",
        "F_BOWL_TO_COLLAR": "fillet_bowl_to_collar",
        "STL_LINEAR": "stl_linear",
        "STL_ANGULAR": "stl_angular",
    }
    kw = {}
    src = dict(d)
    if "params" in src and isinstance(src["params"], dict):
        src = {**src, **src["params"]}
    if "geometry" in src and isinstance(src["geometry"], dict):
        src = {**src, **src["geometry"]}
    for k, v in src.items():
        key = alias.get(k, k)
        if key is None:
            continue
        if key in known:
            kw[key] = v
    return Params(**kw)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Generate the smooth basin-guard CAD")
    ap.add_argument("-o", "--out", default="out/smooth")
    ap.add_argument("--prefix", default="basin_guard_smooth")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--slice", action="store_true")
    args = ap.parse_args()
    files, report = generate(out_dir=args.out, prefix=args.prefix, preview=args.preview, slice_print=args.slice)
    m = report["measure"]
    print("files", files)
    print("max_sphere", m["max_sphere_mm"], "strut", m["min_strut_mm"],
          "open%", m["open_area_pct"], "volume", m.get("volume_mm3"))
