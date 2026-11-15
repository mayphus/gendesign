#!/usr/bin/env python3
"""
Basin toy guard v2 — computational design loop.

NEW GOAL: let hair and water drop through easily; block baby toys.
Fit diameters are reused from the measured De40 catcher work and are FIXED.
Insert depth (and dish/proud) is a free variable with stated bounds.

Search: generational evolution. Each generation's best is saved as a
top-view frame so the iteration can be inspected.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt, label, gaussian_filter
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve, factorized
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Wedge, PathPatch
from matplotlib.collections import PatchCollection
import matplotlib.patches as mpatches

OUT = Path(__file__).resolve().parent
ITER = OUT / "iterations"
ITER.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Fixed fit — from the measured De40 catcher work (do not invent)
# De40 / DN40 PVC-U waste, GB/T 5836.1-2018. Open hole measured ~35 mm.
# ---------------------------------------------------------------------------
SHRINK = 0.003
LOC_OD_PRINT = 35.10
R_LOC = LOC_OD_PRINT * (1.0 + SHRINK) / 2.0  # CAD radius, OD 35.2053 mm
COLLAR_WALL = 1.6
R_IN = R_LOC - COLLAR_WALL                   # 16.00265 mm, ID 32.0053
R_FLANGE = 23.0                              # 46.0 mm OD; seat assumed, never measured
FLANGE_T = 1.6
FLANGE_CH = 0.6
LEADIN = 0.7

# ---------------------------------------------------------------------------
# Toy-block rule (labeled so it can be changed)
# ---------------------------------------------------------------------------
# 12 mm max passable sphere.
# ASTM F963 / 16 CFR 1501 small-parts cylinder is 31.7 mm — a choking test
# almost as wide as this grate, so it cannot be the opening size.
# 12 mm is below a standard marble (16 mm) and DUPLO's ~16 mm module, and
# blocks typical bath toys, teething rings and 1-jiao / 5-jiao / 1-yuan coins
# (19–25 mm). Openings this large (with rounded lips) are well above the
# ~5–6 mm scale where hair usually snags. It will NOT reliably stop a 1×1
# LEGO brick (~8 mm) or small beads — tighten MAX_SPHERE_MM if needed.
MAX_SPHERE_MM = 12.0
MIN_STRUT_MM = 1.80          # print-friendly PLA, mid of 1.6–2.0
MIN_RIM_MM = 1.20            # ligament from hole edge to collar ID
MIN_OPEN_HARD = 5.0          # openings smaller than this catch hair — reject
MIN_OPEN_SOFT = 8.0          # prefer all openings at least this big

# Depth bounds (free variable). Stopper / overflow were never measured.
# The original cup catcher for this drain went 18 mm below the seat, so that
# is the hard ceiling. A 4 mm collar is the minimum for a stable press-fit
# (includes the 0.7 mm lead-in). Proud-of-basin height is capped so it does
# not become a bump under a hand or cloth. Overhang is capped so the dish
# prints on the A1 mini with no supports (flange on the bed).
MIN_INSERT = 4.0
MAX_INSERT = 18.0
MAX_PROUD = 2.5
MAX_OVERHANG_DEG = 50.0
MIN_THICK = 2.0
MAX_THICK = 3.0

# Raster / FE
PX = 0.12
FE_H = 0.45
E_PLA, NU_PLA = 3500.0, 0.36   # MPa
F_CENTER, F_OFF, P_WATER = 15.0, 10.0, 0.005  # N, N, N/mm^2 (toddler press)
N_GEN = 12
POP = 48
RNG = np.random.default_rng(20261113)

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _grid():
    L = 2 * R_FLANGE + 2.0
    n = int(round(L / PX))
    L = n * PX
    c = (np.arange(n) + 0.5) * PX - L / 2
    X, Y = np.meshgrid(c, c, indexing="xy")
    R = np.hypot(X, Y)
    return L, n, X, Y, R

Lpix, Npix, Xg, Yg, Rg = _grid()
INNER = Rg < R_IN
FLANGE_RING = (Rg >= R_IN) & (Rg <= R_FLANGE)


def holes_mask(holes):
    """Solid True where material exists in the grate disc (r < R_IN)."""
    solid = INNER.copy()
    for x, y, r in holes:
        solid &= np.hypot(Xg - x, Yg - y) >= r
    solid |= ~INNER  # outside the bore is not a grate opening
    return solid


def radial_mask(n_spokes, n_rings, spoke_w, ring_w, r_hub, rot):
    """Rounded radial grate: concentric rings + spokes, all filleted in 2D
    by construction (annular slots with rounded ends approximated by
    isoparametric opening checks later)."""
    ang = np.arctan2(Yg, Xg)
    solid = np.zeros_like(Xg, dtype=bool)
    # hub
    solid |= Rg <= r_hub
    # spokes
    # angular half-width of a spoke of width spoke_w at radius r is ~ (spoke_w/2)/r
    for i in range(n_spokes):
        a0 = rot + i * 2 * np.pi / n_spokes
        # distance to infinite spoke line
        d = np.abs(Xg * np.sin(a0) - Yg * np.cos(a0))
        solid |= (d <= spoke_w / 2) & (Rg <= R_IN)
    # rings
    if n_rings > 0:
        # rings between hub and rim
        rs = np.linspace(r_hub, R_IN, n_rings + 2)[1:-1]
        for rr in rs:
            solid |= (np.abs(Rg - rr) <= ring_w / 2) & (Rg <= R_IN)
    # always keep a rim ring
    solid |= (Rg >= R_IN - MIN_RIM_MM) & (Rg <= R_IN + 0.2)
    solid |= ~INNER
    # close slivers thinner than 0.6 mm (print dust)
    return solid


def measure_openings(solid):
    void = (~solid) & INNER
    if not void.any():
        return dict(n_open=0, max_inscribed=0.0, min_inscribed=0.0,
                    open_frac=0.0, aspect_p95=1.0, open_list=[])
    edt = distance_transform_edt(void) * PX
    lab, nlab = label(void)
    opens = []
    aspects = []
    for k in range(1, nlab + 1):
        m = lab == k
        area = m.sum() * PX * PX
        if area < 0.4:
            continue
        ins = 2.0 * edt[m].max()
        # isoperimetric quotient: 4*pi*A / P^2  (1 = circle)
        # perimeter from binary erosion edge
        from scipy.ndimage import binary_erosion
        peri = (m & ~binary_erosion(m)).sum() * PX
        iq = (4 * np.pi * area / (peri ** 2)) if peri > 0 else 0.0
        # aspect proxy: 1/iq, 1 for a circle, higher for slits
        asp = 1.0 / max(iq, 1e-3)
        opens.append(ins)
        aspects.append(asp)
    if not opens:
        return dict(n_open=0, max_inscribed=0.0, min_inscribed=0.0,
                    open_frac=0.0, aspect_p95=1.0, open_list=[])
    open_frac = void.sum() / INNER.sum()
    return dict(
        n_open=len(opens),
        max_inscribed=float(max(opens)),
        min_inscribed=float(min(opens)),
        open_frac=float(open_frac),
        aspect_p95=float(np.percentile(aspects, 95)),
        open_list=[round(x, 2) for x in sorted(opens)],
    )


def min_strut_width(solid):
    """Min ligament thickness inside the grate, via medial-axis EDT.

    Endpoints of the skeleton run into corners where the EDT goes to 0,
    so only interior skeleton pixels (2+ neighbours) are used.
    """
    from skimage.morphology import skeletonize
    from scipy.ndimage import convolve
    core = solid & (Rg < R_IN - 0.15)
    if not core.any():
        return 0.0
    edt = distance_transform_edt(core) * PX
    sk = skeletonize(core)
    sk &= Rg < R_IN - 0.6
    kern = np.ones((3, 3), dtype=int)
    kern[1, 1] = 0
    nbr = convolve(sk.astype(int), kern, mode="constant")
    ridge = sk & (nbr >= 2)
    if ridge.any():
        return float(2.0 * edt[ridge].min())
    vals = edt[core & (Rg < R_IN - 0.6)]
    return float(2.0 * np.percentile(vals, 5)) if len(vals) else 0.0


def geometric_min_strut(holes):
    """Exact hole-hole ligaments. Rim clearance is checked separately
    (the rim is backed by the collar, so MIN_RIM_MM < MIN_STRUT_MM is OK)."""
    if not holes:
        return 0.0, 0.0
    gaps, rims = [], []
    for i, (x, y, r) in enumerate(holes):
        rims.append(R_IN - math.hypot(x, y) - r)
        for x2, y2, r2 in holes[i + 1:]:
            gaps.append(math.hypot(x - x2, y - y2) - r - r2)
    return (float(min(gaps)) if gaps else 0.0,
            float(min(rims)) if rims else 0.0)


# ---------------------------------------------------------------------------
# Reissner–Mindlin plate FE (same formulation as the earlier catcher TO)
# ---------------------------------------------------------------------------
def _element_ke():
    a = FE_H
    Tref = 1.0
    # unit-modulus, will scale by E * t^3 and shear
    # We rebuild with thickness later — store geometric B once.
    return a


def _build_fe_mesh():
    L = 2 * (R_IN + 2 * FE_H)
    n = int(np.ceil(L / FE_H))
    if n % 2:
        n += 1
    L = n * FE_H
    xc = (np.arange(n) + 0.5) * FE_H - L / 2
    X, Y = np.meshgrid(xc, xc, indexing="xy")
    R = np.hypot(X, Y)
    active = R < (R_IN + 1.0 * FE_H)
    nn = n + 1
    xn = np.arange(nn) * FE_H - L / 2
    XN, YN = np.meshgrid(xn, xn, indexing="xy")
    RN = np.hypot(XN, YN)
    # element -> node ids (row-major)
    def nid(i, j):
        return i * nn + j
    elems = []
    ecent = []
    for i in range(n):
        for j in range(n):
            if not active[i, j]:
                continue
            n0 = nid(i, j)
            n1 = nid(i, j + 1)
            n2 = nid(i + 1, j + 1)
            n3 = nid(i + 1, j)
            elems.append((n0, n1, n2, n3))
            ecent.append((X[i, j], Y[i, j], R[i, j], i, j))
    elems = np.array(elems, dtype=int)
    ecent = np.array(ecent)
    # supported nodes: on/near the collar (r >= R_IN)
    supported = RN >= (R_IN - 0.2)
    return dict(n=n, nn=nn, L=L, X=X, Y=Y, R=R, XN=XN, YN=YN, RN=RN,
                elems=elems, ecent=ecent, supported=supported, nnode=nn * nn)


FE = _build_fe_mesh()


def _ke_plate(thick):
    """12x12 element stiffness for thickness `thick`, modulus E_PLA."""
    a = FE_H
    T = thick
    D_b = E_PLA * T ** 3 / (12 * (1 - NU_PLA ** 2)) * np.array(
        [[1, NU_PLA, 0], [NU_PLA, 1, 0], [0, 0, (1 - NU_PLA) / 2]]
    )
    G = E_PLA / (2 * (1 + NU_PLA))
    D_s = 5 / 6 * G * T * np.eye(2)
    xi_n = np.array([-1.0, 1.0, 1.0, -1.0])
    et_n = np.array([-1.0, -1.0, 1.0, 1.0])

    def shape(xi, et):
        N = 0.25 * (1 + xi * xi_n) * (1 + et * et_n)
        dNx = 0.25 * xi_n * (1 + et * et_n) * 2 / a
        dNy = 0.25 * et_n * (1 + xi * xi_n) * 2 / a
        return N, dNx, dNy

    K = np.zeros((12, 12))
    detJ = a * a / 4
    g = 1 / np.sqrt(3)
    for xi in (-g, g):
        for et in (-g, g):
            N, dx, dy = shape(xi, et)
            B = np.zeros((3, 12))
            for i in range(4):
                B[0, 3 * i + 1] = dx[i]
                B[1, 3 * i + 2] = dy[i]
                B[2, 3 * i + 1] = dy[i]
                B[2, 3 * i + 2] = dx[i]
            K += B.T @ D_b @ B * detJ
    N, dx, dy = shape(0, 0)
    B = np.zeros((2, 12))
    for i in range(4):
        B[0, 3 * i] = dx[i]
        B[0, 3 * i + 1] = N[i]
        B[1, 3 * i] = dy[i]
        B[1, 3 * i + 2] = N[i]
    K += B.T @ D_s @ B * detJ * 4
    return K


_KE_CACHE = {}


def plate_deflection(solid, thick, dish_h, insert_depth):
    """Peak |w| in mm under the toddler-press load cases, shallow-shell adjusted."""
    key_t = round(float(thick), 2)
    if key_t not in _KE_CACHE:
        _KE_CACHE[key_t] = _ke_plate(key_t)
    Ke = _KE_CACHE[key_t]
    # density per element from the high-res mask
    ex, ey = FE["ecent"][:, 0], FE["ecent"][:, 1]
    # sample solid at element centres
    ii = np.clip(((ey + Lpix / 2) / PX).astype(int), 0, Npix - 1)
    jj = np.clip(((ex + Lpix / 2) / PX).astype(int), 0, Npix - 1)
    rho = solid[ii, jj].astype(float)
    # elements in the collar ring are always solid (support)
    rho = np.where(FE["ecent"][:, 2] >= R_IN, 1.0, rho)
    Emin = 1e-6
    scale = Emin + (1.0 - Emin) * rho ** 3

    elems = FE["elems"]
    nnode = FE["nnode"]
    ndof = nnode * 3
    # assemble
    n_el = len(elems)
    I = np.repeat(np.arange(n_el), 144)
    # dof map
    dofs = np.empty((n_el, 12), dtype=int)
    for k in range(4):
        dofs[:, 3 * k:3 * k + 3] = elems[:, k][:, None] * 3 + np.array([0, 1, 2])
    Jloc = np.tile(np.repeat(np.arange(12), 12), n_el)
    Kloc = np.tile(np.tile(np.arange(12), 12), n_el)
    # wait, better use ik, jk
    rows = np.repeat(dofs, 12, axis=1).ravel()
    cols = np.tile(dofs, 12).ravel()
    data = (Ke.ravel()[None, :] * scale[:, None]).ravel()
    K = sp.coo_matrix((data, (rows, cols)), shape=(ndof, ndof)).tocsr()

    # supports: w = 0 on collar nodes (leave rotations free-ish, pin w)
    supp = np.where(FE["supported"].ravel())[0]
    fix = supp * 3 + 0  # w dof
    # loads: 15 N on an 8 mm patch at centre, 10 N at (8,0), uniform pressure
    XN, YN = FE["XN"], FE["YN"]
    RN = FE["RN"]
    node_in = RN <= R_IN + 0.1
    # distribute to nodes from elements? apply at nodes inside patches
    def patch_force(cx, cy, rad, F):
        f = np.zeros(ndof)
        # If the centre is an opening, grow the patch until it finds solid
        # (a finger still presses the surrounding struts).
        for rad_try in (rad, rad + 2, rad + 4, rad + 6, 12.0):
            d = np.hypot(XN - cx, YN - cy)
            m = (d <= rad_try) & node_in
            if not m.any():
                continue
            w = (rad_try - d[m]).clip(0, None)
            ii = np.clip(((YN[m] + Lpix / 2) / PX).astype(int), 0, Npix - 1)
            jj = np.clip(((XN[m] + Lpix / 2) / PX).astype(int), 0, Npix - 1)
            w = w * solid[ii, jj]
            if w.sum() <= 0:
                continue
            w = w / w.sum() * F
            ids = np.where(m.ravel())[0]
            f[ids * 3 + 0] = -w  # -z
            return f
        return f

    f1 = patch_force(0, 0, 4.0, F_CENTER)
    f2 = patch_force(8.0, 0.0, 4.0, F_OFF)
    # water pressure on solid grate area, lumped to nodes
    f3 = np.zeros(ndof)
    # each active element contributes P * A / 4 to its 4 nodes if solid
    A = FE_H * FE_H
    for e, (n0, n1, n2, n3) in enumerate(elems):
        if FE["ecent"][e, 2] >= R_IN:
            continue
        pe = P_WATER * A * rho[e] / 4.0
        for nd in (n0, n1, n2, n3):
            f3[nd * 3] -= pe

    # apply BC by big spring
    # Unused nodes (outside the disc mesh) have zero stiffness and would
    # make K singular. Pin them, and add a tiny diagonal everywhere.
    used = np.zeros(nnode, dtype=bool)
    used[np.unique(elems)] = True
    unused = np.where(~used)[0]
    K = K.tolil()
    kbig = 1e8
    for d in fix:
        K[d, d] += kbig
    for nd in unused:
        for k in range(3):
            K[nd * 3 + k, nd * 3 + k] += kbig
    K = K.tocsr() + 1e-6 * sp.eye(ndof)
    try:
        solve = factorized(K.tocsc())
    except Exception:
        return 9.9
    def peak(f):
        u = solve(f)
        w = u[0::3]
        # only interior nodes
        interior = (RN.ravel() < R_IN) & (~FE["supported"].ravel())
        if not interior.any():
            return 9.9
        return float(np.max(np.abs(w[interior])))

    w = max(peak(f1), peak(f2), peak(f3))
    # shallow-shell + deeper collar support
    shell = 1.0 + 3.5 * (float(dish_h) / R_IN) ** 2
    support = 1.0 + 0.10 * min(max(float(insert_depth) - 4.0, 0.0), 10.0) / 10.0
    return w / (shell * support)


def overhang_deg(dish_h, span_r=None):
    """Paraboloid rim slope from horizontal, degrees (print, flange on bed)."""
    span_r = R_IN if span_r is None else span_r
    if dish_h <= 1e-6:
        return 0.0
    return math.degrees(math.atan(2.0 * dish_h / span_r))


def score_of(m):
    if not m.get("feasible", False):
        # still give a smooth tail so evolution can climb out
        return -100.0 + 10.0 * m.get("open_frac", 0.0) - 5.0 * m.get("viol", 1.0)
    s = m["open_frac"]
    s -= 0.16 * max(0.0, MIN_OPEN_SOFT - m["min_inscribed"])
    s -= 0.35 * max(0.0, m["aspect_p95"] - 1.30)
    s -= 0.22 * max(0.0, m["defl_mm"] - 0.40)
    s -= 0.55 * max(0.0, m["defl_mm"] - 0.90)
    s -= 0.05 * m["proud_h"]
    s -= 0.010 * max(0.0, m["insert_depth"] - 10.0)
    s -= 0.025 * max(0.0, 6.0 - m["insert_depth"])
    s += 0.025 * min(m["dish_h"], 7.0) / 7.0
    # slight preference to use more of the allowed 12 mm ball (more flow)
    if m["max_inscribed"] > 0:
        s += 0.04 * (m["max_inscribed"] / MAX_SPHERE_MM)
    return float(s)


def evaluate(cand):
    """cand: dict with family, holes or radial params, depth, thick, ..."""
    arch = cand.get("arch", "top_grate")
    thick = float(np.clip(cand["thick"], MIN_THICK, MAX_THICK))
    proud = float(np.clip(cand.get("proud_h", 0.0), 0.0, MAX_PROUD))
    if cand["family"] == "holes":
        solid = holes_mask(cand["holes"])
    else:
        solid = radial_mask(
            cand["n_spokes"], cand["n_rings"], cand["spoke_w"],
            cand["ring_w"], cand["r_hub"], cand["rot"],
        )
    op = measure_openings(solid)
    op["aspect_p95"] = float(max(op["aspect_p95"], 1.0))
    if cand["family"] == "holes":
        g, rim = geometric_min_strut(cand["holes"])
        rstr = min_strut_width(solid)
        # trust geometry for hole-hole; raster only if it is clearly thinner
        # (and not the 1.2 mm rim picked up by the skeleton)
        strut = g if (g <= 0 or rstr >= g - 0.35 or rstr < MIN_RIM_MM + 0.15) else rstr
        cand["_rim"] = rim
    else:
        strut = min_strut_width(solid)
        rim = 99.0

    if arch == "bowl":
        dish_h = float(cand.get("dish_h", 6.0))
        insert = float(cand.get("insert_depth", dish_h))
        # bowl: dish is the insert (plus tiny collar lip)
        insert = float(np.clip(insert, MIN_INSERT, MAX_INSERT))
        dish_h = float(np.clip(dish_h, 0.0, insert))
        oh = overhang_deg(dish_h)
    else:
        # top grate + press-fit collar; shallow dish only
        insert = float(np.clip(cand.get("insert_depth", 7.0), MIN_INSERT, MAX_INSERT))
        dish_h = float(np.clip(cand.get("dish_h", 1.2), 0.0, 4.0))
        oh = overhang_deg(dish_h)

    viol = 0.0
    reasons = []
    if op["max_inscribed"] > MAX_SPHERE_MM + 0.05:
        viol += (op["max_inscribed"] - MAX_SPHERE_MM)
        reasons.append("sphere")
    if strut < MIN_STRUT_MM - 0.05:
        viol += (MIN_STRUT_MM - strut)
        reasons.append("strut")
    if op["n_open"] and op["min_inscribed"] < MIN_OPEN_HARD:
        viol += (MIN_OPEN_HARD - op["min_inscribed"])
        reasons.append("slit")
    if cand["family"] == "holes" and cand.get("_rim", 99) < MIN_RIM_MM - 0.06:
        viol += (MIN_RIM_MM - cand["_rim"])
        reasons.append("rim")
    if op["n_open"] == 0:
        viol += 5
        reasons.append("blind")
    if oh > MAX_OVERHANG_DEG + 0.5:
        viol += 0.2 * (oh - MAX_OVERHANG_DEG)
        reasons.append("overhang")
    if insert > MAX_INSERT or insert < MIN_INSERT:
        viol += 1
        reasons.append("depth")

    defl = 9.9
    if viol <= 1e-6:
        try:
            defl = plate_deflection(solid, thick, dish_h, insert)
            if defl >= 9.89:
                reasons.append("fe")
                # keep feasible: a failed stiffness estimate should not kill a
                # geometrically legal grate; score will just not get a defl bonus
        except Exception as e:
            reasons.append("fe")

    m = dict(
        **op,
        min_strut=float(strut),
        thick=thick,
        insert_depth=insert,
        dish_h=dish_h,
        proud_h=proud,
        arch=arch,
        family=cand["family"],
        overhang_deg=float(oh),
        defl_mm=float(defl),
        viol=float(viol),
        reasons=",".join(reasons),
        feasible=viol <= 1e-6,
    )
    m["score"] = score_of(m)
    m["solid"] = solid
    m["cand"] = cand
    return m


# ---------------------------------------------------------------------------
# Candidate generators
# ---------------------------------------------------------------------------
def _ok_holes(holes, min_strut=MIN_STRUT_MM, min_rim=MIN_RIM_MM, max_d=MAX_SPHERE_MM):
    hs = [(float(x), float(y), float(r)) for x, y, r in holes if r > 0.4]
    out = []
    for x, y, r in hs:
        if 2 * r > max_d + 1e-6:
            r = max_d / 2
        if math.hypot(x, y) + r > R_IN - min_rim + 1e-6:
            # push inward or shrink
            rho = math.hypot(x, y)
            if rho < 1e-6:
                r = min(r, R_IN - min_rim)
            else:
                # shrink r to fit
                r = min(r, max(0.0, R_IN - min_rim - rho))
        if r < MIN_OPEN_HARD / 2 - 0.2:
            continue
        out.append((x, y, r))
    # resolve overlaps by shrinking later holes
    cleaned = []
    for x, y, r in out:
        for x2, y2, r2 in cleaned:
            d = math.hypot(x - x2, y - y2)
            allow = r + r2 + min_strut
            if d < allow and d > 1e-6:
                r = max(0.0, d - r2 - min_strut)
        if r >= MIN_OPEN_HARD / 2 - 0.2:
            cleaned.append((x, y, r))
    return cleaned


def pack_equal(n, radius, rot=0.0, with_center=None):
    """Heuristic equal-circle packings inside a circle of given radius."""
    pts = []
    if n <= 0:
        return pts
    if n == 1 or (with_center is not False and n != 6):
        # many classic packs have a centre for n=7,8,9...
        pass
    # classic rings
    if n == 1:
        pts = [(0.0, 0.0)]
    elif n == 2:
        pts = [(radius * 0.5, 0.0), (-radius * 0.5, 0.0)]
    elif n == 3:
        for k in range(3):
            a = rot + k * 2 * np.pi / 3
            r = radius / (1 + 2 / np.sqrt(3)) * (2 / np.sqrt(3))  # rough
            r = radius * 0.5
            pts.append((r * math.cos(a), r * math.sin(a)))
    elif n == 4:
        for k in range(4):
            a = rot + k * np.pi / 2 + np.pi / 4
            r = radius * 0.5 * np.sqrt(2)
            pts.append((r * math.cos(a), r * math.sin(a)))
    elif n == 5:
        pts.append((0.0, 0.0))
        for k in range(4):
            a = rot + k * np.pi / 2
            pts.append((0.55 * radius * math.cos(a), 0.55 * radius * math.sin(a)))
    elif n == 6:
        for k in range(6):
            a = rot + k * np.pi / 3
            pts.append((0.55 * radius * math.cos(a), 0.55 * radius * math.sin(a)))
    elif n == 7:
        pts.append((0.0, 0.0))
        for k in range(6):
            a = rot + k * np.pi / 3
            pts.append((0.5 * radius * math.cos(a), 0.5 * radius * math.sin(a)))
    else:
        # centre + rings
        pts.append((0.0, 0.0))
        left = n - 1
        ring_n = []
        # prefer 6, then 8-12
        if left <= 8:
            ring_n = [left]
        elif left <= 18:
            a = min(6, left - 6)
            # typically 6 then the rest
            first = 6 if left >= 6 else left
            ring_n = [first, left - first] if left > first else [first]
            ring_n = [x for x in ring_n if x > 0]
        else:
            ring_n = [6, 12]
            if left > 18:
                ring_n.append(left - 18)
            else:
                ring_n = [6, left - 6]
        radii = np.linspace(0.42, 0.86, len(ring_n)) * radius
        used = 1
        for rn, rr in zip(ring_n, radii):
            for k in range(rn):
                a = rot + k * 2 * np.pi / rn + (0 if rn != 6 else 0)
                pts.append((rr * math.cos(a), rr * math.sin(a)))
            used += rn
    return pts


def relax_points(pts, min_dist, container_r, steps=80):
    p = np.array(pts, float)
    if len(p) == 0:
        return p
    for s in range(steps):
        step = 0.35 * (1 - s / steps)
        for i in range(len(p)):
            f = np.zeros(2)
            for j in range(len(p)):
                if i == j:
                    continue
                d = p[i] - p[j]
                dist = np.linalg.norm(d) + 1e-9
                if dist < min_dist:
                    f += (d / dist) * (min_dist - dist)
            # wall
            rho = np.linalg.norm(p[i]) + 1e-9
            if rho > container_r:
                f += -p[i] / rho * (rho - container_r)
            p[i] += step * f
        # project into container
        rho = np.linalg.norm(p, axis=1)
        over = rho > container_r
        if over.any():
            p[over] *= (container_r / rho[over])[:, None]
    return p


def make_holes_candidate(n=7, hole_d=9.0, strut=1.9, rot=0.0,
                         insert=7.0, dish=1.5, thick=2.2, proud=0.0,
                         arch="top_grate", seed=None):
    hole_d = float(np.clip(hole_d, MIN_OPEN_HARD, MAX_SPHERE_MM))
    strut = float(max(strut, MIN_STRUT_MM))
    r = hole_d / 2
    container = R_IN - MIN_RIM_MM - r
    if container < 0.5:
        container = 0.5
        r = max(MIN_OPEN_HARD / 2, R_IN - MIN_RIM_MM - container)
    pts = pack_equal(n, max(container, 0.5), rot)
    if seed is not None and len(pts):
        rng = np.random.default_rng(seed)
        pts = [(x + rng.normal(0, 0.25), y + rng.normal(0, 0.25)) for x, y in pts]
    min_dist = 2 * r + strut
    pts = relax_points(pts, min_dist, container, steps=60)
    holes = _ok_holes([(x, y, r) for x, y in pts], min_strut=strut)
    return dict(family="holes", holes=holes, thick=thick, insert_depth=insert,
                dish_h=dish, proud_h=proud, arch=arch, n_target=n, hole_d=hole_d,
                strut=strut, rot=rot)


def make_radial_candidate(n_spokes=6, n_rings=1, spoke_w=2.0, ring_w=2.0,
                          r_hub=4.5, rot=0.0, insert=7.0, dish=1.5,
                          thick=2.2, proud=0.0, arch="top_grate"):
    return dict(
        family="radial", n_spokes=int(n_spokes), n_rings=int(n_rings),
        spoke_w=float(max(spoke_w, MIN_STRUT_MM)),
        ring_w=float(max(ring_w, MIN_STRUT_MM)),
        r_hub=float(np.clip(r_hub, 2.5, 8.0)),
        rot=float(rot), thick=thick, insert_depth=insert, dish_h=dish,
        proud_h=proud, arch=arch,
    )


def random_candidate(g=0):
    arch = RNG.choice(["top_grate", "top_grate", "bowl"])
    insert = float(RNG.uniform(4.5, 16.0 if arch == "bowl" else 12.0))
    if arch == "bowl":
        # slope limit: dish_h such that overhang <= 50 deg
        max_dish = 0.5 * R_IN * math.tan(math.radians(MAX_OVERHANG_DEG - 1))
        dish = float(np.clip(insert, MIN_INSERT, min(insert, max_dish)))
        insert = max(insert, dish)
    else:
        dish = float(RNG.uniform(0.0, 3.0))
    thick = float(RNG.uniform(2.0, 2.8))
    proud = float(RNG.choice([0.0, 0.0, 0.0, 0.4, 1.0]))
    if RNG.random() < 0.72:
        n = int(RNG.choice([3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 19]))
        # early gens: smaller / messier holes; later allowed larger
        dhi = 8.0 + 4.0 * min(g, 8) / 8.0
        hole_d = float(RNG.uniform(6.0, dhi))
        strut = float(RNG.uniform(1.8, 2.6))
        rot = float(RNG.uniform(0, 2 * np.pi))
        return make_holes_candidate(n, hole_d, strut, rot, insert, dish, thick, proud, arch,
                                    seed=int(RNG.integers(0, 1_000_000)))
    nsp = int(RNG.choice([4, 5, 6, 7, 8]))
    nr = int(RNG.choice([0, 1, 1, 2]))
    return make_radial_candidate(
        nsp, nr, float(RNG.uniform(1.8, 2.8)), float(RNG.uniform(1.8, 2.6)),
        float(RNG.uniform(3.0, 6.5)), float(RNG.uniform(0, 2 * np.pi)),
        insert, dish, thick, proud, arch,
    )


def mutate(cand, g=0):
    c = json.loads(json.dumps({k: v for k, v in cand.items() if k != "holes"}))
    # deepcopy holes separately
    if cand["family"] == "holes":
        c["holes"] = [(x, y, r) for x, y, r in cand["holes"]]
        c["family"] = "holes"
        for k in ("n_target", "hole_d", "strut", "rot"):
            if k in cand:
                c[k] = cand[k]
    else:
        c = dict(cand)
    c["thick"] = float(np.clip(c["thick"] + RNG.normal(0, 0.12), MIN_THICK, MAX_THICK))
    c["insert_depth"] = float(np.clip(c["insert_depth"] + RNG.normal(0, 0.8), MIN_INSERT, MAX_INSERT))
    c["proud_h"] = float(np.clip(c.get("proud_h", 0) + RNG.normal(0, 0.15), 0, MAX_PROUD))
    if c.get("arch", "top_grate") == "bowl":
        max_dish = 0.5 * R_IN * math.tan(math.radians(MAX_OVERHANG_DEG - 1))
        c["dish_h"] = float(np.clip(c.get("dish_h", c["insert_depth"]) + RNG.normal(0, 0.6),
                                    3.0, min(max_dish, c["insert_depth"], MAX_INSERT)))
        c["insert_depth"] = max(c["insert_depth"], c["dish_h"])
        if RNG.random() < 0.1:
            c["arch"] = "top_grate"
            c["dish_h"] = float(np.clip(c["dish_h"], 0, 3.5))
    else:
        c["dish_h"] = float(np.clip(c.get("dish_h", 1.2) + RNG.normal(0, 0.25), 0.0, 4.0))
        if RNG.random() < 0.08:
            c["arch"] = "bowl"
            max_dish = 0.5 * R_IN * math.tan(math.radians(MAX_OVERHANG_DEG - 1))
            c["dish_h"] = float(np.clip(max(c["insert_depth"], 6.0), 4.0, max_dish))
            c["insert_depth"] = c["dish_h"]
    if c["family"] == "holes":
        holes = list(c["holes"])
        if holes and RNG.random() < 0.5:
            # grow / shrink all radii (the key flow operator)
            scale = float(np.clip(1.0 + RNG.normal(0, 0.08), 0.85, 1.15))
            holes = [(x, y, r * scale) for x, y, r in holes]
        if holes and RNG.random() < 0.45:
            holes = [(x + RNG.normal(0, 0.35), y + RNG.normal(0, 0.35), r) for x, y, r in holes]
        if holes and RNG.random() < 0.25:
            # rotate
            ang = RNG.normal(0, 0.15)
            ca, sa = math.cos(ang), math.sin(ang)
            holes = [(ca * x - sa * y, sa * x + ca * y, r) for x, y, r in holes]
        if RNG.random() < 0.15:
            # add or drop a hole and relax
            n = max(3, len(holes) + int(RNG.choice([-2, -1, 1, 1, 2])))
            rmean = np.mean([h[2] for h in holes]) if holes else 4.5
            return make_holes_candidate(
                n, 2 * rmean, c.get("strut", MIN_STRUT_MM),
                float(c.get("rot", 0) + RNG.normal(0, 0.2)),
                c["insert_depth"], c["dish_h"], c["thick"], c["proud_h"], c.get("arch", "top_grate"),
                seed=int(RNG.integers(0, 1e6)),
            )
        if holes and RNG.random() < 0.3:
            rmean = np.mean([h[2] for h in holes])
            pts = relax_points([(x, y) for x, y, _ in holes],
                               2 * rmean + MIN_STRUT_MM,
                               max(0.5, R_IN - MIN_RIM_MM - rmean), steps=40)
            holes = [(p[0], p[1], rmean) for p in pts]
        c["holes"] = _ok_holes(holes)
        return c
    # radial mutate
    c["n_spokes"] = int(np.clip(c["n_spokes"] + int(RNG.choice([-1, 0, 0, 1])), 4, 10))
    c["n_rings"] = int(np.clip(c["n_rings"] + int(RNG.choice([-1, 0, 0, 1])), 0, 3))
    c["spoke_w"] = float(np.clip(c["spoke_w"] + RNG.normal(0, 0.12), MIN_STRUT_MM, 3.2))
    c["ring_w"] = float(np.clip(c["ring_w"] + RNG.normal(0, 0.12), MIN_STRUT_MM, 3.2))
    c["r_hub"] = float(np.clip(c["r_hub"] + RNG.normal(0, 0.25), 2.5, 8.0))
    c["rot"] = float(c["rot"] + RNG.normal(0, 0.2))
    if RNG.random() < 0.12:
        return make_holes_candidate(
            int(RNG.choice([6, 7, 8])), float(RNG.uniform(8, 11.5)),
            1.9, float(RNG.uniform(0, 2 * np.pi)),
            c["insert_depth"], c["dish_h"], c["thick"], c["proud_h"], c.get("arch", "top_grate"),
        )
    return c


# ---------------------------------------------------------------------------
# Iteration top-view frames
# ---------------------------------------------------------------------------
def _font(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_iter_frame(m, path, gen, ngen, tag="best of generation"):
    """Clean top-view PNG of a candidate with key numbers overlaid."""
    fig = plt.figure(figsize=(7.2, 8.4), dpi=140)
    fig.patch.set_facecolor("#F4F0EA")
    # main top view
    ax = fig.add_axes([0.06, 0.22, 0.88, 0.72])
    ax.set_facecolor("#F4F0EA")
    # ceramic / flange context
    ax.add_patch(plt.Circle((0, 0), 32, color="#D8D3CC", zorder=0))
    ax.add_patch(plt.Circle((0, 0), R_FLANGE, color="#C7CCD1", zorder=1))  # chrome seat
    # part flange
    ax.add_patch(plt.Circle((0, 0), R_FLANGE, color="#E6E3DC", zorder=2))
    # bore / grate disc
    # paint from solid mask
    L = Lpix
    extent = (-L / 2, L / 2, -L / 2, L / 2)
    # RGBA image: solid grate beige, openings dark drain, outside transparent
    rgba = np.zeros((Npix, Npix, 4))
    # drain hole background
    rgba[INNER] = (0.22, 0.24, 0.27, 1.0)
    # solid grate
    sg = m["solid"] & (Rg <= R_FLANGE + 0.01)
    rgba[sg] = (0.905, 0.890, 0.863, 1.0)
    # flange ring already drawn; mask outside flange
    rgba[Rg > R_FLANGE] = (0, 0, 0, 0)
    ax.imshow(rgba, origin="lower", extent=extent, interpolation="bilinear", zorder=3)
    # outlines
    ax.add_patch(plt.Circle((0, 0), R_FLANGE, fill=False, ec="#8A8F96", lw=1.1, zorder=5))
    ax.add_patch(plt.Circle((0, 0), R_IN, fill=False, ec="#6E6258", lw=0.6, ls="--", zorder=5, alpha=0.6))
    ax.set_xlim(-26, 26)
    ax.set_ylim(-26, 26)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Iteration {gen:02d}  ·  {tag}", fontsize=13, color="#2A2622", pad=8, fontweight="medium")

    # side-view inset of depth
    ax2 = fig.add_axes([0.70, 0.24, 0.24, 0.16])
    ax2.set_facecolor("#EDE9E2")
    _draw_side(ax2, m)
    ax2.set_title("side", fontsize=7, color="#5A534C", pad=1)
    ax2.tick_params(length=0, labelbottom=False, labelleft=False)
    for s in ax2.spines.values():
        s.set_color("#C8C2B8")

    # metrics bar
    feas = "FEASIBLE" if m["feasible"] else "infeasible: " + (m.get("reasons") or "—")
    color = "#1F6B4A" if m["feasible"] else "#8B2E1A"
    txt = (
        f"open area  {m['open_frac']*100:.1f}%     "
        f"max ball  {m['max_inscribed']:.2f} mm     "
        f"min strut  {m['min_strut']:.2f} mm\n"
        f"depth  {m['insert_depth']:.1f} mm into drain"
        f"  (dish {m['dish_h']:.1f}"
        f"{', bowl' if m['arch']=='bowl' else ', top grate'}"
        f"{'' if m['proud_h']<0.05 else f', proud {m['proud_h']:.1f}'})     "
        f"score  {m['score']:.3f}"
    )
    fig.text(0.06, 0.13, txt, fontsize=10, color="#2A2622", family="DejaVu Sans", va="top")
    fig.text(0.06, 0.05, f"{feas}   ·   {m['family']}   ·   {m['n_open']} openings   ·   "
             f"defl ~{m['defl_mm']:.2f} mm at 15 N   ·   gen {gen}/{ngen}",
             fontsize=8, color=color, va="top")
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def _draw_side(ax, m):
    # schematic at z=0 seat, +z up (use orientation)
    Rf, Ri, t = R_FLANGE, R_IN, FLANGE_T
    ins, dish, proud, thick = m["insert_depth"], m["dish_h"], m["proud_h"], m["thick"]
    ax.set_xlim(-25, 25)
    ax.set_ylim(-ins - 2.5, t + proud + 3)
    ax.set_aspect("equal")
    # seat
    ax.plot([-25, -Ri], [0, 0], color="#8A8F96", lw=1.4)
    ax.plot([Ri, 25], [0, 0], color="#8A8F96", lw=1.4)
    # flange
    ax.add_patch(plt.Rectangle((-Rf, 0), Rf - Ri, t + proud, color="#E6E3DC"))
    ax.add_patch(plt.Rectangle((Ri, 0), Rf - Ri, t + proud, color="#E6E3DC"))
    # collar
    ax.add_patch(plt.Rectangle((-R_LOC, -ins), R_LOC - Ri, ins, color="#E6E3DC"))
    ax.add_patch(plt.Rectangle((Ri, -ins), R_LOC - Ri, ins, color="#E6E3DC"))
    # grate mid-surface
    xs = np.linspace(-Ri, Ri, 80)
    if m["arch"] == "bowl":
        ztop = (t + proud) - dish * (1 - (xs / Ri) ** 2)
    else:
        ztop = (t + proud) - dish * (1 - (xs / Ri) ** 2)
    zbot = ztop - thick
    ax.fill_between(xs, zbot, ztop, color="#C9C3B8", lw=0)
    ax.plot(xs, ztop, color="#6E6258", lw=0.8)


def metrics_row(gen, m, kind="generation_best"):
    return dict(
        gen=gen,
        kind=kind,
        feasible=int(m["feasible"]),
        score=round(m["score"], 4),
        open_area_pct=round(m["open_frac"] * 100, 2),
        max_sphere_mm=round(m["max_inscribed"], 3),
        min_inscribed_mm=round(m["min_inscribed"], 3),
        min_strut_mm=round(m["min_strut"], 3),
        n_open=m["n_open"],
        aspect_p95=round(m["aspect_p95"], 3),
        insert_depth_mm=round(m["insert_depth"], 2),
        dish_h_mm=round(m["dish_h"], 2),
        proud_h_mm=round(m["proud_h"], 2),
        thick_mm=round(m["thick"], 2),
        arch=m["arch"],
        family=m["family"],
        overhang_deg=round(m["overhang_deg"], 2),
        defl_mm=round(m["defl_mm"], 3),
        reasons=m.get("reasons", ""),
    )


# ---------------------------------------------------------------------------
# 3-D build of a holes / radial candidate (CadQuery + optional dish warp)
# ---------------------------------------------------------------------------
def build_mesh(m):
    import cadquery as cq
    import trimesh

    cand = m["cand"]
    thick = m["thick"]
    insert = m["insert_depth"]
    dish = m["dish_h"]
    proud = m["proud_h"]
    arch = m["arch"]

    z_flange_top = FLANGE_T + proud
    # collar goes from z=0 down to -insert (use orientation)
    # lead-in at the tip
    od = 2 * R_LOC
    id_ = 2 * R_IN

    wp = cq.Workplane("XY")
    # flange disc
    flange = (
        cq.Workplane("XY")
        .circle(R_FLANGE)
        .circle(R_IN)
        .extrude(z_flange_top)
    )
    if FLANGE_CH > 0 and z_flange_top > FLANGE_CH:
        try:
            flange = flange.faces(">Z").edges("%Circle").chamfer(FLANGE_CH * 0.9)
        except Exception:
            pass

    # collar (outer cylinder minus inner, plus lead-in by cutting a cone/chamfer)
    collar_h = insert
    collar = (
        cq.Workplane("XY")
        .circle(R_LOC)
        .circle(R_IN)
        .extrude(-collar_h)
    )
    # 45° lead-in at the bottom outer edge
    try:
        collar = collar.faces("<Z").edges("%Circle").chamfer(min(LEADIN, 0.65, collar_h - 0.2))
    except Exception:
        pass

    body = flange.union(collar)

    # grate slab: for top_grate, from z_flange_top-thick to z_flange_top (then warp dish)
    # for bowl, build a revolved dish shell already at the right depth
    if arch == "bowl":
        # revolved parabolic shell, thickness `thick`, drop `dish` at centre
        # top: z = z_flange_top - dish*(1-(r/R_IN)^2)
        rs = np.linspace(0, R_IN, 40)
        ztop = z_flange_top - dish * (1 - (rs / R_IN) ** 2)
        zbot = ztop - thick
        # profile going out along the top, down at the rim, back along the bottom
        pts_top = [(float(r), float(z)) for r, z in zip(rs, ztop)]
        pts_bot = [(float(r), float(z)) for r, z in zip(rs[::-1], zbot[::-1])]
        poly = pts_top + pts_bot
        # close at centre if needed
        grate = cq.Workplane("XZ").polyline(poly).close().revolve(360)
    else:
        grate = cq.Workplane("XY").circle(R_IN + 0.05).extrude(z_flange_top - thick).translate((0, 0, 0))
        # actually extrude from z = z_flange_top-thick
        grate = (
            cq.Workplane("XY")
            .workplane(offset=z_flange_top - thick)
            .circle(R_IN + 0.02)
            .extrude(thick)
        )

    body = body.union(grate)

    # cut openings
    def cut_cyl(body, x, y, r, z0, z1, chamfer=0.45):
        h = (z1 - z0) + 2.0
        cyl = cq.Workplane("XY").workplane(offset=z0 - 1.0).center(x, y).circle(r).extrude(h)
        try:
            body = body.cut(cyl)
        except Exception:
            return body
        return body

    if cand["family"] == "holes":
        for x, y, r in cand["holes"]:
            body = cut_cyl(body, x, y, r, -insert - 1, z_flange_top + 2)
    else:
        # approximate radial openings by cutting the void of the 2D mask as
        # prisms is heavy; instead cut from a tessellated 2D solid via occupied
        # sectors: build a solid of the VOID and subtract.
        # Use many small cylinder punches? Better: cut from SVG-like 2D.
        solid = m["solid"]
        void = (~solid) & INNER
        # marching-squares style: extract polygons of openings and extrude-cut
        from skimage import measure as skm
        contours = skm.find_contours(void.astype(float), 0.5)
        for cnt in contours:
            # cnt in pixel row,col -> y,x
            if len(cnt) < 8:
                continue
            ys = cnt[:, 0] * PX - Lpix / 2
            xs = cnt[:, 1] * PX - Lpix / 2
            # subsample
            step = max(1, len(xs) // 80)
            pts = [(float(xs[i]), float(ys[i])) for i in range(0, len(xs), step)]
            if len(pts) < 6:
                continue
            try:
                wp = cq.Workplane("XY").workplane(offset=-insert - 1).polyline(pts).close().extrude(insert + z_flange_top + 3)
                body = body.cut(wp)
            except Exception:
                continue

    # tessellate
    try:
        # chamfer hole rims on the top face — optional, may fail
        try:
            body = body.faces(">Z").edges("%Circle").chamfer(0.4)
        except Exception:
            pass
        verts, faces = body.val().tessellate(0.08, 0.2)
        tm = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=True)
    except Exception as e:
        # fallback SDF / voxel
        tm = _voxel_mesh(m)
        return tm

    tm.fill_holes()
    tm.remove_unreferenced_vertices()
    # dish warp for top_grate
    if arch != "bowl" and dish > 0.05:
        v = tm.vertices.copy()
        x, y, z = v[:, 0], v[:, 1], v[:, 2]
        r = np.hypot(x, y)
        fade = np.clip((R_IN - r) / 1.2, 0, 1)
        # only warp grate (inside bore, in the grate z band)
        z0, z1 = z_flange_top - thick - 0.4, z_flange_top + 0.2
        sel = (r < R_IN - 0.15) & (z >= z0) & (z <= z1)
        drop = dish * (1 - (np.clip(r, 0, R_IN) / R_IN) ** 2) * fade
        v[sel, 2] = z[sel] - drop[sel]
        tm.vertices = v
        tm.fix_normals()
    return tm


def _voxel_mesh(m):
    import trimesh
    from skimage import measure as skm
    cand = m["cand"]
    thick, insert, dish, proud = m["thick"], m["insert_depth"], m["dish_h"], m["proud_h"]
    pz = 0.12
    zmin, zmax = -insert - 0.4, FLANGE_T + proud + 0.4
    zs = np.arange(zmin, zmax, pz)
    # reuse XY grid but maybe coarse
    solid2 = m["solid"]
    vol = []
    z_top = FLANGE_T + proud
    for z in zs:
        sl = np.zeros_like(solid2, dtype=bool)
        # flange
        if 0 <= z <= z_top:
            sl |= (Rg <= R_FLANGE) & (Rg >= R_IN)
        # collar
        if -insert <= z <= 0.05:
            lead = max(0.0, LEADIN - (z + insert))
            sl |= (Rg <= R_LOC - lead) & (Rg >= R_IN)
        # grate
        rsafe = np.maximum(Rg, 1e-6)
        if m["arch"] == "bowl":
            zt = z_top - dish * (1 - (np.clip(Rg, 0, R_IN) / R_IN) ** 2)
        else:
            fade = np.clip((R_IN - Rg) / 1.2, 0, 1)
            zt = z_top - dish * (1 - (np.clip(Rg, 0, R_IN) / R_IN) ** 2) * fade
        zb = zt - thick
        in_grate = (z >= zb) & (z <= zt) & (Rg <= R_IN + 0.05)
        sl |= in_grate & solid2
        vol.append(sl)
    vol = np.stack(vol, axis=2)
    # marching cubes; skimage expects z,y,x or y,x with a 3D array (row,col,z)
    vox = vol
    try:
        verts, faces, nrm, _ = skm.marching_cubes(vox.astype(np.float32), level=0.5, spacing=(PX, PX, pz))
    except Exception:
        # empty
        return trimesh.Trimesh()
    # verts are (row, col, z) = (y, x, z)
    y = verts[:, 0] - Lpix / 2
    x = verts[:, 1] - Lpix / 2
    z = verts[:, 2] + zmin
    tm = trimesh.Trimesh(vertices=np.column_stack([x, y, z]), faces=faces, process=True)
    trimesh.smoothing.filter_taubin(tm, iterations=8)
    tm.fill_holes()
    return tm


def to_print_orientation(tm):
    """Flip so flange top sits on the bed (z_print = z_flange_top - z_use)."""
    import trimesh
    t = tm.copy()
    ztop = FLANGE_T  # proud may lift; use actual max of flange
    # use the mesh's max z near the flange ring as the bed plane
    t.vertices[:, 2] = t.vertices[:, 2].max() - t.vertices[:, 2]
    # shift so min z = 0
    t.vertices[:, 2] -= t.vertices[:, 2].min()
    return t


# ---------------------------------------------------------------------------
# Final renders + comparison + slice
# ---------------------------------------------------------------------------
def render_final(tm_use, out_top, out_34):
    import pyvista as pv
    pv.OFF_SCREEN = True
    mesh = pv.wrap(tm_use).compute_normals(split_vertices=True, feature_angle=50)
    PART = dict(color="#E6E3DC", specular=0.5, specular_power=40, ambient=0.06, diffuse=0.72, smooth_shading=True)

    def plotter():
        p = pv.Plotter(off_screen=True, window_size=(1600, 1200), lighting="none")
        p.set_background("#ECE8E1", top="#FBFAF8")
        p.add_light(pv.Light(position=(70, -90, 160), focal_point=(0, 0, 0), intensity=0.95))
        p.add_light(pv.Light(position=(-120, 40, 80), focal_point=(0, 0, 0), intensity=0.4))
        p.add_light(pv.Light(light_type="headlight", intensity=0.3))
        p.enable_anti_aliasing("ssaa")
        try:
            p.enable_ssao(radius=1.5, bias=0.02, kernel_size=128)
        except Exception:
            pass
        return p

    def drain(p):
        FT = FLANGE_T
        RB = 17.85
        ceramic = pv.Disc(inner=24.2, outer=70, c_res=200).translate((0, 0, FT))
        waste_top = pv.Cylinder(center=(0, 0, FT / 2), direction=(0, 0, 1), radius=24.2, height=FT, resolution=200, capping=False)
        seat = pv.Disc(inner=RB, outer=24.2, c_res=200)
        bore = pv.Cylinder(center=(0, 0, -20), direction=(0, 0, 1), radius=RB, height=40, resolution=200, capping=False)
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


def measure_old_catcher():
    """Max passable sphere and open-area of the previous two-level Voronoi (C, then B)."""
    import trimesh
    results = {}
    for name, path in (
        ("C", Path("./hair_catcher_C_use.stl")),
        ("C_earlier", Path("./catcher-C-use-orientation.stl")),
        ("B", Path("./catcher-B-use-orientation.stl")),
    ):
        if not path.exists():
            continue
        tm = trimesh.load(path)
        # slice at several z, measure openings in the disc r<R_IN
        zs = np.linspace(tm.bounds[0, 2] + 0.4, tm.bounds[1, 2] - 0.2, 18)
        # build a raster by checking occupancy via nearest ray / section
        # Use voxelization of a central column for speed
        px = 0.15
        n = int(round((2 * R_IN + 2) / px))
        c = (np.arange(n) + 0.5) * px - (n * px) / 2
        X, Y = np.meshgrid(c, c, indexing="xy")
        R = np.hypot(X, Y)
        inner = R < R_IN
        pts_xy = np.stack([X[inner], Y[inner]], 1)
        max_ins_at = []
        open_at = []
        for z in zs:
            # even-odd? use contains via proximity: section
            try:
                sec = tm.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            except Exception:
                continue
            if sec is None:
                continue
            try:
                poly = sec.to_2D()[0]
            except Exception:
                continue
            # rasterize: point in path
            # trimesh Path2D has contains
            try:
                contains = poly.contains_points(pts_xy)
            except Exception:
                continue
            solid = np.zeros_like(inner)
            tmp = np.zeros(inner.sum(), dtype=bool)
            tmp[contains] = True
            solid[inner] = tmp
            void = (~solid) & inner
            if not void.any():
                max_ins_at.append(0.0)
                open_at.append(0.0)
                continue
            edt = distance_transform_edt(void) * px
            max_ins_at.append(float(2 * edt.max()))
            open_at.append(float(void.sum() / inner.sum()))
        if not max_ins_at:
            continue
        # conservative straight-drop sphere: min over z of the max opening? 
        # A sphere must fit through EVERY layer at some XY (can slide).
        # Approximate: tightest layer's max inscribed (if holes don't align,
        # true value can be smaller). Also report per-layer max.
        results[name] = dict(
            path=str(path),
            max_inscribed_any_layer=float(max(max_ins_at)),
            max_sphere_tightest_layer=float(min(max_ins_at)),
            open_frac_median=float(np.median(open_at)),
            open_frac_min=float(min(open_at)),
            bounds=tm.bounds.tolist(),
            extents=(tm.bounds[1] - tm.bounds[0]).tolist(),
        )
    # published mid-plane stats as a backup
    results["B_json"] = dict(
        level1_open=0.5395, level2_open=0.4381, straight_through=0.2671,
        level2_max_inscribed=4.963, level2_min_inscribed=3.553,
    )
    results["C_json"] = dict(
        level1_open=0.5054, level2_open=0.4484, straight_through=0.2553,
        level2_max_inscribed=5.614, level2_min_inscribed=3.586,
    )
    return results


def write_contact_sheet(paths, out):
    ims = [Image.open(p).convert("RGB") for p in paths]
    n = len(ims)
    cols = 4
    rows = int(math.ceil(n / cols))
    w, h = ims[0].size
    # resize to a consistent cell
    cell_w, cell_h = 480, int(480 * h / w)
    sheet = Image.new("RGB", (cols * cell_w + 16, rows * cell_h + 16), (244, 240, 234))
    for i, im in enumerate(ims):
        im = im.resize((cell_w - 8, cell_h - 8), Image.Resampling.LANCZOS)
        r, c = divmod(i, cols)
        sheet.paste(im, (8 + c * cell_w, 8 + r * cell_h))
    sheet.save(out, quality=95)
    return out


def write_gif(paths, out, duration=800):
    ims = [Image.open(p).convert("P", palette=Image.Palette.ADAPTIVE, colors=240) for p in paths]
    ims[0].save(out, save_all=True, append_images=ims[1:], duration=duration, loop=0, optimize=False)
    return out


def optimization_chart(history_rows, all_rows, best_hist, out):
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.6), dpi=140)
    fig.patch.set_facecolor("#F7F4EF")
    gens = [r["gen"] for r in history_rows]
    # score
    ax = axes[0, 0]
    ax.plot(gens, [r["score"] for r in history_rows], "-o", color="#1F6B4A", lw=2, ms=5)
    ax.set_title("Best score by generation")
    ax.set_xlabel("generation")
    ax.set_ylabel("score")
    ax.grid(True, alpha=0.3)
    # open area
    ax = axes[0, 1]
    ax.plot(gens, [r["open_area_pct"] for r in history_rows], "-o", color="#2C5F8A", lw=2, ms=5, label="best of gen")
    ax.set_title("Open area (best of generation)")
    ax.set_xlabel("generation")
    ax.set_ylabel("open area %")
    ax.grid(True, alpha=0.3)
    # scatter all candidates
    ax = axes[1, 0]
    feas = [r for r in all_rows if r["feasible"]]
    no = [r for r in all_rows if not r["feasible"]]
    if no:
        ax.scatter([r["open_area_pct"] for r in no], [r["defl_mm"] for r in no],
                   s=12, c="#C9B7AE", alpha=0.5, label="infeasible")
    if feas:
        sc = ax.scatter([r["open_area_pct"] for r in feas], [r["defl_mm"] for r in feas],
                        s=18, c=[r["gen"] for r in feas], cmap="viridis", alpha=0.85, label="feasible")
        fig.colorbar(sc, ax=ax, label="generation")
    ax.set_xlabel("open area %")
    ax.set_ylabel("predicted deflection mm (15 N)")
    ax.set_title("All candidates")
    ax.grid(True, alpha=0.3)
    # depth vs open of gen bests
    ax = axes[1, 1]
    ax.plot(gens, [r["insert_depth_mm"] for r in history_rows], "-o", color="#8B5A2B", lw=2, ms=5, label="insert depth")
    ax.plot(gens, [r["max_sphere_mm"] for r in history_rows], "-s", color="#5A3D7A", lw=2, ms=5, label="max ball")
    ax.axhline(MAX_SPHERE_MM, color="#5A3D7A", ls="--", lw=0.8, alpha=0.6)
    ax.set_xlabel("generation")
    ax.set_ylabel("mm")
    ax.set_title("Depth and max passable sphere (best of gen)")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(True, alpha=0.3)
    for a in axes.ravel():
        a.set_facecolor("#FBF9F6")
    fig.tight_layout()
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)


def comparison_chart(old, new_m, out):
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=140)
    fig.patch.set_facecolor("#F7F4EF")
    ax.set_facecolor("#FBF9F6")
    labels = ["Open area %\n(flow)", "Max passable\nsphere mm", "Min strut mm"]
    # old C: use json mid-plane level-2 (the tighter hair filter) + straight-through
    old_open = old.get("C_json", {}).get("straight_through", 0.255) * 100
    old_sphere = old.get("C_json", {}).get("level2_max_inscribed", 5.61)
    old_strut = 1.67  # C level2 min strut measured
    # also show level-2 open for honesty? The relevant flow is straight-through
    # for a two-level part. I'll plot straight-through vs new open area,
    # and also annotate level-2 open.
    new_open = new_m["open_frac"] * 100
    new_sphere = new_m["max_inscribed"]
    new_strut = new_m["min_strut"]
    x = np.arange(len(labels))
    w = 0.35
    b1 = ax.bar(x - w / 2, [old_open, old_sphere, old_strut], w, color="#A39B90", label="Old catcher C (two-level Voronoi)")
    b2 = ax.bar(x + w / 2, [new_open, new_sphere, new_strut], w, color="#1F6B4A", label="New toy guard (computer search)")
    ax.set_xticks(x, labels)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("Old hair catcher vs new toy guard")
    for bars in (b1, b2):
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.4,
                    f"{r.get_height():.1f}", ha="center", va="bottom", fontsize=8, color="#2A2622")
    ax.annotate("Old open area is the straight-through fraction\n"
                f"(level-2 open was {old.get('C_json',{}).get('level2_open',0.45)*100:.0f}%). "
                "New part is a single grate.",
                xy=(0, 0), xytext=(0.02, -0.28), textcoords="axes fraction", fontsize=7.5, color="#5A534C")
    ax.set_ylim(0, max(new_open, old_sphere, new_sphere) * 1.25)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def slice_stl(stl_path):
    ini = OUT / "slicer-a1mini-pla-basic.ini"
    gcode = OUT / "basin_guard_v2-print.gcode"
    cmd = [
        "prusa-slicer",
        "--load", str(ini),
        "--export-gcode",
        "--output", str(gcode),
        str(stl_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    report = OUT / "slice-report.txt"
    text = ""
    if gcode.exists():
        g = gcode.read_text(errors="ignore")
        # typical PrusaSlicer comments
        import re
        def grab(pat, default="—"):
            m = re.search(pat, g)
            return m.group(1) if m else default
        filament_m = grab(r"; filament used \[mm\] = ([0-9.]+)")
        filament_g = grab(r"; filament used \[g\] = ([0-9.]+)")
        filament_cm3 = grab(r"; filament used \[cm3\] = ([0-9.]+)")
        time_s = grab(r"; estimated printing time \(normal mode\) = ([^\n]+)")
        layers = grab(r"; total layers count = ([0-9]+)")
        # sometimes different format
        if time_s == "—":
            time_s = grab(r"; estimated printing time[^=]*= ([^\n]+)")
        text = (
            "Basin toy guard v2 — slice estimate\n"
            "===================================\n"
            "Slicer:    PrusaSlicer 2.9.2 CLI on this machine (stand-in for OrcaSlicer / Bambu Studio)\n"
            "Profile:   slicer-a1mini-pla-basic.ini (A1 mini 180x180, 0.4 nozzle, PLA Basic 1.24 g/cm3)\n"
            "Settings:  0.20 mm layers, 0.42 mm lines, 4 perimeters, 5 top/5 bottom, 20% gyroid,\n"
            "           220 C nozzle / 65 C bed, no brim, support_material = 0\n"
            f"File:      {stl_path.name}  (flange top on the bed; collar / dish grow upward)\n"
            "\n"
            f"{gcode.name}\n"
            f"  filament: {filament_m} mm / {filament_cm3} cm3 / {filament_g} g\n"
            f"  time:     {time_s} (normal mode)\n"
            f"  layers:   {layers}\n"
            "  supports: none requested; this is an estimate only. Nothing was sent to the printer.\n"
            "\n"
            "OrcaSlicer was not available here; this PrusaSlicer profile is the same stand-in used\n"
            "for the earlier catcher. Bambu Studio / Orca on the A1 mini may finish a little faster.\n"
        )
        if r.returncode != 0:
            text += f"\nprusa-slicer stderr (exit {r.returncode}):\n{r.stderr[-2000:]}\n"
    else:
        text = (
            "Slice failed or produced no gcode.\n"
            f"cmd: {' '.join(cmd)}\n"
            f"exit {r.returncode}\nstdout:\n{r.stdout[-2000:]}\nstderr:\n{r.stderr[-2000:]}\n"
        )
    report.write_text(text)
    return text, r.returncode


def write_readme(best, old, slice_text, n_eval):
    (OUT / "README.md").write_text(f"""# Basin toy guard v2 — computer-designed drain insert

