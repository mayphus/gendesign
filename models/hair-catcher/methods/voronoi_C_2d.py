#!/usr/bin/env python3
"""
Variant C, stage 1 (plan view): B's drainage/print floors, A's grown, pebble-like look.
C change vs B: each Voronoi void is morphologically OPENED with a per-cell radius
ROUND_K * (its inscribed radius)  ->  corners become true arcs (pebbles), the inscribed
circle is preserved, and material is only ever ADDED (opening of the void = closing of the solid).
A short-wavelength domain warp bends the remaining straight sides.

(original B docstring follows)
Variant B, stage 1 (plan view): drain-first, print-first two-level Voronoi.

Changes vs A (after the first print: water hung in the small cells, Level 2 webbed/strung):
 * Level 1: ~12-18 cells, every opening inscribed >= 4.5 mm (target 5-8 mm).
 * Level 2: ~18-30 cells, every opening inscribed >= 3.5 mm (floor 3.2), target 3.5-5.5 mm.
 * Struts >= 2.0 mm everywhere (fillets are added by union, never by eroding a strut).
 * Seeds are edited until the floors are met: an opening under the floor -> its seed is
   removed (cell merges with a neighbour); an opening over the ceiling -> a seed is added.
 * The TO load-path field from grow_to.py still grades the strut width (thicker on load paths).
"""
import json, sys
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, map_coordinates, label
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

OUT = Path(__file__).resolve().parent
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 7
PX = 0.08
SHRINK = 0.003; LOC_OD_PRINT = 35.10; R_LOC = LOC_OD_PRINT*(1+SHRINK)/2
COLLAR_WALL = 1.6; R_IN = R_LOC - COLLAR_WALL; R_FLANGE = 23.0
# level 1 (top, flush)
D_TOP = (6.4, 7.2); W_TOP = (2.2, 2.0); TOP_FLOOR, TOP_CEIL, TOP_N = 4.7, 8.3, (11, 18)
# level 2 (dropped)
D_FINE = (4.7, 5.2); W_FINE = (2.1, 2.0); FINE_FLOOR, FINE_CEIL, FINE_N = 3.5, 5.6, (17, 30)
WARP_AMP, WARP_LEN = 0.8, 6.0
FILLET = 0.6
WMIN = 2.05         # 2D strut floor band (mesh smoothing + section raster lose ~0.1-0.15 mm)
ROUND_K = 0.75      # corner arc radius as fraction of each opening's inscribed radius

rng = np.random.default_rng(SEED)
meta = json.load(open(OUT/'to_meta.json')); rho = np.load(OUT/'to_density.npy').astype(float)
L = 2*R_FLANGE + 1.2; n = int(round(L/PX)); L = n*PX
c = (np.arange(n)+0.5)*PX - L/2
X, Y = np.meshgrid(c, c, indexing='xy'); R = np.hypot(X, Y)
gi = (Y + meta['L']/2)/meta['H'] - 0.5; gj = (X + meta['L']/2)/meta['H'] - 0.5
S = np.clip(map_coordinates(gaussian_filter(rho, 2.0), [gi, gj], order=1), 0, 1)
inner = R < R_IN

def warp(seed):
    r = np.random.default_rng(seed)
    wx = gaussian_filter(r.normal(size=(n, n)), WARP_LEN/PX/2.5); wy = gaussian_filter(r.normal(size=(n, n)), WARP_LEN/PX/2.5)
    return X + wx*WARP_AMP/wx.std(), Y + wy*WARP_AMP/wy.std()

def s_at(p):
    ii = np.clip(((p[..., 1] + L/2)/PX).astype(int), 0, n-1); jj = np.clip(((p[..., 0] + L/2)/PX).astype(int), 0, n-1)
    return S[ii, jj]

