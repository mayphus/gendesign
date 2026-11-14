"""Basin guard v3 (deep basket) — shared analytic geometry.

Use coordinates: z = 0 is the flange SEAT (underside), +z up into the basin,
the drain is -z. Fit constants are copied verbatim from optimize.py /
build_smooth.py (v2) and are not changed.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.spatial import cKDTree

# ---------------- fixed fit (identical to v2) ----------------
SHRINK = 0.003
LOC_OD_PRINT = 35.10
R_LOC = LOC_OD_PRINT * (1.0 + SHRINK) / 2.0   # 17.60265  (OD 35.21 CAD)
COLLAR_WALL = 1.6
R_IN = R_LOC - COLLAR_WALL                    # 16.00265  (ID 32.01)
R_FLANGE = 23.0
FLANGE_T = 1.6
LEADIN = 0.7
A_DISC = math.pi * R_IN ** 2                  # 804.5 mm^2, v2's open-area denominator

# ---------------- rules ----------------
MIN_STRUT = 1.80
MIN_OPEN_HARD = 5.0      # v2: smaller openings catch hair -> reject
MIN_OPEN_SOFT = 8.0      # v2: prefer >= 8 mm
COIN_MAX_LEN = 18.0      # longest opening extent < 19 mm 1-jiao coin (edgewise)
MAX_ROOF_DEG = 45.0      # side-hole roof from vertical (print)
MIN_BETA, MAX_BETA = 40.0, 65.0   # floor cone from horizontal (overhang = 90-beta <= 50)
MAX_ALPHA = 30.0         # side wall lean from vertical (overhang <= 45)
F_JUNCTION = 0.8
F_LIP = 0.6
RIM_M = F_JUNCTION + 1.2  # clear distance from a surface kink to a hole edge

# ---------------- drain assumptions (stated, not measured) ----------------
KNOWN_BORE_DEPTH = 10.21  # v2 collar already assumed Ø35.2 clear to here
PIPE_ID = 32.0            # worst case of the 32-35 mm range below that
GAP_MIN = 2.0             # radial water gap outside side holes
R_CLEAR = PIPE_ID / 2 - GAP_MIN   # 14.0

PLA_DENS = 1.24e-3        # g/mm^3


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _line_isect(p1, d1, p2, d2):
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]], float)
    s, _ = np.linalg.solve(A, np.asarray(p2, float) - np.asarray(p1, float))
    return np.asarray(p1, float) + s * np.asarray(d1, float)


def profile(g):
    """Return dict with outer/inner key points for genome g (use coords)."""
    Lc, t, Ro, al, be, Hs = g["Lc"], g["t"], g["Ro"], g["alpha"], g["beta"], g["Hs"]
    ta, tb = math.tan(math.radians(al)), math.tan(math.radians(be))
    O1 = np.array([R_LOC, 0.0])
    O2 = np.array([R_LOC, -(Lc - LEADIN)])
    O3 = np.array([Ro, O2[1] - (R_LOC - Ro)])            # 45° shoulder (lead-in continues)
    O4 = np.array([Ro - Hs * ta, O3[1] - Hs])
    O5 = np.array([0.0, O4[1] - O4[0] * tb])
    segs = [(O2, O3), (O3, O4), (O4, O5)]
    offs = []
    for P, Q in segs:
        d = _unit(Q - P)
        n = np.array([d[1], -d[0]])                     # into material (up/in)
        offs.append((P + n * t, d))
    Ij = _line_isect(offs[0][0], offs[0][1], np.array([R_IN, 0.0]), np.array([0.0, 1.0]))
    I3 = _line_isect(offs[0][0], offs[0][1], offs[1][0], offs[1][1])
    I4 = _line_isect(offs[1][0], offs[1][1], offs[2][0], offs[2][1])
    I5 = _line_isect(offs[2][0], offs[2][1], np.array([0.0, 0.0]), np.array([0.0, 1.0]))
    return dict(O1=O1, O2=O2, O3=O3, O4=O4, O5=O5, Ij=Ij, I3=I3, I4=I4, I5=I5,
                ta=ta, tb=tb)


def r_inner_side(P, z):
    # inner side-wall line through I3-I4
    I3, I4 = P["I3"], P["I4"]
    return I3[0] + (z - I3[1]) * (I4[0] - I3[0]) / (I4[1] - I3[1])


def r_outer_side(P, z):
    O3, O4 = P["O3"], P["O4"]
    return O3[0] + (z - O3[1]) * (O4[0] - O3[0]) / (O4[1] - O3[1])


def z_floor_inner(P, r):
    return P["I5"][1] + r * P["tb"]


def z_floor_outer(P, r):
    return P["O5"][1] + r * P["tb"]


def rhombus_inscribed_d(a, b):
    return 2 * a * b / math.hypot(a, b)


def rounded_rhombus_area(a, b, rc):
    """Area of rhombus (half-diagonals a,b) with all 4 corners filleted rc."""
    A = 2 * a * b
    s = math.hypot(a, b)
    # interior angles: at (±a,0) vertex angle 2*atan(b/a); at (0,±b) 2*atan(a/b)
    lost = 0.0
    for half in (math.atan(b / a), math.atan(a / b)):
        th = 2 * half
        # area removed by a fillet of radius rc in a corner of angle th
        lost += 2 * (rc ** 2 / math.tan(th / 2) - 0.5 * rc ** 2 * (math.pi - th))
    return A - lost


def rhombus_outline(a, b, rc, n_arc=6):
    """2-D outline (u horizontal tangential, w vertical) with rounded corners."""
    V = [np.array(p, float) for p in ((a, 0), (0, b), (-a, 0), (0, -b))]
    pts = []
    for i in range(4):
        Vp, Vc, Vn = V[i - 1], V[i], V[(i + 1) % 4]
        u1, u2 = _unit(Vp - Vc), _unit(Vn - Vc)
        phi = 0.5 * math.acos(np.clip(np.dot(u1, u2), -1, 1))
        d = rc / math.tan(phi)
        w = _unit(u1 + u2)
        C = Vc + w * rc / math.sin(phi)
        T1, T2 = Vc + u1 * d, Vc + u2 * d
        a1 = math.atan2(*(T1 - C)[::-1]); a2 = math.atan2(*(T2 - C)[::-1])
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n_arc + 1):
            ang = a1 + da * k / n_arc
            pts.append(C + rc * np.array([math.cos(ang), math.sin(ang)]))
    return np.array(pts)


def _fillet_poly(V, rc, n_arc=6):
    pts = []
    n = len(V)
    for i in range(n):
        Vp, Vc, Vn = V[i - 1], V[i], V[(i + 1) % n]
        u1, u2 = _unit(Vp - Vc), _unit(Vn - Vc)
        phi = 0.5 * math.acos(np.clip(np.dot(u1, u2), -1, 1))
        d = rc / math.tan(phi)
        w = _unit(u1 + u2)
        C = Vc + w * rc / math.sin(phi)
        T1 = Vc + u1 * d; T2 = Vc + u2 * d
        a1 = math.atan2((T1 - C)[1], (T1 - C)[0]); a2 = math.atan2((T2 - C)[1], (T2 - C)[0])
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n_arc + 1):
            ang = a1 + da * k / n_arc
            pts.append(C + rc * np.array([math.cos(ang), math.sin(ang)]))
    return np.array(pts)


def hole_vertices(a, b, gam):
    """Pointed slot: half-width a, half-height b, roofs gam deg from vertical.
    b == a/tan(gam) gives a rhombus (diamond)."""
    tg = math.tan(math.radians(gam))
    h0 = b - a / tg
    if h0 < 1e-6:
        return [np.array(p, float) for p in ((a, 0), (0, b), (-a, 0), (0, -b))]
    return [np.array(p, float) for p in ((a, -h0), (a, h0), (0, b), (-a, h0), (-a, -h0), (0, -b))]


def hole_outline(a, b, gam, rc, n_arc=6):
    return _fillet_poly(hole_vertices(a, b, gam), rc, n_arc)


def hole_area(a, b, gam, rc):
    from shapely.geometry import Polygon
    return Polygon(hole_outline(a, b, gam, rc, 12)).area


def hole_ball(a, b, gam):
    return 2 * min(a, b * math.sin(math.radians(gam)))


def side_vmin(a, b, gam, rc, p, sm, stagger):
    from shapely.geometry import Polygon
    from shapely import affinity
    H = Polygon(hole_outline(a, b, gam, rc, 6))
    if H.distance(affinity.translate(H, p, 0)) < sm:
        return None
    if not stagger:
        return 2 * b + sm
    lo, hi = 0.0, 2 * b + sm + 1
    for _ in range(28):
        v = 0.5 * (lo + hi)
        ok = (H.distance(affinity.translate(H, p / 2, v)) >= sm and
              H.distance(affinity.translate(H, 0, 2 * v)) >= sm)
        if ok:
            hi = v
        else:
            lo = v
    return hi


def _zone(g, P):
    ztop = min(P["O3"][1], P["I3"][1]) - RIM_M
    zbot = max(P["O4"][1], P["I4"][1]) + RIM_M
    return ztop, zbot


def size_wall(g):
    """Hs is derived: just tall enough for nrows rows of side holes (+ slack)."""
    nrows = int(g["nrows"])
    if nrows <= 0:
        g["Hs"] = 1.0
        return
    a, b = g["a"], g["b"]
    g["Hs"] = 2 * b + 6.0
    for _ in range(4):
        P = profile(g)
        ztop, zbot = _zone(g, P)
        c = g["Hs"] - (ztop - zbot)
        rho_min = r_inner_side(P, zbot)
        sm = MIN_STRUT + 0.10
        N_max = int(math.floor(2 * math.pi * rho_min / (2 * a + sm)))
        N = max(N_max - int(g.get("dN", 0)), 3)
        p = 2 * math.pi * rho_min / N
        v = side_vmin(a, b, g["gam"], g["rc"], p, sm, g["stagger"]) or (2 * b + sm)
        v += g.get("v_slack", 0.0)
        Z = 2 * b + (nrows - 1) * v
        g["Hs"] = max(1.0, Z + c + 0.02 + g.get("h_slack", 0.0))


def layout(g):
    """Place floor + side holes. Returns dict or raises ValueError(reason)."""
    size_wall(g)
    P = profile(g)
    res = dict(P=P, floor=[], side=[], reasons=[])
    if P["O4"][0] < 6.0:
        res["reasons"].append("narrow_floor")
    # ---- floor holes: vertical cylinders, all d_f ----
    d_f = g["d_f"]; rf = d_f / 2
    r_lim = min(P["I4"][0], P["O4"][0]) - RIM_M          # hole edge must stay inside
    floor = []
    if g["center"]:
        floor.append((0.0, 0.0, rf))
    rho_prev = 0.0 if g["center"] else None
    for k, key in enumerate(("rho1", "rho2")):
        if key == "rho2" and not g.get("ring2", False):
            break
        if rho_prev is None:
            rho_min = rf + 0.6
        else:
            rho_min = rho_prev + d_f + MIN_STRUT
        rho_max = r_lim - rf
        if rho_max < rho_min - 1e-9:
            break
        rho = rho_min + g[key] * (rho_max - rho_min)
        # most holes on this ring with strut
        s = (d_f + MIN_STRUT) / (2 * rho) if rho > 1e-6 else 9.0
        if s >= 1:
            n = 1 if rho_prev is None else 0
        else:
            n = int(math.floor(math.pi / math.asin(s) + 1e-9))
        n = min(n, int(g.get("n%d_cap" % (k + 1), 99)))
        if n <= 0:
            break
        rot = g.get("rot%d" % (k + 1), 0.0) * 2 * math.pi / n
        for j in range(n):
            th = rot + j * 2 * math.pi / n
            floor.append((rho * math.cos(th), rho * math.sin(th), rf))
        rho_prev = rho
    res["floor"] = floor
    # ---- side holes: horizontal radial rounded-rhombus prisms ----
    side = []
    nrows = int(g["nrows"])
    a, b = g["a"], g["b"]
    if nrows > 0:
        ztop, zbot = _zone(g, P)
        # lattice that satisfies the strut rule by construction (flat-lattice
        # formulas at the narrowest inner radius); kd-tree check verifies.
        rho_min = r_inner_side(P, zbot)
        sm = MIN_STRUT + 0.10
        gam = g["gam"]
        N_max = int(math.floor(2 * math.pi * rho_min / (2 * a + sm)))
        N = max(N_max - int(g.get("dN", 0)), 0)
        g["N"] = N
        if N < 3:
            g["v"] = 0.0
            res["rows_fit"] = 0
            res["side"] = []
            return res
        p = 2 * math.pi * rho_min / N
        v = side_vmin(a, b, gam, g["rc"], p, sm, g["stagger"])
        if v is None:
            g["v"] = 0.0
            res["rows_fit"] = 0; res["side"] = []; res["reasons"].append("lattice")
            return res
        v = v + g.get("v_slack", 0.0)
        g["v"] = v
        fit = 0
        for k_ in range(nrows):
            zc = ztop - b - k_ * v
            if zc - b < zbot - 1e-9:
                break
            fit += 1
        for k_ in range(fit):
            zc = ztop - b - k_ * v
            off = (0.5 if (k_ % 2 and g["stagger"]) else 0.0) * 2 * math.pi / N
            for j in range(N):
                side.append((off + j * 2 * math.pi / N, zc))
        res["rows_fit"] = fit
    else:
        g["N"] = 0; g["v"] = 0.0
        res["rows_fit"] = 0
    res["side"] = side
    return res


def boundary_points(g, L, n_c=40):
    """3-D boundary samples of every hole on both shell surfaces."""
    P = L["P"]
    groups = []
    a, b, rc = g["a"], g["b"], g["rc"]
    if L["side"]:
        ol = hole_outline(a, b, g["gam"], rc, n_arc=3)
        # densify
        dense = []
        for i in range(len(ol)):
            p, q = ol[i], ol[(i + 1) % len(ol)]
            m = max(1, int(np.linalg.norm(q - p) / 0.4))
            for s in range(m):
                dense.append(p + (q - p) * s / m)
        ol = np.array(dense)
    for th, zc in L["side"]:
        er = np.array([math.cos(th), math.sin(th), 0.0])
        et = np.array([-math.sin(th), math.cos(th), 0.0])
        pts = []
        for fn in (r_inner_side, r_outer_side):
            for u, w in ol:
                z = zc + w
                R = fn(P, z)
                s = math.sqrt(max(R * R - u * u, 0.0))
                pts.append(er * s + et * u + np.array([0, 0, z]))
        groups.append(np.array(pts))
    for x, y, r in L["floor"]:
        ang = np.linspace(0, 2 * math.pi, n_c, endpoint=False)
        X = x + r * np.cos(ang); Y = y + r * np.sin(ang)
        rr = np.hypot(X, Y)
        Zi = z_floor_inner(P, rr); Zo = z_floor_outer(P, rr)
        groups.append(np.r_[np.c_[X, Y, Zi], np.c_[X, Y, Zo]])
    return groups


def min_ligament(groups):
    if len(groups) < 2:
        return 99.0
    allp = np.vstack(groups)
    lab = np.concatenate([np.full(len(gp), i) for i, gp in enumerate(groups)])
    tree = cKDTree(allp)
    best = 99.0
    d, idx = tree.query(allp, k=min(60, len(allp)))
    other = lab[idx] != lab[:, None]
    dd = np.where(other, d, np.inf).min(axis=1)
    return float(dd.min())


def depth_of(g, L):
    P = L["P"]
    rc = 0.0
    if L["floor"] and L["floor"][0][0] == 0.0 and L["floor"][0][1] == 0.0:
        rc = L["floor"][0][2]
    return -(P["O5"][1] + rc * P["tb"])


def shell_volume(g, L):
    """Pappus volume of the revolved section minus hole plugs (approx)."""
    from shapely.geometry import Polygon
    P = L["P"]
    poly = Polygon([tuple(P["O5"]), tuple(P["O4"]), tuple(P["O3"]), tuple(P["O2"]),
                    tuple(P["O1"]), (R_FLANGE, 0), (R_FLANGE, FLANGE_T), (R_IN, FLANGE_T),
                    tuple(P["Ij"]), tuple(P["I3"]), tuple(P["I4"]), tuple(P["I5"])])
    V = 2 * math.pi * poly.centroid.x * poly.area
    tb = P["tb"]; t = g["t"]
    for x, y, r in L["floor"]:
        V -= math.pi * r * r * (t / math.cos(math.atan(tb)))
    A_s = hole_area(g["a"], g["b"], g["gam"], g["rc"]) if L["side"] else 0.0
    ca = math.cos(math.radians(g["alpha"]))
    V -= len(L["side"]) * A_s * t / ca
    return V


def drainage(holes_depths, h_basin=5.0, cd=0.6):
    """Ideal orifice sum: Q (L/min) with basin water h_basin mm above the flange
    top. holes_depths: list of (area_mm2, depth_below_flange_top_mm)."""
    g = 9.81
    Q = 0.0
    for A, d in holes_depths:
        Q += cd * A * 1e-6 * math.sqrt(2 * g * max(h_basin + d, 0.0) * 1e-3)
    return Q * 1000 * 60


def evaluate(g, ball_limit, max_depth):
    try:
        return _evaluate(g, ball_limit, max_depth)
    except Exception as e:  # degenerate geometry
        return dict(feasible=0, score=-200.0, open_area_pct=0, open_mm2=0, floor_mm2=0, side_mm2=0,
                    floor_share_pct=0, max_ball_mm=0, floor_hole_d=0, side_ball_mm=0, min_open_mm=0,
                    min_strut_mm=None, n_floor=0, n_side=0, rows=0, depth_mm=0, Lc=g["Lc"], t=g["t"],
                    Ro=g["Ro"], alpha=g["alpha"], beta=g["beta"], Hs=g["Hs"], a=g["a"], b=g["b"], gam=g["gam"], stagger=int(g["stagger"]),
                    N=int(g["N"]), v=g["v"], hole_edge_mm=0, edge_per_open=None, q_clean_lpm=0,
                    q_floor_blocked_lpm=0, cad_vol_mm3=0, mass_g_est=0, annulus_mm2=0,
                    reasons="degenerate:" + type(e).__name__), None


def _evaluate(g, ball_limit, max_depth):
    L = layout(g)
    P = L["P"]
    viol, reasons = 0.0, list(L["reasons"])
    a, b, rc = g["a"], g["b"], g["rc"]
    side_ball = hole_ball(a, b, g["gam"]) if L["side"] else 0.0
    floor_ball = g["d_f"] if L["floor"] else 0.0
    max_ball = max(side_ball, floor_ball)
    if max_ball > ball_limit + 1e-6:
        viol += max_ball - ball_limit; reasons.append("sphere")
    opens = [x for x in (side_ball, floor_ball) if x > 0]
    min_open = min(opens) if opens else 0.0
    if opens and min_open < MIN_OPEN_HARD:
        viol += MIN_OPEN_HARD - min_open; reasons.append("slit")
    if L["side"] and 2 * b > COIN_MAX_LEN:
        viol += 2 * b - COIN_MAX_LEN; reasons.append("coin")
    if L["side"] and g["gam"] > MAX_ROOF_DEG + 1e-6:
        viol += 1; reasons.append("roof")
    dep = depth_of(g, L)
    if dep > max_depth:
        viol += dep - max_depth; reasons.append("depth")
    # envelope below the known bore must fit a Ø32 pipe
    zk = -KNOWN_BORE_DEPTH
    O2, O3 = P["O2"], P["O3"]
    if zk < O2[1]:
        r_at = O2[0] - (O2[1] - zk) if zk > O3[1] else r_outer_side(P, zk)
        if r_at > PIPE_ID / 2 + 1e-6:
            viol += r_at - PIPE_ID / 2; reasons.append("pipe")
    else:
        viol += 1; reasons.append("pipe")
    if P["I4"][0] <= 0.5 or P["I3"][1] <= P["I4"][1] or P["Ij"][1] <= P["I3"][1]:
        viol += 5; reasons.append("profile")
    nh = len(L["floor"]) + len(L["side"])
    if nh == 0:
        viol += 5; reasons.append("blind")
    lig = 99.0
    if viol == 0 and nh:
        lig = min_ligament(boundary_points(g, L))
        if lig < MIN_STRUT + 0.02:  # sampled distance can overestimate by ~0.01
            viol += MIN_STRUT + 0.02 - lig; reasons.append("strut")
    A_floor = sum(math.pi * r * r for _, _, r in L["floor"])
    A_hole_side = hole_area(a, b, g["gam"], rc) if L["side"] else 0.0
    A_side = len(L["side"]) * A_hole_side
    A_tot = A_floor + A_side
    open_frac = A_tot / A_DISC
    # hair proxies
    perim_side = 0.0
    if L["side"]:
        ol = hole_outline(a, b, g["gam"], rc, 8)
        perim_side = float(np.sum(np.linalg.norm(np.diff(np.r_[ol, ol[:1]], axis=0), axis=1)))
    perim = len(L["side"]) * perim_side + sum(2 * math.pi * r for _, _, r in L["floor"])
    ftop = FLANGE_T
    hd = [(math.pi * r * r, ftop - z_floor_inner(P, math.hypot(x, y))) for x, y, r in L["floor"]]
    hs = [(A_hole_side, ftop - zc) for _, zc in L["side"]]
    q_clean = drainage(hd + hs)
    q_blocked = drainage(hs)
    vol = shell_volume(g, L)
    s = open_frac
    s -= 0.16 * max(0.0, MIN_OPEN_SOFT - min_open)
    s -= 0.0005 * dep
    feas = viol <= 1e-9
    if not feas:
        s = -100.0 + 10 * open_frac - 5 * viol
    out = dict(
        feasible=int(feas), score=round(s, 5), open_area_pct=round(100 * open_frac, 2),
        open_mm2=round(A_tot, 1), floor_mm2=round(A_floor, 1), side_mm2=round(A_side, 1),
        floor_share_pct=round(100 * A_floor / A_tot, 1) if A_tot else 0.0,
        max_ball_mm=round(max_ball, 3), floor_hole_d=round(floor_ball, 3),
        side_ball_mm=round(side_ball, 3), min_open_mm=round(min_open, 3),
        min_strut_mm=round(lig, 3) if lig < 90 else None,
        n_floor=len(L["floor"]), n_side=len(L["side"]), rows=L["rows_fit"],
        depth_mm=round(dep, 2), Lc=round(g["Lc"], 2), t=round(g["t"], 2), Ro=round(g["Ro"], 2),
        alpha=round(g["alpha"], 1), beta=round(g["beta"], 1), Hs=round(g["Hs"], 2),
        a=round(a, 2), b=round(b, 2), gam=round(g["gam"], 1), stagger=int(g["stagger"]), N=int(g["N"]), v=round(g["v"], 2),
        hole_edge_mm=round(perim, 0), edge_per_open=round(perim / A_tot, 3) if A_tot else None,
        q_clean_lpm=round(q_clean, 1), q_floor_blocked_lpm=round(q_blocked, 1),
        cad_vol_mm3=round(vol, 0), mass_g_est=round(vol * PLA_DENS, 2),
        annulus_mm2=round(math.pi * ((PIPE_ID / 2) ** 2 - g["Ro"] ** 2), 0),
        reasons=",".join(reasons),
    )
    out = {k: (float(v) if isinstance(v, np.floating) else v) for k, v in out.items()}
    return out, L


def v2_reference():
    """v2 smooth winner numbers recomputed with the same formulas."""
    DISH, R = 9.2, R_IN
    def ztop(r):
        return FLANGE_T - DISH * (1 - (r / R) ** 2)
    holes = [(0.0, 4.3)] + [(10.4, 4.3)] * 6
    A = sum(math.pi * r * r for _, r in holes)
    hd = [(math.pi * r * r, FLANGE_T - ztop(rho)) for rho, r in holes]
    return dict(open_mm2=round(A, 1), open_area_pct=round(100 * A / A_DISC, 2),
                q_clean_lpm=round(drainage(hd), 1), q_floor_blocked_lpm=0.0,
                hole_edge_mm=round(7 * 2 * math.pi * 4.3, 0),
                edge_per_open=round(7 * 2 * math.pi * 4.3 / A, 3),
                floor_share_pct=100.0, depth_mm=10.21)