**Status: preview + slice only. Do not print until the user says go.**

The goal changed. This is no longer a hair catcher. Hair and water should
**drop through**; the insert only has to stop a baby's toys from falling
down the drain.

The grate was not drawn by hand. A generational search produced and scored
candidates against the rules below, and the winner was built as a printable
STL. Each generation's best is in `iterations/`.

## Fit (fixed — reused, not invented)

From the earlier De40 catcher work (`.`):

| | |
|---|---|
| Waste | De40 / DN40 PVC-U, GB/T 5836.1-2018; open hole measured ~35 mm |
| Collar CAD OD | **35.21 mm** → target **≈35.10 mm as printed** (0.3 % PLA shrink) |
| Collar ID / wall | 32.01 mm / 1.6 mm; 0.7 mm 45° lead-in |
| Flange | Ø46.0 × 1.6 mm (seat diameter was never measured — same assumption as before) |

## Toy-block rule (changeable)

`MAX_SPHERE_MM = {MAX_SPHERE_MM:.1f}` mm. No opening may admit a sphere larger than this.

ASTM F963 / 16 CFR 1501 uses a 31.7 mm small-parts cylinder (choking). That
is almost this grate's 32 mm inner diameter, so it is not a useful opening
size. **12 mm** sits below a standard marble (16 mm) and DUPLO's ~16 mm
module, and blocks typical bath toys, teething rings and 1-jiao / 5-jiao /
1-yuan coins (19–25 mm). Rounded 12 mm openings are well above the ~5–6 mm
scale where hair usually snags. It will **not** reliably stop a 1×1 LEGO
(~8 mm) or small beads — say if her smallest toys are smaller and the limit
will be tightened.