def poisson(dpair, rmax, rng):
    cand = rng.uniform(-rmax, rmax, (20000, 2)); cand = cand[np.hypot(*cand.T) < rmax]
    pts = np.empty((0, 2))
    for p in cand:
        d = dpair[1] + (dpair[0]-dpair[1])*s_at(p)
        if len(pts) and np.min(np.hypot(*(pts - p).T)) < d: continue
        pts = np.vstack([pts, p])
    return pts

gp = np.stack([X[inner], Y[inner]], 1)[::7]
def lloyd(seeds, dpair, k, relax=0.6):
    w = 1.0/(dpair[1] + (dpair[0]-dpair[1])*s_at(gp))**2
    for _ in range(k):
        idx = cKDTree(seeds).query(gp)[1]
        sw = np.bincount(idx, w, len(seeds)); cx = np.bincount(idx, w*gp[:, 0], len(seeds)); cy = np.bincount(idx, w*gp[:, 1], len(seeds))
        ok = sw > 0; seeds = seeds.copy()
        seeds[ok] = (1-relax)*seeds[ok] + relax*np.stack([cx[ok]/sw[ok], cy[ok]/sw[ok]], 1)
        seeds = seeds[ok]
    return seeds

def lattice(seeds, wpair, XW, YW, wmin):
    d, i = cKDTree(seeds).query(np.stack([XW.ravel(), YW.ravel()], 1), k=2)
    sep = np.linalg.norm(seeds[i[:, 1]] - seeds[i[:, 0]], axis=1)
    bis = ((d[:, 1]**2 - d[:, 0]**2)/(2*np.maximum(sep, 1e-9))).reshape(n, n)
    Wf = wpair[1] + (wpair[0]-wpair[1])*S
    solid = (bis < Wf/2) | ~inner
    # junction fillets by UNION only (blur of the signed distance can only add material here)
    sd = distance_transform_edt(~solid)*PX - distance_transform_edt(solid)*PX
    solid = solid | (gaussian_filter(sd, FILLET/PX) < 0)
    # hard minimum strut width: a wmin-wide band around the medial axis is always solid
    sk = skeletonize(solid & inner)
    solid = solid | (distance_transform_edt(~sk)*PX <= wmin/2)
    # pinholes/slivers left between fillets are closed (they could never drain anyway)
    lab, dia, _ = openings(solid)
    solid = solid | np.isin(lab, np.where(dia < 1.5)[0] + 1)
    # C: round every void LAST (adds material only, so the strut floor above still holds)
    solid = round_voids(solid)
    lab, dia, _ = openings(solid)
    solid = solid | np.isin(lab, np.where(dia < 1.5)[0] + 1)
    return solid

def round_voids(solid):
    """per-cell morphological opening of each void (adds material only) -> pebble-shaped cells"""
    lab, dia, _ = openings(solid)
    out = solid.copy()
    from scipy.ndimage import find_objects
    for k, sl in enumerate(find_objects(lab)):
        if sl is None: continue
        rr = ROUND_K*dia[k]/2
        pad = int(rr/PX) + 3
        s0 = slice(max(sl[0].start-pad, 0), min(sl[0].stop+pad, n)); s1 = slice(max(sl[1].start-pad, 0), min(sl[1].stop+pad, n))
        v = lab[s0, s1] == k+1
        core = distance_transform_edt(v)*PX > rr                 # erode
        if not core.any(): continue
        back = distance_transform_edt(~core)*PX <= rr + 0.5*PX    # dilate
        out[s0, s1] |= v & ~back                                  # corners the disc can't reach -> material
    return out

def openings(solid):
    void = (~solid) & inner
    edt = distance_transform_edt(void)*PX
    lab, nl = label(void)
    mx = np.zeros(nl+1); np.maximum.at(mx, lab.ravel(), edt.ravel())
    arg = np.zeros(nl+1, int); flat = edt.ravel(); lr = lab.ravel()
    order = np.argsort(flat); arg[lr[order]] = order        # index of the max-EDT pixel per opening
    return lab, 2*mx[1:], arg[1:]

