"""Graded Voronoi hair catcher: big pebble cells on the flush top face, small
cells on the bottom face, and a branching strut foam between them that follows
the cell edges (each top junction grows down and forks into the smaller cells).

Installed coords: z=0 basin surface, z=-8.6 bottom of collar.
"""
import numpy as np
from scipy.spatial import Voronoi, cKDTree
from scipy import ndimage

FL_R, FL_T = 23.0, 1.6
C_OD, C_ID = 35.21 / 2, 32.0 / 2
Z_BOT, LEAD = -8.6, 0.7
TOP_SKIN = (-1.6, 0.0)
BOT_SKIN = (-8.6, -7.2)
OPEN_R = C_ID - 0.6            # hard limit; the mirrored cells already stop ~1 mm short
STRUT_TOP_Z, STRUT_BOT_Z = -1.75, -7.05
MAX_TILT = 30.0


# ---------------------------------------------------------------- 2D seeds
def poisson_disc(rng, radius, spacing, n_try=5000):
    pts = []
    for _ in range(n_try):
        r = radius * np.sqrt(rng.random()); t = rng.random() * 2 * np.pi
        p = np.array([r * np.cos(t), r * np.sin(t)])
        if all(np.hypot(*(p - q)) >= spacing for q in pts):
            pts.append(p)
    return np.array(pts)


def ghosts(r, n):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[r * np.cos(t), r * np.sin(t)]


RB = C_ID  # cells are mirrored across the bore wall -> outer cell edges hug it


def mirror(pts):
    r = np.hypot(pts[:, 0], pts[:, 1])[:, None]
    return pts * (2 * RB - r) / np.maximum(r, 1e-6)


def lloyd(pts, radius, iters, rng, ghost_r):
    S = 60000
    sr = radius * np.sqrt(rng.random(S)); st = rng.random(S) * 2 * np.pi
    samp = np.c_[sr * np.cos(st), sr * np.sin(st)]
    for _ in range(iters):
        G = np.vstack([mirror(pts), ghosts(RB + 14, 24)])
        _, idx = cKDTree(np.vstack([pts, G])).query(samp)
        pts = np.array([samp[idx == i].mean(0) if (idx == i).any() else pts[i]
                        for i in range(len(pts))])
    return pts


def layer(rng, spacing, jitter, iters=8):
    p = poisson_disc(rng, RB - spacing * 0.3, spacing)
    p = lloyd(p, RB, iters, rng, None)
    p = p + rng.normal(0, jitter, p.shape)
    r = np.hypot(p[:, 0], p[:, 1])[:, None]
    return np.where(r > RB - 1.5, p * (RB - 1.5) / r, p)


# ---------------------------------------------------------------- 2D fields
class Grid:
    def __init__(self, h, half=23.4):
        self.h = h
        self.x = np.arange(-half, half + 1e-9, h)
        self.X, self.Y = np.meshgrid(self.x, self.x, indexing="ij")
        self.R = np.hypot(self.X, self.Y)


def noise(g, rng, amp, waves=5, wl=(7, 14)):
    f = np.zeros_like(g.X)
    for _ in range(waves):
        k = 2 * np.pi / rng.uniform(*wl); a = rng.random() * np.pi
        f += np.sin(k * (g.X * np.cos(a) + g.Y * np.sin(a)) + rng.random() * 6.28)
    return amp * f / np.sqrt(waves / 2)