## Depth (free in the search)

Stopper / overflow travel were never measured. Bounds used:

- At least **{MIN_INSERT:.0f} mm** into the bore (stable press-fit, includes the lead-in)
- At most **{MAX_INSERT:.0f} mm** into the bore (the original cup catcher for this
  drain was 18 mm deep; nothing is known to sit shallower, so the search
  would not go deeper)
- At most **{MAX_PROUD:.1f} mm** proud of the basin
- Dish slope ≤ **{MAX_OVERHANG_DEG:.0f}°** from horizontal so it prints with the
  flange on the bed and **no supports**

The winner's insert depth is **{best['insert_depth']:.1f} mm** into the drain
(dish {best['dish_h']:.1f} mm, architecture `{best['arch']}`, proud {best['proud_h']:.1f} mm).

## Winner

| | |
|---|---|
| Open area | **{best['open_frac']*100:.1f}%** of the grate disc |
| Max passable sphere | **{best['max_inscribed']:.2f} mm** |
| Min opening | {best['min_inscribed']:.2f} mm |
| Min strut | **{best['min_strut']:.2f} mm** |
| Grate thickness | {best['thick']:.2f} mm |
| Predicted deflection | ~{best['defl_mm']:.2f} mm under a 15 N toddler press (plate + shallow-shell estimate, not a lab test) |
| Score | {best['score']:.3f} |

