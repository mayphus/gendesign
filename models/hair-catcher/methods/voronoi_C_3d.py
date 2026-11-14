#!/usr/bin/env python3
"""
Variant C, stage 2 (same print-first branch/gusset rules as B; plans come from build_C_2d.py,
whose voids are opened per cell into pebble shapes). Seat (z=0) and top (z=1.6) datum faces are
re-flattened after Taubin smoothing.

Variant B, stage 2: branches chosen for printability, solid model, mesh, export.

Use orientation: z = 0 = waste seat, +z up; collar goes down into the bore.
Print orientation (exported *-print.stl): flipped, flush top + flange on the bed, Level 2 printed last.

Branch rule (print-first):
 * a branch runs from a Level-1 strut straight down to a Level-2 strut, axis <= MAX_AXIS deg from
   vertical, Ø >= 2.3 mm, tapered + smooth-blended into Level 1 (that end is on the bed side when printing);
 * where it meets Level 2 it flares into a 30-deg cone gusset (self-supporting, no round overhang);
 * landings are placed greedily on Level 2 until every point of every Level-2 strut is within
   HALF_SPAN of a support (gusset or collar wall), measured along the strut (geodesic) ->
   the longest unsupported bridge is <= 2*HALF_SPAN, all on >= 2 mm thick, >= 2 mm wide beams.
"""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt, label
from scipy.spatial import cKDTree
from skimage import measure
from skimage.graph import MCP_Geometric
from skimage.morphology import skeletonize
import trimesh, fast_simplification

OUT = Path(__file__).resolve().parent
f = np.load(OUT/'C'/'plans.npz', allow_pickle=True)
PX = float(f['PX']); L = float(f['L']); R_IN = float(f['R_IN']); R_LOC = float(f['R_LOC'])
n = int(round(L/PX))
PZ = 0.08
COLLAR_H, LEADIN, R_FLANGE, FLANGE_T, FLANGE_CH = 7.0, 0.7, 23.0, 1.6, 0.6
TOP_Z0, TOP_Z1 = -0.8, FLANGE_T
FINE_Z0, FINE_Z1 = -COLLAR_H, -COLLAR_H + 2.0
ROUND_TOP, ROUND_FINE = 0.6, 0.35
MAX_AXIS = 20.0            # preferred branch axis from vertical [deg]
MAX_AXIS_FALLBACK = 25.0   # only where no landing within 20 deg can shorten a bridge
BR_R_TOP, BR_R_FINE = 1.20, 1.10     # branch radii [mm] (Ø2.4 -> Ø2.2)
GUSSET_H, GUSSET_ANG = 1.3, 30.0     # cone flare under Level 2 (print orientation), deg from vertical
HALF_SPAN = 3.6
EMBED = 0.4
c = (np.arange(n)+0.5)*PX - L/2
X, Y = np.meshgrid(c, c, indexing='xy'); R = np.hypot(X, Y); inner = R < R_IN

# ---------------- branch landings ----------------
za = TOP_Z0 + EMBED; zb = FINE_Z1 - EMBED; dz = za - zb
max_off = np.tan(np.radians(MAX_AXIS_FALLBACK))*dz; pref_off = np.tan(np.radians(MAX_AXIS))*dz
rg = BR_R_FINE + GUSSET_H*np.tan(np.radians(GUSSET_ANG))

def choose(top_solid, fine_solid, ds=1, verbose=False):
    """greedy landing placement; ds = subsampling for speed during the plan search"""
    T = top_solid[::ds, ::ds]; F = fine_solid[::ds, ::ds]; Xs = X[::ds, ::ds]; Ys = Y[::ds, ::ds]; Rs = R[::ds, ::ds]; px = PX*ds
    edt_top = distance_transform_edt(T)*px
    ok_top = T & (Rs < R_IN - 1.2) & (edt_top >= 0.85)
    top_pts = np.stack([Xs[ok_top], Ys[ok_top]], 1); tk = cKDTree(top_pts)
    edt_f = distance_transform_edt(F)*px
    sk = skeletonize(F & (Rs < R_IN - 1.6)) & (edt_f >= 0.9)
    cand = np.stack([Xs[sk], Ys[sk]], 1)
    coff, _ = tk.query(cand); good = coff <= max_off; cand, coff = cand[good], coff[good]
    cost = np.where(F, 1.0, np.inf); landings = []
    def geodesic():
        starts = F & (Rs >= R_IN - 0.05)
        for p in landings: starts |= F & (np.hypot(Xs - p[0], Ys - p[1]) <= rg)
        d, _ = MCP_Geometric(cost).find_costs(list(zip(*np.nonzero(starts))))
        return np.where(F, d*px, 0)
    for it in range(60):
        G = geodesic(); gmax = G.max()
        if gmax <= HALF_SPAN: break
        ci = np.clip(((cand + L/2)/px - 0.5).round().astype(int), 0, F.shape[0]-1)
        gc = G[ci[:, 1], ci[:, 0]]
        if gc.max() < 2.0: break
        pref = coff <= pref_off
        if (gc[pref] >= 2.0).any(): k = np.where(pref)[0][np.argmax(gc[pref] - 0.8*coff[pref])]
        else: k = np.argmax(gc - 0.8*coff)
        landings.append(cand[k])
    G = geodesic()
    segs = []
    for p in landings:
        _, j = tk.query(p); t = top_pts[j]; segs.append(((t[0], t[1], za), (p[0], p[1], zb)))
    return segs, float(G.max()), G

