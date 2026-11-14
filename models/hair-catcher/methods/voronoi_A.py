#!/usr/bin/env python3
"""
Two-level grown Voronoi hair catcher for a De40 (DN40) washbasin waste.

Coordinates in USE orientation: z = 0 is the drain rim the flange sits on,
+z up out of the basin, the collar goes down into the bore (z < 0).
The STL is exported flipped (flange/top face on the bed) - see README.

Pipeline
 1. Load-path field s(x,y) from grow_to.py (SIMP plate-bending topology optimisation).
 2. TOP level  : variable-radius Poisson-disc seeds (spacing D_TOP, tighter where s is
                 high) + density-weighted Lloyd relaxation -> 2-D Voronoi; struts are the
                 exact bisector distance field, width W_TOP(s); junctions filleted.
 3. FINE level : same algorithm at hair scale; every opening is checked with a distance
                 transform and re-seeded until inscribed diameter <= MAX_GAP; slivers
                 below MIN_GAP are closed.
 4. LINK level : a third, intermediate Voronoi tessellation; its vertices (z-jittered) are
                 branch nodes. Top-level vertices branch down to nearby link nodes, link
                 nodes branch down to fine-level vertices. Only branches within
                 MAX_BRANCH_ANGLE of vertical are kept -> self-supporting when printed
                 upside down. Branches are tapered round cones, smooth-min blended
                 (organic fillets) into both levels.
 5. Solid flange + solid press-fit collar (axisymmetric), union, marching cubes, Taubin.
"""
import json, sys
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, map_coordinates, label
from scipy.spatial import cKDTree, Voronoi
from skimage import measure
from skimage.morphology import skeletonize
import trimesh, fast_simplification

OUT = Path(__file__).resolve().parent
VARIANT = sys.argv[1] if len(sys.argv) > 1 else 'A'
# ======================= parameters =======================
SEED = {'A': 11, 'B': 29, 'C': 5}.get(VARIANT, 11)
PX, PZ = 0.08, 0.08            # voxel pitch [mm]
# --- fit ---
SHRINK      = 0.003            # PLA Basic linear shrink allowance (0.3 %)
LOC_OD_PRINT= 35.10            # target as-printed collar OD [mm] (bore ID ~35.2-36.0)
R_LOC       = LOC_OD_PRINT*(1+SHRINK)/2   # CAD radius -> 35.21 mm CAD OD
COLLAR_WALL = 1.6
COLLAR_H    = 7.0              # depth into the bore [mm]
LEADIN      = 0.7              # 45 deg lead-in chamfer at collar tip
R_FLANGE    = 23.0             # 46 mm OD flange (seat assumption, see README)
FLANGE_T    = 1.6              # = depth of the drain recess for a flush top (assumption)
FLANGE_CH   = 0.6              # 45 deg chamfer on the visible top edge
# --- levels (use orientation) ---
TOP_Z0, TOP_Z1   = -0.8, FLANGE_T         # top lattice slab (flush with flange top = basin level)
FINE_Z0, FINE_Z1 = -COLLAR_H, -COLLAR_H + 1.3
LINK_Z, LINK_JIT = -3.4, 0.4
D_TOP  = (5.0, 6.6)            # top-level seed spacing on / off load paths [mm]
W_TOP  = (2.3, 1.7)            # top strut width on / off load paths
D_FINE = (3.25, 3.6)
W_FINE = (1.30, 1.20)
D_LINK = 4.6
MAX_GAP, MIN_GAP = 2.5, 1.1
MAX_BRANCH_ANGLE = 38.0        # deg from vertical (overhang 52 deg from horizontal)
BR_R_TOP, BR_R_LINK, BR_R_FINE = 0.95, 0.80, 0.65   # branch radii [mm]
SMOOTH_K = 0.7                 # smooth-min blend radius [mm]
ROUND_TOP, ROUND_FINE = 0.5, 0.45
FILLET_TOP, FILLET_FINE = 0.75, 0.30   # junction fillet (blur of signed distance) [mm]
WARP_AMP, WARP_LEN = 0.7, 5.0          # smooth domain warp -> curved, grown-looking cell edges [mm]
# ==========================================================
rng = np.random.default_rng(SEED)
meta = json.load(open(OUT/'to_meta.json')); rho = np.load(OUT/'to_density.npy').astype(float)
R_IN = R_LOC - COLLAR_WALL      # inner radius of the collar
L = 2*R_FLANGE + 1.2
n = int(round(L/PX)); L = n*PX
c = (np.arange(n)+0.5)*PX - L/2
X, Y = np.meshgrid(c, c, indexing='xy'); R = np.hypot(X, Y)
gi = (Y + meta['L']/2)/meta['H'] - 0.5; gj = (X + meta['L']/2)/meta['H'] - 0.5
S = np.clip(map_coordinates(gaussian_filter(rho, 1.2), [gi, gj], order=1), 0, 1)
inner = R < R_IN
wx = gaussian_filter(rng.normal(size=(n, n)), WARP_LEN/PX/2.5); wy = gaussian_filter(rng.normal(size=(n, n)), WARP_LEN/PX/2.5)
wx *= WARP_AMP/wx.std(); wy *= WARP_AMP/wy.std()
XW, YW = X + wx, Y + wy

