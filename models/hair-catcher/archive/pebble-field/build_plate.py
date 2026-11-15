"""Version E: a single smooth Voronoi plate (2D), flush with the basin.

usage: python build2d.py <seed> <spacing> <outdir> [h] [--quick]

Every opening is an exact rounded polygon (Voronoi cell, inset by half a rib,
then opened with a per-cell radius so it becomes a pebble). The 3D field is the
exact distance to those smooth outlines, so the mesh has no pixel staircase.
Openings go straight through a plate that prints flat on the bed: no bridges,
no overhangs. Fit (flange, collar, lead-in) is identical to the other versions.
"""
import sys, os, json
from functools import reduce
import numpy as np
import shapely
from shapely.geometry import Point, Polygon, MultiPolygon
from scipy.spatial import Voronoi, cKDTree
from scipy import ndimage
from skimage import measure
import trimesh, fast_simplification
import design as D

SEED = int(sys.argv[1]); SP = float(sys.argv[2]); OUT = sys.argv[3]
H = float(sys.argv[4]) if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else 0.07
QUICK = "--quick" in sys.argv
os.makedirs(OUT, exist_ok=True)

RIB = 2.0                 # rib width between openings (mm)
EDGE_RIB = 1.2            # material between the outer openings and the bore wall (mm)
PLATE_T = 2.2             # plate thickness inside the bore (flange stays 1.6)
ROUND_FRAC = 0.8          # pebble-ness: corner radius as a fraction of the cell's inradius
GRADE = float(os.environ.get("GRADE", 0.15))             # density grading: cells shrink toward the rim by ~this fraction
K_TOP, K_BOT = 0.6, 0.9   # rounded rims of the openings (top face is on the bed)
MIN_INSCRIBED = 3.5       # openings smaller than this are left solid
RB = D.C_ID               # bore radius


def mx(*a): return reduce(np.maximum, a)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k): return -smin(-a, -b, k)


# ---------------------------------------------------------------- seeds
def density(p):
    r = np.hypot(p[:, 0], p[:, 1]) / RB
    return (1 + GRADE * r ** 2) ** 2          # more seeds (smaller cells) toward the rim


def seeds(rng):
    """Graded Poisson-disc + weighted Lloyd, mirrored across the bore wall."""
    pts = []
    for _ in range(6000):
        r = (RB - 1.0) * np.sqrt(rng.random()); t = rng.random() * 2 * np.pi
        p = np.array([r * np.cos(t), r * np.sin(t)])
        sp = SP / np.sqrt(density(p[None])[0])
        if all(np.hypot(*(p - q)) >= sp for q in pts):
            pts.append(p)
    pts = np.array(pts)
    S = 80000
    sr = RB * np.sqrt(rng.random(S)); st = rng.random(S) * 2 * np.pi
    samp = np.c_[sr * np.cos(st), sr * np.sin(st)]
    w = density(samp)
    for _ in range(12):
        G = np.vstack([D.mirror(pts), D.ghosts(RB + 14, 24)])
        _, idx = cKDTree(np.vstack([pts, G])).query(samp)
        pts = np.array([(samp[idx == i] * w[idx == i, None]).sum(0) / w[idx == i].sum()
                        if (idx == i).any() else pts[i] for i in range(len(pts))])
    return pts + rng.normal(0, 0.25, pts.shape)


def openings(pts):
    """Exact pebble outlines (shapely), one per cell."""
    allp = np.vstack([pts, D.mirror(pts), D.ghosts(RB + 14, 24)])
    vor = Voronoi(allp)
    bore = Point(0, 0).buffer(RB - EDGE_RIB + RIB / 2, quad_segs=128)
    holes = []
    for i in range(len(pts)):
        reg = vor.regions[vor.point_region[i]]
        if -1 in reg or not reg:
            continue
        cell = Polygon(vor.vertices[reg]).intersection(bore)
        inset = cell.buffer(-RIB / 2, join_style="mitre")
        if inset.is_empty:
            continue
        ir = shapely.maximum_inscribed_circle(inset).length    # radius of largest circle
        R = ROUND_FRAC * ir
        peb = inset.buffer(-R, quad_segs=32).buffer(R, quad_segs=64)
        if peb.is_empty:
            continue
        if peb.geom_type == "MultiPolygon":
            peb = max(peb.geoms, key=lambda g: g.area)
        ins = 2 * shapely.maximum_inscribed_circle(peb).length
        if ins >= MIN_INSCRIBED:
            holes.append(peb)
    return holes


def stats(holes):
    ins = sorted(round(2 * shapely.maximum_inscribed_circle(h).length, 2) for h in holes)
    eq = sorted(round(2 * np.sqrt(h.area / np.pi), 2) for h in holes)
    gaps = []
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            d = holes[i].distance(holes[j])
            if d < 3.5:
                gaps.append(d)
    edge = min(RB - max(np.hypot(*np.array(h.exterior.coords).T)) for h in holes)
    return dict(n=len(holes), inscribed=dict(min=ins[0], median=float(np.median(ins)), max=ins[-1]),
                equiv=dict(min=eq[0], median=float(np.median(eq)), max=eq[-1]),
                rib_min=round(min(gaps), 2), rib_median=round(float(np.median(gaps)), 2),
                edge_min=round(float(edge), 2), open_mm2=round(sum(h.area for h in holes)))


