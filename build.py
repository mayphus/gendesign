"""usage: python build.py <seed> <top_spacing> <bot_spacing> <outdir> [h]"""
import sys, os, json
from functools import reduce
import numpy as np
from scipy import ndimage
from skimage import measure
import trimesh, fast_simplification
import design as D

SEED = int(sys.argv[1]); TSP = float(sys.argv[2]); BSP = float(sys.argv[3]); OUT = sys.argv[4]
H = float(sys.argv[5]) if len(sys.argv) > 5 else 0.1
os.makedirs(OUT, exist_ok=True)

RIB_TOP, RIB_BOT = 2.1, 1.95
RIB_NOISE = 0.12                 # organic variation of rib width (still >= 1.8)
ROUND_TOP, ROUND_BOT = float(os.environ.get('RT', 2.3)), float(os.environ.get('RBT', 1.35))  # minimum corner radius of the pebble cells
K_RIM_TOP, K_RIM_BOT = 1.2, 0.9  # rounded rims of the openings
STRUT_R = 1.15                   # Ø2.3 posts
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
segs = D.strut_tree(D.junctions(top, D.OPEN_R - 0.8), D.junctions(bot, D.OPEN_R - 0.8), rng)
# organic rib-width variation (never thinner: noise only widens ribs)
nrng = np.random.default_rng(SEED + 1000)
nz = np.abs(D.noise(g2, nrng, RIB_NOISE))
tm, ts = D.hole_mask(g2, top, RIB_TOP, nz, ROUND_TOP, 4.6)
bm, bs = D.hole_mask(g2, bot, RIB_BOT, nz, ROUND_BOT, 3.3)
ht = D.signed_field(g2, tm)
hb = D.signed_field(g2, bm)

g = D.Grid(H) if H != 0.1 else g2
if H != 0.1:
    from scipy.interpolate import RegularGridInterpolator as RGI
    ht = RGI((g2.x, g2.x), ht)(np.c_[g.X.ravel(), g.Y.ravel()]).reshape(g.X.shape)
    hb = RGI((g2.x, g2.x), hb)(np.c_[g.X.ravel(), g.Y.ravel()]).reshape(g.X.shape)
xs = g.x; zs = np.arange(-8.9, 0.3 + 1e-9, H); X, Y, Rr = g.X, g.Y, g.R

acc = np.zeros((len(xs), len(xs), len(zs)), np.float32)
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

F = np.empty_like(struts)
for k, z in enumerate(zs):
    T = smax(mx(z, -D.FL_T - z), ht, K_RIM_TOP)
    B = smax(mx(z - D.BOT_SKIN[1], D.BOT_SKIN[0] - z), hb, K_RIM_BOT)
    B = np.maximum(B, Rr - (D.C_ID + 0.4))
    C = mx(Rr - D.C_OD, D.C_ID - Rr, z + 1.0, D.Z_BOT - z)
    U = smin(np.minimum(T, C), B, 0.7)
    U = smin(U, struts[:, :, k], K_BLEND)
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


to, tcol = openings(-1.6, 0.0)
bo, bcol = openings(-8.6, -7.2)
see = np.all(F[:, :, (zs > -8.6) & (zs < 0)] > 0, axis=2) & (Rr < D.C_ID)
tl = [D.tilt(P, Q) for P, Q in segs]
metrics = dict(seed=SEED, top_spacing=TSP, bot_spacing=BSP,
               top_inscribed=summ(to, "inscribed"), top_equiv=summ(to, "equiv"),
               bot_inscribed=summ(bo, "inscribed"), bot_equiv=summ(bo, "equiv"),
               top_rib=rib_min(tcol), bot_rib=rib_min(bcol),
               struts=len(segs), strut_max_tilt=round(max(tl), 1),
               strut_tilts=sorted(round(t, 1) for t in tl),
               open_top_mm2=round(tcol.sum() * H * H), open_bot_mm2=round(bcol.sum() * H * H),
               see_through_mm2=round(see.sum() * H * H))
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
            bodies=len(mp.split(only_watertight=False)), volume_mm3=round(float(mp.volume), 1),
            extents=[round(float(e), 2) for e in mp.extents],
            collar_OD=round(float(2 * rr.max()), 3),
            collar_ID_min=round(float(2 * rr[rr > 15.0].min()), 3))
print(json.dumps(info))
json.dump(info, open(f"{OUT}/mesh.json", "w"), indent=1)
