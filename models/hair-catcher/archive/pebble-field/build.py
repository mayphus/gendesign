"""usage: python build.py <seed> <top_spacing> <bot_spacing> <outdir> [h] [style]

style D (default): vaulted lower mesh - every lower rib is an arch sprung between
                   struts/wall, so nothing is printed over air.
style C:           the first printed version (lower ribs bridge between 15 struts).
"""
import sys, os, json
from functools import reduce
import numpy as np
from scipy import ndimage
from skimage import measure
import trimesh, fast_simplification
import design as D

SEED = int(sys.argv[1]); TSP = float(sys.argv[2]); BSP = float(sys.argv[3]); OUT = sys.argv[4]
H = float(sys.argv[5]) if len(sys.argv) > 5 else 0.1
STYLE = sys.argv[6] if len(sys.argv) > 6 else "D"
os.makedirs(OUT, exist_ok=True)

RIB_TOP, RIB_BOT = 2.1, float(os.environ.get('RIBB', 1.95))
RIB_NOISE = 0.12                 # organic variation of rib width (still >= 1.8)
ROUND_TOP, ROUND_BOT = float(os.environ.get('RT', 2.3)), float(os.environ.get('RBT', 1.35))  # minimum corner radius of the pebble cells
K_RIM_TOP, K_RIM_BOT = 1.2, 0.9  # rounded rims of the openings
STRUT_R = 1.15                   # Ø2.3 posts (style C)
SUB_AREA = 40.0                  # style D: target area of a lower cell (mm2)
WALL_T = 1.9                     # style D: funnel wall thickness (mm)
FUNNEL_ROUND = 1.2               # style D: corner radius inside the funnels (mm)
WARP = float(os.environ.get('WARP', 0.35))  # style D: pattern warp amplitude (mm)
K_STRUT, K_BLEND = 0.3, 1.1      # node blending / gussets into the skins


def mx(*a): return reduce(np.maximum, a)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k): return -smin(-a, -b, k)


g2 = D.Grid(0.1)                 # the 2D search grid (same RNG stream as search.py)
rng = np.random.default_rng(SEED)
top = D.layer(rng, TSP, 0.5)
bot = D.layer(rng, BSP, 0.35)
tm, ts = D.hole_mask(g2, top, RIB_TOP, 0, ROUND_TOP, 4.6)
bm, bs = D.hole_mask(g2, bot, RIB_BOT, 0, ROUND_BOT, 3.3)
if STYLE == "C":
    segs = D.strut_tree(D.junctions(top, D.OPEN_R - 0.8), D.junctions(bot, D.OPEN_R - 0.8), rng)
else:
    segs = []                    # no free-standing struts: funnel walls carry everything
# organic rib-width variation (never thinner: noise only widens ribs)
nrng = np.random.default_rng(SEED + 1000)
nz = np.abs(D.noise(g2, nrng, RIB_NOISE))
tm, ts = D.hole_mask(g2, top, RIB_TOP, nz, ROUND_TOP, 4.6)
bm, bs = D.hole_mask(g2, bot, RIB_BOT, nz, ROUND_BOT, 3.3)
if STYLE != "C":
    # gentle warp of the whole pattern: ribs, funnel walls and lower ribs curve together
    gw = D.Warped(g2, SEED + 7, WARP)
    tm, ts = D.warped_top_mask(gw, top, RIB_TOP, nz, ROUND_TOP, 4.6)
    subs, parent = D.sub_seeds(gw, top, SUB_AREA)
    b_top, b_all = D.warped_fields(gw, top, subs, parent)
    bm, bs = D.openings_from_b(g2, b_all, RIB_BOT, nz, ROUND_BOT, 3.2)
    # funnels have the top opening's pebble cross-section: keep the lower openings
    # inside it and re-round where the two outlines cross
    inner = b_top > WALL_T / 2 + FUNNEL_ROUND
    funnel2 = ndimage.distance_transform_edt(~inner) * g2.h <= FUNNEL_ROUND
    bm, bs = D.reopen(g2, bm & funnel2, 0.9, 3.2)
    wall_field2 = D.signed_field(g2, funnel2)           # <0 inside the walls