## Versus the old two-level Voronoi catcher (variant C)

| | Old C | New guard |
|---|---|---|
| Purpose | Catch hair | Pass hair, block toys |
| Open area | {old.get('C_json',{}).get('straight_through',0.255)*100:.1f}% straight-through ({old.get('C_json',{}).get('level2_open',0.45)*100:.1f}% at the fine level) | {best['open_frac']*100:.1f}% |
| Max passable sphere | {old.get('C_json',{}).get('level2_max_inscribed',5.61):.2f} mm (fine level) | {best['max_inscribed']:.2f} mm |
| Min strut (fine / grate) | ~1.67 mm | {best['min_strut']:.2f} mm |

## Print (when approved)

- File: `basin_guard_v2-print.stl` — flange top on the bed, no supports.
- A1 mini, PLA Basic, 0.20 mm. PLA in a wet drain is a durability compromise;
  PETG would last longer. Reprint when it goes brittle or slimy.
- **Do not send this to the printer until the user says go.**

{slice_text}

## Files

- `basin_guard_v2-print.stl` / `basin_guard_v2-use.stl`
- `preview-top.png`, `preview-34.png`
- `optimization-chart.png`, `comparison.png`
- `iterations/iter_XX.png`, `iterations/iterations.csv`, `iterations/all_candidates.csv`
- `iterations/contact-sheet.png`, `iterations/evolution.gif`
- `stats.json`, `optimize.py`