def s_at(p):
    ii = np.clip(((p[..., 1] + L/2)/PX).astype(int), 0, n-1); jj = np.clip(((p[..., 0] + L/2)/PX).astype(int), 0, n-1)
    return S[ii, jj]

def poisson(dpair, rmax):
    cand = rng.uniform(-rmax, rmax, (80000, 2)); cand = cand[np.hypot(*cand.T) < rmax]
    pts = np.empty((0, 2))
    for p in cand:
        d = dpair[1] + (dpair[0]-dpair[1])*s_at(p)
        if len(pts) and np.min(np.hypot(*(pts - p).T)) < d: continue
        pts = np.vstack([pts, p])
    return pts

gp = np.stack([X[inner], Y[inner]], 1)
def lloyd(seeds, dpair, k, relax=0.5):
    w = 1.0/(dpair[1] + (dpair[0]-dpair[1])*s_at(gp))**2
    for _ in range(k):
        idx = cKDTree(seeds).query(gp)[1]
        sw = np.bincount(idx, w, len(seeds)); cx = np.bincount(idx, w*gp[:, 0], len(seeds)); cy = np.bincount(idx, w*gp[:, 1], len(seeds))
        ok = sw > 0; seeds = seeds.copy()
        seeds[ok] = (1-relax)*seeds[ok] + relax*np.stack([cx[ok]/sw[ok], cy[ok]/sw[ok]], 1)
    return seeds

def bisector(seeds):
    d, i = cKDTree(seeds).query(np.stack([XW.ravel(), YW.ravel()], 1), k=2)
    sep = np.linalg.norm(seeds[i[:, 1]] - seeds[i[:, 0]], axis=1)
    return ((d[:, 1]**2 - d[:, 0]**2)/(2*np.maximum(sep, 1e-9))).reshape(n, n)

def sdist(mask):
    return distance_transform_edt(~mask)*PX - distance_transform_edt(mask)*PX

def grow_level(dpair, wpair, max_gap=None, rounds=40, fillet=0.3):
    seeds = lloyd(poisson(dpair, R_IN + 0.8), dpair, 5)
    Wf = wpair[1] + (wpair[0]-wpair[1])*S
    for _ in range(rounds):
        solid = ((bisector(seeds) < Wf/2) & inner) | ~inner
        if max_gap is None: break
        void = ~solid; edt = distance_transform_edt(void)*PX
        lab, nl = label(void); mx = np.zeros(nl+1); np.maximum.at(mx, lab.ravel(), edt.ravel())
        big = np.where(2*mx[1:] > max_gap)[0] + 1
        if not len(big): break
        add = [[X.ravel()[k], Y.ravel()[k]] for k in (np.argmax(np.where(lab == b, edt, 0)) for b in big)]
        seeds = lloyd(np.vstack([seeds, add]), dpair, 1, 0.3)
    void = ~solid; edt = distance_transform_edt(void)*PX
    lab, nl = label(void); mx = np.zeros(nl+1); np.maximum.at(mx, lab.ravel(), edt.ravel())
    if max_gap is not None:
        solid |= np.isin(lab, np.where(2*mx < MIN_GAP)[0]) & void
    sd = gaussian_filter(sdist(solid), fillet/PX)             # fillet the Voronoi junctions
    solid = sd < 0
    void = (~solid) & inner; edt = distance_transform_edt(void)*PX
    lab, nl = label(void); mx = np.zeros(nl+1); np.maximum.at(mx, lab.ravel(), edt.ravel())
    sk = skeletonize(solid & (R < R_IN - 1.0)); ins = distance_transform_edt(solid)*PX
    sw = 2*ins[sk]; sw = sw[sw > 0.5]
    stats = dict(cells=int(len(seeds)), openings=int(nl), open_dia_min=float(2*mx[1:].min()),
                 open_dia_median=float(np.median(2*mx[1:])), open_dia_max=float(2*mx[1:].max()),
                 strut_w_p10=float(np.percentile(sw, 10)), strut_w_median=float(np.median(sw)),
                 open_area_frac=float(void.sum()/inner.sum()))
    return seeds, sd, solid, stats