ht = D.signed_field(g2, tm)
hb = D.signed_field(g2, bm)

g = D.Grid(H) if H != 0.1 else g2
if H != 0.1:
    from scipy.interpolate import RegularGridInterpolator as RGI
    ht = RGI((g2.x, g2.x), ht)(np.c_[g.X.ravel(), g.Y.ravel()]).reshape(g.X.shape)
    hb = RGI((g2.x, g2.x), hb)(np.c_[g.X.ravel(), g.Y.ravel()]).reshape(g.X.shape)
    if STYLE != "C":
        b_top = RGI((g2.x, g2.x), np.minimum(b_top, 50))(np.c_[g.X.ravel(), g.Y.ravel()]).reshape(g.X.shape)
        wall_field2 = RGI((g2.x, g2.x), wall_field2)(np.c_[g.X.ravel(), g.Y.ravel()]).reshape(g.X.shape)
xs = g.x; zs = np.arange(-8.9, 0.3 + 1e-9, H); X, Y, Rr = g.X, g.Y, g.R
XW, YW = D.warp_xy(X, Y, SEED + 7, WARP) if (STYLE != "C" and WARP > 0) else (X, Y)  # pattern coords

acc = np.zeros((len(xs), len(xs), len(zs)), np.float32)
acc += np.float32(np.exp(-30 / K_STRUT)) if not segs else 0
for P, Q in segs:
    lo = np.minimum(P, Q) - 2.6; hi = np.maximum(P, Q) + 2.6
    sl = [slice(max(0, int((lo[i] - (xs[0] if i < 2 else zs[0])) / H)),
                int((hi[i] - (xs[0] if i < 2 else zs[0])) / H) + 2) for i in range(3)]
    gx, gy, gz = np.meshgrid(xs[sl[0]], xs[sl[1]], zs[sl[2]], indexing="ij")
    pts = np.stack([gx, gy, gz], -1)
    d = Q - P
    t = np.clip(((pts - P) @ d) / (d @ d), 0, 1)
    dist = np.linalg.norm(pts - (P + t[..., None] * d), axis=-1) - STRUT_R
    acc[sl[0], sl[1], sl[2]] += np.exp(-np.clip(dist, -5, 30) / K_STRUT)
struts = -K_STRUT * np.log(acc + 1e-12); del acc

ZT = D.BOT_SKIN[1]               # installed top face of the lower mesh (print underside)


def funnel_vault():
    """Walls + arched dividers (style D).

    Walls: a band under every top rib, from the top face down to the lower mesh.
    They stand on the top face, which is on the bed, so they need nothing else.
    Dividers: the rest of the lower mesh. Each divider point at geodesic distance
    g (along the mesh) from a wall or the collar is lifted into an arch whose
    underside rises at ARCH_SLOPE toward the walls: height = slope * (Gmax - g)
    with Gmax the farthest point of that divider. So every layer rests on the
    layer printed before it, within 40° of vertical."""
    from skimage.graph import MCP_Geometric
    wall2d = (wall_field2 < 0) & (Rr < D.C_ID + 0.3)
    # mesh within 0.35 mm of a wall rests on the wall (and its fillet), not on an arch
    support = (ndimage.distance_transform_edt(~wall2d) * H <= 0.35) | (Rr >= D.C_ID - 0.05)
    region = (hb < 0) & (Rr < D.C_ID) & ~support
    walk = region | support
    cost = np.where(walk, 1.0, np.inf)
    mcp = MCP_Geometric(cost)
    gdist, _ = mcp.find_costs(np.argwhere(support & ndimage.binary_dilation(region)))
    gdist = np.where(np.isfinite(gdist), gdist * H, 0.0)
    lab, n = ndimage.label(region)
    gmax = ndimage.maximum(gdist, lab, index=np.arange(1, n + 1)) if n else []
    roof = np.zeros(X.shape)
    for i in range(1, n + 1):
        m = lab == i
        roof[m] = D.ARCH_SLOPE * (gmax[i - 1] - gdist[m])
    # extend the roof height outward so the field is smooth at the divider edges
    _, ind = ndimage.distance_transform_edt(~region, return_indices=True)
    roof = roof[ind[0], ind[1]]
    # smooth the pixel steps; lift by the smoothing error so no point drops below its support
    sm = ndimage.gaussian_filter(roof, sigma=1.5)
    roof = sm + max(0.0, float(np.percentile((roof - sm)[region], 99)))
    roof = np.minimum(roof, (D.TOP_SKIN[0] - 0.3) - ZT)   # never reaches into the top openings
    # arches run on into the near-wall band so they meet the wall face itself
    touch = region | (ndimage.distance_transform_edt(~region) * H <= 0.5) & ~wall2d & (hb < 0)
    region_sd = (ndimage.distance_transform_edt(~touch) - ndimage.distance_transform_edt(touch)) * H
    wall_sd = np.maximum(wall_field2, Rr - (D.C_ID + 0.3))
    return wall_sd, region_sd, roof, region, float(max(gmax) * D.ARCH_SLOPE if n else 0)