P = np.load(OUT/'C'/'plans.npz', allow_pickle=True)
import os
res = []
FORCE = os.environ.get('PLAN')
for i in ([] if FORCE else range(len(P['top']))):
    for j in range(len(P['fine'])):
        segs, hs, _ = choose(P['top'][i], P['fine'][j], ds=2)
        ang = max(np.degrees(np.arctan2(np.hypot(a[0]-b[0], a[1]-b[1]), a[2]-b[2])) for a, b in segs)
        res.append((hs > HALF_SPAN + 0.1, round(hs, 1), len(segs), ang, i, j)); print(f'  plan L1#{i} L2#{j}: half-span {hs:.2f}, {len(segs)} branches, max axis {ang:.1f}', flush=True)
if FORCE: bi, bj = map(int, FORCE.split(','))
else:
    res.sort(key=lambda r: (r[0], r[3] > MAX_AXIS + 0.5, r[2], r[1])); _, _, _, _, bi, bj = res[0]
    json.dump([list(map(float, r)) for r in res], open(OUT/'C'/'plan_search.json', 'w'))
top_solid = P['top'][bi]; fine_solid = P['fine'][bj]
segs, half_span, Gmap = choose(top_solid, fine_solid, ds=1)
angles = [np.degrees(np.arctan2(np.hypot(a[0]-b[0], a[1]-b[1]), a[2]-b[2])) for a, b in segs]
taper = np.degrees(np.arctan((BR_R_TOP - BR_R_FINE)/dz))
landings = [s[1][:2] for s in segs]
print(f'CHOSEN L1#{bi} L2#{bj}: branches {len(segs)}, axis angle max {max(angles):.1f} deg, taper {taper:.1f}, half-span {half_span:.2f}')
np.savez_compressed(OUT/'C'/'chosen.npz', top=top_solid, fine=fine_solid, G=Gmap.astype(np.float32), L=L, PX=PX, R_IN=R_IN)

# ---------------- solid field ----------------
def sdf2(mask):
    return distance_transform_edt(~mask)*PX - distance_transform_edt(mask)*PX
# lattice runs 0.8 mm into the collar wall with a continuous field (no jump at the bore radius)
sd_top = np.maximum(sdf2(top_solid), R - (R_IN + 0.8)).astype(np.float32)
sd_fine = np.maximum(sdf2(fine_solid), R - (R_IN + 0.8)).astype(np.float32)
zs = np.arange(-COLLAR_H - 0.3, FLANGE_T + 0.3, PZ)
def smin(a, b, k):
    k = np.maximum(k, 1e-6); h = np.clip(0.5 + 0.5*(b - a)/k, 0, 1)
    return b*(1-h) + a*h - k*h*(1-h)
def rslab(sd2, z, z0, z1, rr):
    q1 = sd2 + rr; q2 = np.abs(z - 0.5*(z0+z1)) - 0.5*(z1-z0) + rr
    return np.sqrt(np.maximum(q1, 0)**2 + np.maximum(q2, 0)**2) + np.minimum(np.maximum(q1, q2), 0) - rr
vol = np.empty((n, n, len(zs)), np.float32)
for k, z in enumerate(zs):
    lat = np.minimum(rslab(sd_top, z, TOP_Z0, TOP_Z1, ROUND_TOP), rslab(sd_fine, z, FINE_Z0, FINE_Z1, ROUND_FINE))
    fl = np.maximum.reduce([R_IN - R, R - R_FLANGE, -z + 0*R, z - FLANGE_T + 0*R,
                            (R - R_FLANGE + FLANGE_CH + z - FLANGE_T)/np.sqrt(2)])
    co = np.maximum.reduce([R_IN - R, R - R_LOC, -COLLAR_H - z + 0*R, z - 0.2 + 0*R,
                            (R - R_LOC + LEADIN - (z + COLLAR_H))/np.sqrt(2)])
    vol[:, :, k] = smin(lat, np.minimum(fl, co), 0.3)
