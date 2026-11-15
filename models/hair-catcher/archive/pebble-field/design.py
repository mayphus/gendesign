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


# ---------------------------------------------------------------- version D: vaulted lower mesh
VAULT_TILT = 35.0      # max strut angle from vertical
MID_STRUT_L = 99.0     # lower ribs longer than this get a mid-span strut
ARCH_SLOPE = np.tan(np.radians(50))  # arch underside rises 50° from horizontal (40° overhang)


def voronoi_edges(seeds, clip_r=RB + 0.3):
    """Rib centre-lines of a mirrored Voronoi pattern, clipped at the bore wall.
    Returns (A, B, A_on_wall, B_on_wall)."""
    allp = np.vstack([seeds, mirror(seeds), ghosts(RB + 14, 24)])
    vor = Voronoi(allp)
    out = []
    for (i, j), rv in zip(vor.ridge_points, vor.ridge_vertices):
        if -1 in rv or (i >= len(seeds) and j >= len(seeds)):
            continue
        A, B = vor.vertices[rv[0]].copy(), vor.vertices[rv[1]].copy()
        ra, rb = np.hypot(*A), np.hypot(*B)
        if ra > clip_r and rb > clip_r:
            continue
        wa, wb = ra > RB - 1.0, rb > RB - 1.0   # within 1 mm of the wall: wall-supported
        if ra > clip_r or rb > clip_r:        # clip the outer end onto the circle
            if ra > clip_r:
                A, B, ra, rb, wa, wb = B, A, rb, ra, wb, wa
            d = B - A
            a, b, c = d @ d, 2 * A @ d, A @ A - clip_r ** 2
            t = (-b + np.sqrt(b * b - 4 * a * c)) / (2 * a)
            B = A + t * d; wb = True
        if np.linalg.norm(B - A) > 0.2:
            out.append((A, B, wa, wb))
    return out


def nearest_on_edges(p, edges):
    best, bd = None, 1e9
    for A, B, _, _ in edges:
        d = B - A
        t = np.clip((p - A) @ d / (d @ d), 0, 1)
        q = A + t * d
        dd = np.linalg.norm(p - q)
        if dd < bd:
            best, bd = q, dd
    return best, bd


def vault_struts(top, bot, max_children=3):
    """Every interior junction of the lower pattern gets a strut, so every lower
    rib can be an arch sprung between supports. Struts start on the top ribs:
    at a top junction (shared trunk that forks) when one is in reach, otherwise
    straight from the nearest point on a top rib."""
    top_edges = voronoi_edges(top)
    tj = junctions(top, OPEN_R - 0.8)
    bj = junctions(bot, RB - 1.0)
    Hh = STRUT_TOP_Z - STRUT_BOT_Z
    tanm = np.tan(np.radians(VAULT_TILT - 1))
    reach = tanm * Hh
    kids = {i: [] for i in range(len(tj))}
    direct = []
    tree = cKDTree(tj)
    for b in bj:
        d, i = tree.query(b)
        if d <= reach * 0.85 and len(kids[i]) < max_children:
            kids[i].append(b)
        else:
            direct.append(b)
    segs = []
    for i, ch in kids.items():
        if not ch:
            continue
        T = np.r_[tj[i], STRUT_TOP_Z]
        ch = np.array(ch)
        if len(ch) == 1:
            segs.append((T, np.r_[ch[0], STRUT_BOT_Z])); continue
        off = np.linalg.norm(ch - tj[i], axis=1).max()
        zf = np.clip(STRUT_BOT_Z + off / tanm + 0.3, STRUT_BOT_Z + 1.4, STRUT_TOP_Z - 1.2)
        Fk = np.r_[tj[i], zf]
        segs.append((T, Fk))
        for c in ch:
            Bp = np.r_[c, STRUT_BOT_Z]
            if tilt(Fk, Bp) <= VAULT_TILT:
                segs.append((Fk, Bp))
            else:
                direct.append(c)
    # long lower ribs also get a strut at mid-span, so no arch spans more than ~L/2
    for A, Bq, wa, wb in voronoi_edges(bot):
        if (wa and wb) or np.linalg.norm(Bq - A) < MID_STRUT_L:
            continue
        direct.append((A + Bq) / 2)
    for b in direct:
        q, _ = nearest_on_edges(b, top_edges)
        P, Q = np.r_[q, STRUT_TOP_Z], np.r_[b, STRUT_BOT_Z]
        if tilt(P, Q) <= VAULT_TILT:      # out of reach: the vault arches over it instead
            segs.append((P, Q))
    return segs, bj