WAIST = 0.15                     # walls are this much thinner per side at mid-depth
WIN_TILT = np.radians(40)        # teardrop tip: sides 40° from vertical (print-safe)


def make_windows():
    """Arcades: rows of teardrop windows through the funnel walls, pointed toward
    the lower mesh - in print orientation that point is the roof of the hole, so it
    builds without support. Windows fill every free stretch of wall between the
    junction columns and the points where divider arches meet the wall."""
    wins = []
    COL, RMAX, MARGIN = 1.3, 1.1, 1.3
    for A, Bq, wa, wb in D.voronoi_edges(top):
        CAND.append(1)
        if wa and wb:
            continue                                   # lies along the collar
        L = np.linalg.norm(Bq - A)
        d = (Bq - A) / L; nrm = np.array([-d[1], d[0]])
        U_ = (XW - A[0]) * d[0] + (YW - A[1]) * d[1]   # position along the wall
        N_ = (XW - A[0]) * nrm[0] + (YW - A[1]) * nrm[1]
        near = (np.abs(N_) <= 2.3) & (U_ > -1) & (U_ < L + 1)
        contact = DIV_REGION & near & (ROOF > 0.4)
        ts = np.arange(MARGIN, L - MARGIN + 1e-6, 0.1)
        if len(ts) == 0:
            continue
        blocked = np.zeros(len(ts), bool)
        for u in U_[contact]:
            blocked |= np.abs(ts - u) < 1.0
        # free runs of wall
        runs, s = [], None
        for i, bl in enumerate(blocked):
            if not bl and s is None: s = i
            if (bl or i == len(ts) - 1) and s is not None:
                e = i if bl else i + 1
                runs.append((ts[s], ts[e - 1])); s = None
        placed = 0
        for t0, t1 in runs:
            ell = t1 - t0
            n = max(1, int((ell + COL) // (2 * RMAX + COL)))
            r = min(RMAX, (ell - (n - 1) * COL) / (2 * n))
            if r < 0.6:
                continue
            zh = D.TOP_SKIN[0] - 0.8 - r
            ztip = ZT + 1.0
            zl = min(zh, ztip + r / np.sin(WIN_TILT))
            ztip = zl - r / np.sin(WIN_TILT)
            for j in range(n):
                tc = t0 + r + j * (2 * r + COL) + (ell - n * 2 * r - (n - 1) * COL) / 2
                u = U_ - tc
                sel = (np.abs(u) <= r + 0.5) & (np.abs(N_) <= 2.1) & (Rr < D.C_ID - 0.3)
                wins.append((sel, u[sel], N_[sel], r, zl, zh, ztip)); placed += 1
        if not placed:
            SKIPPED.append(1)
    return wins


def windows_sd(z):
    out = np.full(X.shape, 10.0)
    for sel, u, n, r, zl, zh, ztip in WINDOWS:
        zc = np.clip(z, zl, zh)
        caps = np.hypot(u, z - zc) - r
        tip = mx(np.abs(u) * np.cos(WIN_TILT) - (z - ztip) * np.sin(WIN_TILT), z - zl, ztip - z)
        prof = np.minimum(caps, tip)
        out[sel] = np.minimum(out[sel], np.maximum(prof, np.abs(n) - 2.0))
    return out


if STYLE != "C":
    WALL_SD, REG_SD, ROOF, DIV_REGION, ROOF_MAX = funnel_vault()
    CAND, SKIPPED = [], []
    WINDOWS = make_windows()
    print("tallest divider arch: %.2f mm, windows: %d (edges %d, blocked by dividers %d)" % (ROOF_MAX, len(WINDOWS), len(CAND), len(SKIPPED)))

F = np.empty_like(struts)
for k, z in enumerate(zs):
    T = smax(mx(z, -D.FL_T - z), ht, K_RIM_TOP)
    if STYLE == "C":
        B = smax(mx(z - D.BOT_SKIN[1], D.BOT_SKIN[0] - z), hb, K_RIM_BOT)
    else:  # rounded rims only on the exposed bottom face; the bed-facing side stays sharp
        B = mx(z - ZT, smax(D.BOT_SKIN[0] - z, hb, K_RIM_BOT))
    B = np.maximum(B, Rr - (D.C_ID + 0.4))
    C = mx(Rr - D.C_OD, D.C_ID - Rr, z + 1.0, D.Z_BOT - z)
    U = smin(np.minimum(T, C), B, 0.7)
    U = smin(U, struts[:, :, k], K_BLEND)
    if STYLE != "C":
        h = z - ZT
        f = np.clip((-D.FL_T - z) / (-D.FL_T - ZT), 0, 1)
        Wl = mx(WALL_SD + WAIST * np.sin(np.pi * f), z - (-D.FL_T + 0.2), ZT - 0.2 - z)
        if WINDOWS and ZT < z < D.TOP_SKIN[0]:
            Wl = smax(Wl, -windows_sd(z), 0.35)
        Vt = mx(REG_SD, (h - ROOF) / np.hypot(1, D.ARCH_SLOPE), -h)
        U = smin(U, Wl, 0.7)
        U = smin(U, Vt, 0.5)
    flange = mx(Rr - D.FL_R, z, -D.FL_T - z)
    lead = ((Rr - D.C_OD) + (D.Z_BOT + D.LEAD - z)) / np.sqrt(2)
    E = np.minimum(flange, mx(Rr - D.C_OD, z, D.Z_BOT - z, lead))
    F[:, :, k] = np.maximum(U, E)


# ---------------- measurements on the actual 3D field ----------------
def openings(z0, z1):
    ks = (zs >= z0) & (zs <= z1)
    col = np.all(F[:, :, ks] > 0, axis=2) & (Rr < D.C_ID)
    lab, n = ndimage.label(col); out = []
    for i in range(1, n + 1):
        m = lab == i; a = m.sum() * H * H
        if a < 0.5: continue
        dt = ndimage.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] * H
        out.append(dict(inscribed=round(float(2 * dt.max()), 2),
                        equiv=round(float(2 * np.sqrt(a / np.pi)), 2)))
    return out, col


def summ(l, key):
    v = sorted(o[key] for o in l)
    return dict(n=len(v), min=v[0], median=round(float(np.median(v)), 2), max=v[-1])


def rib_min(col):
    """Rib width = shortest gap between each pair of neighbouring openings."""
    lab, n = ndimage.label(col)
    gaps = []
    for i in range(1, n + 1):
        di = ndimage.distance_transform_edt(lab != i) * H
        for j in range(i + 1, n + 1):
            gaps.append(float(di[lab == j].min()))
    gaps = sorted(g for g in gaps if g < 4.0)   # neighbours only
    return dict(min=round(gaps[0], 2), p10=round(float(np.percentile(gaps, 10)), 2),
                median=round(float(np.median(gaps)), 2), n=len(gaps))


def overhangs(max_deg=55.0, layer=0.2):
    """Print orientation (flipped): area each 0.2 mm layer prints outside the
    previous layer by more than layer*tan(max_deg) - i.e. bridges and steep overhangs."""
    tol = layer * np.tan(np.radians(max_deg)) + H
    prev = None; per_layer = []; where = np.zeros(X.shape, bool); spots = []
    for pz in np.arange(layer / 2, 8.6, layer):
        k = int(np.argmin(np.abs(zs + pz)))
        M = F[:, :, k] < 0
        if prev is not None:
            dist = ndimage.distance_transform_edt(~prev) * H
            bad = M & (dist > tol)
            where |= bad
            per_layer.append(round(float(bad.sum() * H * H), 2))
            lab, n = ndimage.label(bad)
            for i in range(1, n + 1):
                w = lab == i
                if w.sum() * H * H > 0.2:
                    spots.append((round(float(pz), 1), round(float(X[w].mean()), 1),
                                  round(float(Y[w].mean()), 1), round(float(w.sum() * H * H), 2)))
        prev = M
    return dict(total_mm2=round(sum(per_layer), 1), worst_layer_mm2=max(per_layer),
                layers_with_overhang=sum(a > 0.5 for a in per_layer), spots=spots), where


ovh, ovh_map = overhangs()
np.save(f"{OUT}/overhang_map.npy", ovh_map)
to, tcol = openings(-1.6, 0.0)
bo, bcol = openings(-8.6, -7.2) if STYLE == "C" else openings(-8.6, -1.6)  # D: through the whole funnel
see = np.all(F[:, :, (zs > -8.6) & (zs < 0)] > 0, axis=2) & (Rr < D.C_ID)
tl = [D.tilt(P, Q) for P, Q in segs] or [0.0]
metrics = dict(seed=SEED, top_spacing=TSP, bot_spacing=BSP,
               top_inscribed=summ(to, "inscribed"), top_equiv=summ(to, "equiv"),
               bot_inscribed=summ(bo, "inscribed"), bot_equiv=summ(bo, "equiv"),
               top_rib=rib_min(tcol), bot_rib=rib_min(bcol),
               struts=len(segs), strut_max_tilt=round(max(tl), 1),
               strut_tilts=sorted(round(t, 1) for t in tl),
               open_top_mm2=round(tcol.sum() * H * H), open_bot_mm2=round(bcol.sum() * H * H),
               see_through_mm2=round(see.sum() * H * H), unsupported=ovh)
print(json.dumps({k: v for k, v in metrics.items() if k != "strut_tilts"}))
json.dump(metrics, open(f"{OUT}/metrics.json", "w"), indent=1)

# ---------------- mesh ----------------
Fp = np.pad(F, 1, constant_values=1.0)
v, f, _, _ = measure.marching_cubes(Fp, 0.0, spacing=(H, H, H))
v += np.array([xs[0], xs[0], zs[0]]) - H
m0 = trimesh.Trimesh(v, f, process=True)
m0.update_faces(m0.nondegenerate_faces()); m0.merge_vertices(); m0.remove_unreferenced_vertices()
v, f = np.asarray(m0.vertices), np.asarray(m0.faces)
target = 400000
if len(f) > target:
    v, f = fast_simplification.simplify(v.astype(np.float32), f.astype(np.int32), 1 - target / len(f))
m = trimesh.Trimesh(v, f, process=True)
m.update_faces(m.nondegenerate_faces()); m.merge_vertices(); m.remove_unreferenced_vertices()
parts = m.split(only_watertight=False)
if len(parts) > 1:                       # drop decimation crumbs (a few faces)
    m = max(parts, key=lambda p: len(p.faces))
if m.volume < 0: m.invert()
m.export(f"{OUT}/installed.stl")
mp = m.copy()
mp.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
mp.apply_translation([0, 0, -mp.bounds[0][2]])
mp.export(f"{OUT}/print.stl")
# fit check on the mesh itself
sec = m.section(plane_origin=[0, 0, -4.5], plane_normal=[0, 0, 1])
pts = sec.vertices[:, :2]; rr = np.hypot(*pts.T)
info = dict(faces=len(mp.faces), watertight=bool(mp.is_watertight),
            bodies=len(mp.split(only_watertight=False)), body_faces=sorted(len(c.faces) for c in mp.split(only_watertight=False))[-8:], volume_mm3=round(float(mp.volume), 1),
            extents=[round(float(e), 2) for e in mp.extents],
            collar_OD=round(float(2 * rr.max()), 3))
print(json.dumps(info))
json.dump(info, open(f"{OUT}/mesh.json", "w"), indent=1)