Evaluated **{n_eval}** candidates across **{N_GEN+1}** generations (pop {POP}).
""")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    print("== basin guard v2 search ==", flush=True)
    print(f"R_IN={R_IN:.4f} R_LOC={R_LOC:.4f} FLANGE={2*R_FLANGE:.1f} MAX_SPHERE={MAX_SPHERE_MM}", flush=True)

    all_rows = []
    gen_bests = []
    frame_paths = []
    pop = []

    # Generation 0: diverse (and deliberately imperfect) seed population
    print("gen 00: seeding", flush=True)
    seeds = []
    for i in range(POP):
        seeds.append(random_candidate(g=0))
    # a few structured but not optimal starting points (small holes, coarse radial)
    for n, d in ((12, 6.2), (19, 5.6), (4, 7.0), (8, 6.8), (6, 7.5)):
        seeds.append(make_holes_candidate(n, d, 2.2, float(RNG.uniform(0, 1)), 6.0, 0.8, 2.2, 0.0, "top_grate"))
    seeds.append(make_radial_candidate(8, 2, 2.2, 2.2, 5.0, 0.0, 6.0, 0.6, 2.2, 0.0, "top_grate"))

    scored = []
    for i, c in enumerate(seeds):
        m = evaluate(c)
        scored.append(m)
        all_rows.append(metrics_row(0, m, kind="candidate"))
        if (i + 1) % 15 == 0:
            print(f"  seeded {i+1}/{len(seeds)}  best so far {max(x['score'] for x in scored):.3f}", flush=True)

    scored.sort(key=lambda x: x["score"], reverse=True)
    pop = [s["cand"] for s in scored[:POP]]
    best = scored[0]
    gen_bests.append(best)
    fp = ITER / "iter_00.png"
    render_iter_frame(best, fp, 0, N_GEN, tag="best of generation 0 (seed)")
    frame_paths.append(fp)
    print(f"  gen 00 best score={best['score']:.3f} open={best['open_frac']*100:.1f}% "
          f"ball={best['max_inscribed']:.2f} strut={best['min_strut']:.2f} "
          f"depth={best['insert_depth']:.1f} feas={best['feasible']}", flush=True)

    for g in range(1, N_GEN + 1):
        print(f"gen {g:02d}: evolving", flush=True)
        # elites + mutated offspring
        elite_n = 8
        new_cands = [scored[i]["cand"] for i in range(min(elite_n, len(scored)))]
        # one "grow holes" improvement on the elite (push toward the sphere cap)
        if scored[0]["family"] == "holes" and scored[0]["feasible"]:
            c = json.loads(json.dumps({k: v for k, v in scored[0]["cand"].items() if k != "holes"}))
            c["family"] = "holes"
            c["holes"] = [(x, y, min(r * 1.04, MAX_SPHERE_MM / 2)) for x, y, r in scored[0]["cand"]["holes"]]
            c["holes"] = _ok_holes(c["holes"])
            c["thick"] = scored[0]["cand"]["thick"]
            c["insert_depth"] = scored[0]["cand"]["insert_depth"]
            c["dish_h"] = scored[0]["cand"].get("dish_h", 1.2)
            c["proud_h"] = scored[0]["cand"].get("proud_h", 0)
            c["arch"] = scored[0]["cand"].get("arch", "top_grate")
            new_cands.append(c)
        while len(new_cands) < POP:
            parent = scored[int(RNG.integers(0, min(20, len(scored))))]["cand"]
            new_cands.append(mutate(parent, g=g))
        # a few fresh randoms so it cannot fully collapse
        for _ in range(4):
            new_cands.append(random_candidate(g=g))

        scored = []
        for i, c in enumerate(new_cands):
            m = evaluate(c)
            scored.append(m)
            all_rows.append(metrics_row(g, m, kind="candidate"))
        scored.sort(key=lambda x: x["score"], reverse=True)
        pop = [s["cand"] for s in scored[:POP]]
        best = scored[0]
        gen_bests.append(best)
        fp = ITER / f"iter_{g:02d}.png"
        render_iter_frame(best, fp, g, N_GEN, tag=f"best of generation {g}")
        frame_paths.append(fp)
        print(f"  gen {g:02d} best score={best['score']:.3f} open={best['open_frac']*100:.1f}% "
              f"ball={best['max_inscribed']:.2f} strut={best['min_strut']:.2f} "
              f"depth={best['insert_depth']:.1f} feas={best['feasible']} "
              f"({best['family']}/{best['arch']})", flush=True)

    # CSV
    hist_rows = [metrics_row(i, m, kind="generation_best") for i, m in enumerate(gen_bests)]
    def write_csv(path, rows):
        if not rows:
            return
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    write_csv(ITER / "iterations.csv", hist_rows)
    write_csv(ITER / "all_candidates.csv", all_rows)

    write_contact_sheet(frame_paths, ITER / "contact-sheet.png")
    write_gif(frame_paths, ITER / "evolution.gif", duration=850)
    optimization_chart(hist_rows, all_rows, gen_bests, OUT / "optimization-chart.png")

    winner = gen_bests[-1]
    # if a later gen is not the global best (unlikely if elites are kept), use global best
    global_best = max(gen_bests, key=lambda x: x["score"])
    winner = global_best
    print(f"WINNER score={winner['score']:.3f} open={winner['open_frac']*100:.1f}% "
          f"ball={winner['max_inscribed']:.2f} strut={winner['min_strut']:.2f} "
          f"depth={winner['insert_depth']:.1f}", flush=True)

    # 3D
    print("building 3D mesh", flush=True)
    try:
        tm = build_mesh(winner)
        if tm is None or len(tm.faces) < 20:
            print("CQ mesh failed, voxel fallback", flush=True)
            tm = _voxel_mesh(winner)
    except Exception as e:
        print("build_mesh error:", e, "— voxel fallback", flush=True)
        tm = _voxel_mesh(winner)
    print(f"  mesh faces={len(tm.faces)} watertight={getattr(tm,'is_watertight',None)} "
          f"bounds={tm.bounds}", flush=True)
    use_path = OUT / "basin_guard_v2-use.stl"
    print_path = OUT / "basin_guard_v2-print.stl"
    tm.export(use_path)
    to_print_orientation(tm).export(print_path)

    print("renders", flush=True)
    try:
        render_final(tm, OUT / "preview-top.png", OUT / "preview-34.png")
    except Exception as e:
        print("pyvista render failed:", e, flush=True)
        # 2D stand-ins already exist as last iter frame
        shutil.copy(frame_paths[-1], OUT / "preview-top.png")

    print("measuring old catcher", flush=True)
    try:
        old = measure_old_catcher()
    except Exception as e:
        print("old measure failed:", e, flush=True)
        old = dict(
            C_json=dict(level1_open=0.5054, level2_open=0.4484, straight_through=0.2553,
                        level2_max_inscribed=5.614, level2_min_inscribed=3.586),
            B_json=dict(level1_open=0.5395, level2_open=0.4381, straight_through=0.2671,
                        level2_max_inscribed=4.963, level2_min_inscribed=3.553),
        )
    comparison_chart(old, winner, OUT / "comparison.png")

    print("slicing (no print)", flush=True)
    try:
        slice_text, sc = slice_stl(print_path)
        print(slice_text, flush=True)
    except Exception as e:
        slice_text = f"Slice step failed: {e}\nNothing was sent to the printer.\n"
        print(slice_text, flush=True)

    stats = dict(
        winner={k: v for k, v in metrics_row(-1, winner, "winner").items()},
        fit=dict(R_IN=R_IN, R_LOC=R_LOC, LOC_OD_PRINT=LOC_OD_PRINT, SHRINK=SHRINK,
                 R_FLANGE=R_FLANGE, FLANGE_T=FLANGE_T, COLLAR_WALL=COLLAR_WALL, LEADIN=LEADIN),
        rules=dict(MAX_SPHERE_MM=MAX_SPHERE_MM, MIN_STRUT_MM=MIN_STRUT_MM, MIN_RIM_MM=MIN_RIM_MM,
                   MIN_INSERT=MIN_INSERT, MAX_INSERT=MAX_INSERT, MAX_PROUD=MAX_PROUD,
                   MAX_OVERHANG_DEG=MAX_OVERHANG_DEG),
        old=old,
        n_eval=len(all_rows),
        n_gen=N_GEN + 1,
        elapsed_s=round(time.time() - t0, 1),
    )
    # make JSON safe
    def scrub(o):
        if isinstance(o, dict):
            return {str(k): scrub(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [scrub(x) for x in o]
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return o
    (OUT / "stats.json").write_text(json.dumps(scrub(stats), indent=2))
    write_readme(winner, old, slice_text, len(all_rows))
    print(f"done in {time.time()-t0:.1f}s  outputs in {OUT}", flush=True)


if __name__ == "__main__":
    main()