def grow(dpair, wpair, floor, ceil, nrange, tries=40, iters=40, want=8):
    best = None; oks = []
    for t in range(tries):
        r = np.random.default_rng(SEED*1000 + t*17 + int(10*dpair[0]))
        XW, YW = warp(SEED*1000 + t*17 + 1)
        seeds = lloyd(poisson(dpair, R_IN - 0.25*dpair[1], r), dpair, 8)
        for it in range(iters):
            solid = lattice(seeds, wpair, XW, YW, WMIN)
            lab, dia, arg = openings(solid)
            lo = np.where(dia < floor)[0]; hi = np.where(dia > ceil)[0]
            if not len(lo) and not len(hi): break
            if len(lo):
                k = lo[np.argmin(dia[lo])]
                p = np.array([X.ravel()[arg[k]], Y.ravel()[arg[k]]])
                j = cKDTree(seeds).query(p)[1]
                seeds = np.delete(seeds, j, 0)
            else:
                k = hi[np.argmax(dia[hi])]
                p = np.array([X.ravel()[arg[k]], Y.ravel()[arg[k]]])
                seeds = np.vstack([seeds, p])
            seeds = lloyd(seeds, dpair, 1, 0.3)
        ok = (dia.min() >= floor) and (dia.max() <= ceil) and nrange[0] <= len(dia) <= nrange[1]
        viol = np.clip(floor - dia, 0, None).sum() + np.clip(dia - ceil, 0, None).sum() + 2*max(0, nrange[0]-len(dia), len(dia)-nrange[1])
        score = (0 if ok else 1, viol, -dia.min())
        print(f'  try {t}: {len(dia)} openings, {dia.min():.2f}-{dia.max():.2f} median {np.median(dia):.2f} ok={ok}', flush=True)
        if best is None or score < best[0]:
            best = (score, seeds, solid, dia, (XW, YW))
        if ok: oks.append((score, seeds, solid, dia))
        if len(oks) >= want: break
    return best, oks

if __name__ == '__main__':
    import os
    LEV = os.environ.get('LEVEL', 'both')
    def save(name, oks):
        np.savez_compressed(OUT/'C'/f'plans_{name}.npz', sol=np.array([o[2] for o in oks]), dia=np.array([o[3] for o in oks], dtype=object), allow_pickle=True)
    if LEV in ('both', 'top'):
        print('level 1'); bt, okt = grow(D_TOP, W_TOP, TOP_FLOOR, TOP_CEIL, TOP_N); save('top', okt); print(len(okt), 'valid level-1 plans')
    if LEV in ('both', 'fine'):
        print('level 2'); bf, okf = grow(D_FINE, W_FINE, FINE_FLOOR, FINE_CEIL, FINE_N); save('fine', okf); print(len(okf), 'valid level-2 plans')
    if LEV in ('both', 'merge'):
        t = np.load(OUT/'C'/'plans_top.npz', allow_pickle=True); f = np.load(OUT/'C'/'plans_fine.npz', allow_pickle=True)
        np.savez_compressed(OUT/'C'/'plans.npz', top=t['sol'], fine=f['sol'], top_dia=t['dia'], fine_dia=f['dia'],
                            S=S.astype(np.float32), L=L, PX=PX, R_IN=R_IN, R_LOC=R_LOC, allow_pickle=True)
        json.dump(dict(SEED=SEED, D_TOP=D_TOP, W_TOP=W_TOP, D_FINE=D_FINE, W_FINE=W_FINE, WMIN=WMIN, WARP_AMP=WARP_AMP, WARP_LEN=WARP_LEN,
                       FILLET=FILLET, ROUND_K=ROUND_K, TOP_FLOOR=TOP_FLOOR, FINE_FLOOR=FINE_FLOOR), open(OUT/'C'/'params2d.json', 'w'), indent=1)
        print('merged')