def vor_vertices(seeds, rlim):
    ang = np.linspace(0, 2*np.pi, 64, endpoint=False)
    ghost = 2.2*R_IN*np.stack([np.cos(ang), np.sin(ang)], 1)
    v = Voronoi(np.vstack([seeds, ghost])).vertices
    return v[np.hypot(*v.T) < rlim]

top_seeds, sd_top, top_solid, st_top = grow_level(D_TOP, W_TOP, fillet=FILLET_TOP)
fine_seeds, sd_fine, fine_solid, st_fine = grow_level(D_FINE, W_FINE, MAX_GAP, fillet=FILLET_FINE)
print('top ', st_top); print('fine', st_fine)

# ---- link level: third Voronoi, vertices become branch nodes ----
link_seeds = lloyd(poisson((D_LINK, D_LINK), R_IN + 0.8), (D_LINK, D_LINK), 3)
v_top  = vor_vertices(top_seeds, R_IN - 0.6)
v_fine = vor_vertices(fine_seeds, R_IN - 0.6)
v_link = vor_vertices(link_seeds, R_IN - 1.2)
z_top = 0.5*(TOP_Z0 + TOP_Z1); z_fine = 0.5*(FINE_Z0 + FINE_Z1)
z_link = LINK_Z + rng.uniform(-LINK_JIT, LINK_JIT, len(v_link))
tanA = np.tan(np.radians(MAX_BRANCH_ANGLE))
segs = []
# top vertices -> up to 2 link nodes (Y-branches)
tl = cKDTree(v_link)
used_link = np.zeros(len(v_link), bool)
for p in v_top:
    d, j = tl.query(p, k=3)
    for dd, jj in zip(d, j):
        if dd <= (z_top - z_link[jj])*tanA:
            segs.append(((p[0], p[1], z_top), (*v_link[jj], z_link[jj]), BR_R_TOP, BR_R_LINK)); used_link[jj] = True
# fine vertices -> nearest used link node (each fine vertex at most one branch; keeps cells open)
tlu = cKDTree(v_link[used_link]); idx_used = np.where(used_link)[0]
fine_conn = 0
for p in v_fine:
    d, j = tlu.query(p)
    jj = idx_used[j]
    if d <= (z_link[jj] - z_fine)*tanA:
        segs.append(((*v_link[jj], z_link[jj]), (p[0], p[1], z_fine), BR_R_LINK, BR_R_FINE)); fine_conn += 1
# link nodes that reached nothing below get removed (avoid dangling stubs)
down = {s[0][:2] for s in segs if s[1][2] == z_fine}
segs = [s for s in segs if not (s[1][2] != z_fine and (s[1][0], s[1][1]) not in down)]
print(f'link: {len(v_top)} top vertices, {used_link.sum()} link nodes, {fine_conn} fine vertices fed, {len(segs)} branches')

# ---- volume ----
zs = np.arange(-COLLAR_H - 0.3, FLANGE_T + 0.3, PZ)
def smin(a, b, k):
    h = np.clip(0.5 + 0.5*(b - a)/k, 0, 1)
    return b*(1-h) + a*h - k*h*(1-h)
def rslab(sd2, z, z0, z1, rr):
    q1 = sd2 + rr; q2 = np.abs(z - 0.5*(z0+z1)) - 0.5*(z1-z0) + rr
    return np.sqrt(np.maximum(q1, 0)**2 + np.maximum(q2, 0)**2) + np.minimum(np.maximum(q1, q2), 0) - rr
sd_top_in = np.where(inner, sd_top, 1.0); sd_fine_in = np.where(inner, sd_fine, 1.0)
vol = np.empty((n, n, len(zs)), np.float32)
for k, z in enumerate(zs):
    lat = np.minimum(rslab(sd_top_in, z, TOP_Z0, TOP_Z1, ROUND_TOP), rslab(sd_fine_in, z, FINE_Z0, FINE_Z1, ROUND_FINE))
    # flange: r in [R_IN, R_FLANGE], z in [0, FLANGE_T], top-outer chamfer
    fl = np.maximum.reduce([R_IN - R, R - R_FLANGE, -z + 0*R, z - FLANGE_T + 0*R,
                            (R - R_FLANGE + FLANGE_CH + z - FLANGE_T)/np.sqrt(2)])
    # collar: r in [R_IN, R_LOC], z in [-COLLAR_H, 0.01], tip lead-in chamfer
    co = np.maximum.reduce([R_IN - R, R - R_LOC, -COLLAR_H - z + 0*R, z - 0.2 + 0*R,
                            (R - R_LOC + LEADIN - (z + COLLAR_H))/np.sqrt(2)])
    vol[:, :, k] = smin(lat, np.minimum(fl, co), 0.35)