tg = np.tan(np.radians(GUSSET_ANG)); cg = np.cos(np.radians(GUSSET_ANG))
for (a, b) in segs:
    a = np.array(a); b = np.array(b)
    lo = np.minimum(a, b) - 3.0; hi = np.maximum(a, b) + 3.0
    i0, i1 = [int(np.clip((v + L/2)/PX, 0, n)) for v in (lo[1], hi[1])]
    j0, j1 = [int(np.clip((v + L/2)/PX, 0, n)) for v in (lo[0], hi[0])]
    k0, k1 = [int(np.clip((v - zs[0])/PZ, 0, len(zs))) for v in (lo[2], hi[2])]
    yy, xx, zz = np.meshgrid(c[i0:i1], c[j0:j1], zs[k0:k1], indexing='ij')
    P = np.stack([xx, yy, zz], -1); ab = b - a
    t = np.clip(((P - a) @ ab)/(ab @ ab), 0, 1)
    d = np.linalg.norm(P - (a + t[..., None]*ab), axis=-1) - (BR_R_TOP + (BR_R_FINE - BR_R_TOP)*t)
    # 30-deg cone gusset where the branch lands on Level 2 (top face at FINE_Z1)
    rho = np.hypot(xx - b[0], yy - b[1])
    rcone = BR_R_FINE + np.clip(FINE_Z1 + GUSSET_H - zz, 0, None)*tg
    dc = np.maximum((rho - rcone)*cg, zz - (FINE_Z1 + GUSSET_H))
    dc = np.maximum(dc, FINE_Z1 - 0.3 - zz)
    dc = np.maximum(dc, sd_fine[i0:i1, j0:j1, None] - 0.02)   # flare stays over the strut, never into an opening
    d = np.minimum(d, dc)
    # blend radius: generous at Level 1 (bed side in print), small at Level 2 (no round overhang)
    kb = np.where(zz > TOP_Z0 - 1.5, 0.45, 0.08)
    sub = vol[i0:i1, j0:j1, k0:k1]
    vol[i0:i1, j0:j1, k0:k1] = smin(d, sub, kb)
vol[0] = vol[-1] = 1; vol[:, 0] = vol[:, -1] = 1; vol[:, :, 0] = vol[:, :, -1] = 1
verts, faces, _, _ = measure.marching_cubes(vol, 1e-3, spacing=(PX, PX, PZ), allow_degenerate=False); del vol
verts = verts[:, [1, 0, 2]]; faces = faces[:, ::-1]
verts[:, 0] += c[0]; verts[:, 1] += c[0]; verts[:, 2] += zs[0]
m = trimesh.Trimesh(verts, faces, process=True)
parts = m.split(only_watertight=False); m = max(parts, key=lambda q: q.area)
print('fragments dropped', len(parts)-1, 'max frag vol', max([abs(q.volume) for q in parts if q is not m] or [0]), 'pre watertight', m.is_watertight, len(m.faces))
trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=10)
vv, ff = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32), target_reduction=0.85)
m = trimesh.Trimesh(vv, ff, process=True); trimesh.repair.fix_normals(m)
v = m.vertices.copy(); v[v[:, 2] > FLANGE_T - 0.04, 2] = FLANGE_T
rv = np.hypot(v[:, 0], v[:, 1]); v[(np.abs(v[:, 2]) < 0.04) & (rv > R_LOC + 0.05), 2] = 0.0; m.vertices = v
print('watertight', m.is_watertight, 'winding', m.is_winding_consistent, 'volume', m.volume)
m.export(OUT/'catcher-C-use-orientation.stl')
pr = m.copy(); pr.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
pr.apply_translation([0, 0, -pr.bounds[0][2]]); pr.export(OUT/'catcher-C-print.stl')
json.dump(dict(segs=[[*a, *b] for a, b in segs], angles=angles, taper=taper, half_span=half_span, landings=np.array(landings).tolist(), plan=[int(bi), int(bj)],
               rg=rg, params=dict(MAX_AXIS=MAX_AXIS, BR_R_TOP=BR_R_TOP, BR_R_FINE=BR_R_FINE, GUSSET_H=GUSSET_H, GUSSET_ANG=GUSSET_ANG,
               TOP_Z=[TOP_Z0, TOP_Z1], FINE_Z=[FINE_Z0, FINE_Z1], ROUND_TOP=ROUND_TOP, ROUND_FINE=ROUND_FINE, HALF_SPAN=HALF_SPAN, BLEND_TOP=0.45)),
          open(OUT/'C'/'build3d.json', 'w'), indent=1)