rng = np.random.default_rng(SEED)
pts = seeds(rng)
holes = openings(pts)
st = stats(holes)
print(json.dumps(dict(seed=SEED, spacing=SP, **st)))
if QUICK:
    sys.exit()

# ---------------------------------------------------------------- exact 2D field
xs = np.arange(-23.45, 23.45 + 1e-9, H)
X, Y = np.meshgrid(xs, xs, indexing="ij")
Rr = np.hypot(X, Y)
hfield = np.full(X.shape, -5.0)                 # >0 inside an opening (mm), <0 in material
mp = MultiPolygon(holes)
near = Rr < RB + 0.5
P = shapely.points(X[near], Y[near])
dist = shapely.distance(P, mp.boundary)
inside = shapely.contains_xy(mp, X[near], Y[near])
hfield[near] = np.where(inside, dist, -dist)

zs = np.arange(-8.9, 0.3 + 1e-9, H)
F = np.empty((len(xs), len(xs), len(zs)), np.float32)
for k, z in enumerate(zs):
    plate = mx(smax(z, hfield, K_TOP), smax(-PLATE_T - z, hfield, K_BOT), Rr - (RB + 0.3))
    flange = mx(z, -D.FL_T - z, Rr - D.FL_R, (RB + 0.1) - Rr)   # ring: the plate fills the bore
    collar = mx(Rr - D.C_OD, RB - Rr, z + 1.0, D.Z_BOT - z)
    U = smin(np.minimum(flange, collar), plate, 0.8)      # soft fillet plate <-> collar
    lead = ((Rr - D.C_OD) + (D.Z_BOT + D.LEAD - z)) / np.sqrt(2)
    E = np.minimum(mx(Rr - D.FL_R, z, -D.FL_T - z), mx(Rr - D.C_OD, z, D.Z_BOT - z, lead))
    F[:, :, k] = np.maximum(U, E)


# overhang check (print orientation: flipped, top face on the bed)
def overhangs(max_deg=55.0, layer=0.2):
    tol = layer * np.tan(np.radians(max_deg)) + H
    prev = None; tot = 0.0; worst = 0.0
    for pz in np.arange(layer / 2, 8.6, layer):
        M = F[:, :, int(np.argmin(np.abs(zs + pz)))] < 0
        if prev is not None:
            bad = M & (ndimage.distance_transform_edt(~prev) * H > tol)
            a = float(bad.sum() * H * H); tot += a; worst = max(worst, a)
        prev = M
    return dict(total_mm2=round(tot, 1), worst_layer_mm2=round(worst, 2))


ovh = overhangs()
metrics = dict(seed=SEED, spacing=SP, **st, unsupported=ovh)
print(json.dumps(dict(unsupported=ovh)))
json.dump(metrics, open(f"{OUT}/metrics.json", "w"), indent=1)

Fp = np.pad(F, 1, constant_values=1.0); del F
v, f, _, _ = measure.marching_cubes(Fp, 0.0, spacing=(H, H, H)); del Fp
v += np.array([xs[0], xs[0], zs[0]]) - H
m = trimesh.Trimesh(v, f, process=True)
m.update_faces(m.nondegenerate_faces()); m.merge_vertices(); m.remove_unreferenced_vertices()
target = 600000
if len(m.faces) > target:
    v2, f2 = fast_simplification.simplify(np.asarray(m.vertices, np.float32),
                                          np.asarray(m.faces, np.int32), 1 - target / len(m.faces))
    m = trimesh.Trimesh(v2, f2, process=True)
    m.update_faces(m.nondegenerate_faces()); m.merge_vertices(); m.remove_unreferenced_vertices()
parts = m.split(only_watertight=False)
if len(parts) > 1:
    m = max(parts, key=lambda p: len(p.faces))
if m.volume < 0: m.invert()
m.export(f"{OUT}/installed.stl")
mp3 = m.copy()
mp3.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
mp3.apply_translation([0, 0, -mp3.bounds[0][2]])
mp3.export(f"{OUT}/print.stl")
sec = m.section(plane_origin=[0, 0, -4.5], plane_normal=[0, 0, 1])
rr = np.hypot(*sec.vertices[:, :2].T)
info = dict(faces=len(mp3.faces), watertight=bool(mp3.is_watertight),
            bodies=len(mp3.split(only_watertight=False)), volume_mm3=round(float(mp3.volume), 1),
            extents=[round(float(e), 2) for e in mp3.extents],
            collar_OD=round(float(2 * rr.max()), 3), collar_ID=round(float(2 * rr.min()), 3))
print(json.dumps(info))
json.dump(info, open(f"{OUT}/mesh.json", "w"), indent=1)