# branches: tapered round cones, smooth-min into the field (local boxes)
for (a, b, ra, rb) in segs:
    a = np.array(a); b = np.array(b)
    lo = np.minimum(a, b) - 1.8; hi = np.maximum(a, b) + 1.8
    i0, i1 = [np.clip(((v + L/2)/PX).astype(int), 0, n) for v in (lo[1], hi[1])]
    j0, j1 = [np.clip(((v + L/2)/PX).astype(int), 0, n) for v in (lo[0], hi[0])]
    k0, k1 = [np.clip(((v - zs[0])/PZ).astype(int), 0, len(zs)) for v in (lo[2], hi[2])]
    yy, xx, zz = np.meshgrid(c[i0:i1], c[j0:j1], zs[k0:k1], indexing='ij')
    P = np.stack([xx, yy, zz], -1); ab = b - a
    t = np.clip(((P - a) @ ab)/(ab @ ab), 0, 1)
    d = np.linalg.norm(P - (a + t[..., None]*ab), axis=-1) - (ra + (rb - ra)*t)
    vol[i0:i1, j0:j1, k0:k1] = smin(d, vol[i0:i1, j0:j1, k0:k1], SMOOTH_K)

vol[0] = vol[-1] = 1; vol[:, 0] = vol[:, -1] = 1; vol[:, :, 0] = vol[:, :, -1] = 1
print('field border min', float(vol[0].min()), float(vol[-1].min()), float(vol[:,0].min()), float(vol[:,-1].min()), float(vol[:,:,0].min()), float(vol[:,:,-1].min()), 'nan', int(np.isnan(vol).sum()))
verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(PX, PX, PZ))
_m = trimesh.Trimesh(verts, faces, process=True); print('raw MC watertight', _m.is_watertight, 'boundary edges', len(trimesh.grouping.group_rows(_m.edges_sorted, require_count=1)))
verts = verts[:, [1, 0, 2]]; faces = faces[:, ::-1]
verts[:, 0] += c[0]; verts[:, 1] += c[0]; verts[:, 2] += zs[0]
m = trimesh.Trimesh(verts, faces, process=True)
parts = m.split(only_watertight=False); m = max(parts, key=lambda q: q.area)
frag_vol = sorted([abs(q.volume) for q in parts], reverse=True)[1:6]
print('pre-decimation watertight', m.is_watertight, 'faces', len(m.faces), 'largest dropped fragments mm3', frag_vol)
trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=10)
vv, ff = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32), target_reduction=0.85)
m = trimesh.Trimesh(vv, ff, process=True); trimesh.repair.fix_normals(m)
print('post-decimation watertight', m.is_watertight, 'boundary edges', len(trimesh.grouping.group_rows(m.edges_sorted, require_count=1)))
# flatten the two planar datum faces that smoothing softened
v = m.vertices.copy(); v[v[:, 2] > FLANGE_T - 0.04, 2] = FLANGE_T; m.vertices = v
m.export(OUT/f'catcher-{VARIANT}-use-orientation.stl')
pr = m.copy(); pr.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
pr.apply_translation([0, 0, -pr.bounds[0][2]]); pr.export(OUT/f'catcher-{VARIANT}-print.stl')
stats = dict(variant=VARIANT, top=st_top, fine=st_fine, branches=len(segs), fragments_dropped=len(parts)-1, fragment_vol_max=float(frag_vol[0]) if frag_vol else 0.0,
             watertight=bool(m.is_watertight), volume_mm3=float(abs(m.volume)), bounds_use=m.bounds.tolist(),
             collar_cad_od=2*R_LOC, collar_target_print_od=LOC_OD_PRINT, shrink=SHRINK, collar_id=2*R_IN,
             collar_depth=COLLAR_H, flange_od=2*R_FLANGE, flange_t=FLANGE_T, overall_h=FLANGE_T+COLLAR_H,
             max_branch_angle=MAX_BRANCH_ANGLE)
json.dump(stats, open(OUT/f'catcher-{VARIANT}-stats.json', 'w'), indent=1)
np.savez_compressed(OUT/f'catcher-{VARIANT}-fields.npz', S=S.astype(np.float16), top=top_solid, fine=fine_solid,
                    L=L, PX=PX, segs=np.array([[*s[0], *s[1]] for s in segs]))
print(json.dumps(stats, indent=1))