def hole_mask(g, seeds, rib, rib_noise, round_r, min_inscribed):
    """Pebble openings: Voronoi cells inset by rib/2, then morphologically opened
    with a disc of radius round_r (every corner gets at least that radius).
    Openings whose inscribed diameter is below min_inscribed are filled solid."""
    allp = np.vstack([seeds, mirror(seeds), ghosts(RB + 14, 24)])
    P = np.c_[g.X.ravel(), g.Y.ravel()]
    d, idx = cKDTree(allp).query(P, k=6)
    own = allp[idx[:, 0]]
    b = np.full(len(P), np.inf)
    for j in range(1, 6):
        sj = allp[idx[:, j]]
        den = 2 * np.linalg.norm(sj - own, axis=1) + 1e-9
        b = np.minimum(b, (d[:, j] ** 2 - d[:, 0] ** 2) / den)
    b = b.reshape(g.X.shape)
    half = rib / 2 + rib_noise
    inner = (b > half + round_r) & (OPEN_R - g.R > round_r)
    # opening = dilate the eroded region back by round_r (exact EDT)
    dist_out = ndimage.distance_transform_edt(~inner) * g.h
    mask = dist_out <= round_r
    lab, n = ndimage.label(mask)
    stats = []
    for i in range(1, n + 1):
        m = lab == i
        dt = ndimage.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] * g.h
        ins = 2 * dt.max()
        if ins < min_inscribed:
            mask[m] = False
            continue
        area = m.sum() * g.h ** 2
        stats.append(dict(inscribed=round(float(ins), 2),
                          equiv=round(float(2 * np.sqrt(area / np.pi)), 2),
                          area=float(area)))
    return mask, stats


def signed_field(g, mask):
    """>0 inside openings (mm), <0 in material."""
    return (ndimage.distance_transform_edt(mask) - ndimage.distance_transform_edt(~mask)) * g.h


def junctions(seeds, r_max):
    allp = np.vstack([seeds, mirror(seeds), ghosts(RB + 14, 24)])
    v = Voronoi(allp).vertices
    return v[np.hypot(v[:, 0], v[:, 1]) < r_max]


def min_rib(g, mask):
    """Minimum material width between openings inside the bore (2x medial EDT)."""
    solid = ~mask & (g.R < OPEN_R + 0.5)
    dt = ndimage.distance_transform_edt(solid) * g.h
    # medial axis approx: local maxima of dt along the skeleton
    from skimage.morphology import skeletonize
    sk = skeletonize(solid) & (g.R < OPEN_R - 0.3)
    return float(2 * dt[sk].min()) if sk.any() else None


# ---------------------------------------------------------------- struts
def strut_tree(top_j, bot_j, rng, max_children=3):
    """Each bottom junction (small cells) is claimed by the nearest top junction
    (big cells) it can reach within MAX_TILT. A top junction with several
    children grows a vertical trunk that forks lower down - the big cell edges
    branch into the small-cell edges, like a graded foam."""
    H = STRUT_TOP_Z - STRUT_BOT_Z
    reach = np.tan(np.radians(MAX_TILT - 1)) * H
    kids = {i: [] for i in range(len(top_j))}
    tree = cKDTree(top_j)
    for b in bot_j:
        d, i = tree.query(b, k=min(3, len(top_j)))
        for dd, ii in zip(np.atleast_1d(d), np.atleast_1d(i)):
            if dd <= reach and len(kids[ii]) < max_children:
                kids[ii].append(b); break
    segs = []
    for i, ch in kids.items():
        T = np.r_[top_j[i], STRUT_TOP_Z]
        if not ch:
            continue
        if len(ch) == 1:
            segs.append((T, np.r_[ch[0], STRUT_BOT_Z]))
            continue
        ch = np.array(ch)
        off = np.linalg.norm(ch - top_j[i], axis=1).max()
        # lowest fork height that still keeps the branches within MAX_TILT
        tanm = np.tan(np.radians(MAX_TILT - 1))
        zf = STRUT_BOT_Z + off / tanm
        zf = min(zf, STRUT_TOP_Z - 1.6)
        zf = max(zf, STRUT_BOT_Z + 1.6)
        fork_xy = top_j[i] + 0.25 * (ch.mean(0) - top_j[i])
        Fk = np.r_[fork_xy, zf]
        segs.append((T, Fk))
        for c in ch:
            Bp = np.r_[c, STRUT_BOT_Z]
            if tilt(Fk, Bp) <= MAX_TILT:
                segs.append((Fk, Bp))
    # drop trunks whose fork lost every branch
    ends = {tuple(np.round(q, 5)) for p, q in segs}
    starts = {tuple(np.round(p, 5)) for p, q in segs}
    segs = [(p, q) for p, q in segs
            if q[2] <= STRUT_BOT_Z + 1e-6 or tuple(np.round(q, 5)) in starts]
    return segs


def tilt(P, Q):
    d = np.asarray(Q) - np.asarray(P)
    return float(np.degrees(np.arccos(abs(d[2]) / np.linalg.norm(d))))