# ---------------------------------------------------------------- version D: funnels + vaulted dividers
def sub_seeds(g, top, target_area=27.0, rng_seed=0):
    """Split every top cell into k smaller cells (k from its area inside the bore,
    at least 2): k-means on the cell's pixels gives evenly sized sub-cells."""
    allp = np.vstack([top, mirror(top), ghosts(RB + 14, 24)])
    P = np.c_[g.X.ravel(), g.Y.ravel()]
    _, own = cKDTree(allp).query(P)
    inside = (g.R.ravel() < RB - 0.3)
    rng = np.random.default_rng(rng_seed)
    subs, parent = [], []
    for i in range(len(top)):
        pts = P[(own == i) & inside]
        if len(pts) == 0:
            continue
        area = len(pts) * g.h ** 2
        k = 1 if area < 1.9 * target_area else max(2, int(round(area / target_area)))  # small cells stay whole
        c = pts[rng.choice(len(pts), k, replace=False)]
        for _ in range(25):
            _, lab = cKDTree(c).query(pts)
            c = np.array([pts[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
        subs += list(c); parent += [i] * k
    return np.array(subs), np.array(parent)


def bisector_dist(P, seeds, allowed_parent=None, parent=None, k=6):
    """Distance from each point to the nearest Voronoi wall of its own cell.
    With parent ids, only walls between cells of the same parent count."""
    d, idx = cKDTree(seeds).query(P, k=k)
    own = seeds[idx[:, 0]]
    b = np.full(len(P), np.inf)
    for j in range(1, k):
        sj = seeds[idx[:, j]]
        den = 2 * np.linalg.norm(sj - own, axis=1) + 1e-9
        bj = (d[:, j] ** 2 - d[:, 0] ** 2) / den
        if parent is not None:
            bj = np.where(parent[idx[:, j]] == parent[idx[:, 0]], bj, np.inf)
        b = np.minimum(b, bj)
    return b


def funnel_fields(g, top, subs, parent):
    """b_top: distance to the top-cell walls (funnel walls);
    b_sub: distance to the dividers inside each top cell."""
    P = np.c_[g.X.ravel(), g.Y.ravel()]
    allp = np.vstack([top, mirror(top), ghosts(RB + 14, 24)])
    b_top = bisector_dist(P, allp).reshape(g.X.shape)
    b_sub = bisector_dist(P, subs, parent=parent).reshape(g.X.shape)
    return b_top, b_sub


def openings_from_b(g, b, rib, rib_noise, round_r, min_inscribed):
    """Same pebble construction as hole_mask, from a precomputed wall-distance field."""
    half = rib / 2 + rib_noise
    inner = (b > half + round_r) & (OPEN_R - g.R > round_r)
    mask = ndimage.distance_transform_edt(~inner) * g.h <= round_r
    lab, n = ndimage.label(mask)
    stats = []
    for i in range(1, n + 1):
        m = lab == i
        dt = ndimage.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] * g.h
        ins = 2 * dt.max()
        if ins < min_inscribed:
            mask[m] = False; continue
        stats.append(dict(inscribed=round(float(ins), 2),
                          equiv=round(float(2 * np.sqrt(m.sum() * g.h ** 2 / np.pi)), 2)))
    return mask, stats


def reopen(g, mask, round_r, min_inscribed):
    """Morphological opening (disc radius round_r) + drop openings below min_inscribed."""
    inner = ndimage.distance_transform_edt(mask) * g.h > round_r
    mask = ndimage.distance_transform_edt(~inner) * g.h <= round_r
    lab, n = ndimage.label(mask); stats = []
    for i in range(1, n + 1):
        m = lab == i
        dt = ndimage.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1] * g.h
        if 2 * dt.max() < min_inscribed:
            mask[m] = False; continue
        stats.append(dict(inscribed=round(float(2 * dt.max()), 2),
                          equiv=round(float(2 * np.sqrt(m.sum() * g.h ** 2 / np.pi)), 2)))
    return mask, stats


def warp_xy(X, Y, seed, amp, wl=(10.0, 16.0), waves=4):
    """Smooth sinusoidal domain warp (same seed -> same field on any grid)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(2):
        f = np.zeros_like(X)
        for _ in range(waves):
            k = 2 * np.pi / rng.uniform(*wl); a = rng.random() * np.pi; ph = rng.random() * 6.28
            f += np.sin(k * (X * np.cos(a) + Y * np.sin(a)) + ph)
        out.append(amp * f / np.sqrt(waves / 2))
    return X + out[0], Y + out[1]


class Warped:
    """A grid whose pattern coordinates (X, Y) are warped; R and spacing stay real."""
    def __init__(self, g, seed, amp):
        self.h, self.x, self.R = g.h, g.x, g.R
        self.X, self.Y = warp_xy(g.X, g.Y, seed, amp) if amp > 0 else (g.X, g.Y)


def boundary_dist(lab, h):
    """True (unwarped) distance from each pixel to the nearest label boundary."""
    edge = np.zeros(lab.shape, bool)
    edge[:-1] |= lab[:-1] != lab[1:]; edge[1:] |= lab[1:] != lab[:-1]
    edge[:, :-1] |= lab[:, :-1] != lab[:, 1:]; edge[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    return ndimage.distance_transform_edt(~edge) * h + 0.07   # calibrated against the exact bisector distance


def warped_fields(gw, top, subs, parent):
    """Cells assigned in warped coordinates, distances measured in real space:
    curved cell walls with exact rib widths. Returns (b_top, b_sub)."""
    P = np.c_[gw.X.ravel(), gw.Y.ravel()]
    allp = np.vstack([top, mirror(top), ghosts(RB + 14, 24)])
    _, tl = cKDTree(allp).query(P)
    tl = tl.reshape(gw.X.shape)
    sl = np.full(gw.X.shape, -1)
    for i in np.unique(parent):
        ids = np.where(parent == i)[0]
        m = tl == i
        if m.any():
            _, j = cKDTree(subs[ids]).query(P[m.ravel()])
            sl[m] = ids[j]
    b_top = boundary_dist(tl, gw.h)
    both = tl * 10000 + sl
    b_all = boundary_dist(both, gw.h)
    return b_top, b_all          # b_all: distance to any wall (top or divider)


def warped_top_mask(gw, top, rib, rib_noise, round_r, min_inscribed):
    P = np.c_[gw.X.ravel(), gw.Y.ravel()]
    allp = np.vstack([top, mirror(top), ghosts(RB + 14, 24)])
    _, tl = cKDTree(allp).query(P)
    b = boundary_dist(tl.reshape(gw.X.shape), gw.h)
    return openings_from_b(gw, b, rib, rib_noise, round_r, min_inscribed)
