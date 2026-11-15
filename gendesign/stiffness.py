"""Out-of-plane beam grillage for a flat strut graph.

Each edge is a Timoshenko beam with a rectangular section (in-plane
width by out-of-plane thickness) plus Saint-Venant torsion. Nodes have
three degrees of freedom: vertical displacement w (positive up) and
small rotations about the global x and y axes. The rim is clamped.

Units are consistent millimetre units: E in MPa (N/mm^2), lengths in
mm, forces in N, displacement in mm.

This is a ranking model. It does not include shell membrane action, so
a cone or a dish is stiffer in reality than the flat graph of its plan.
Printed PLA is anisotropic; E is a single conservative modulus. The
response is linear: no contact, no buckling, no broken layer lines.
"""
from __future__ import annotations

import numpy as np


def section_properties(width_mm: float, thickness_mm: float) -> dict:
    """I, J, A for a rectangular strut. width is the in-plane size."""
    b = max(float(width_mm), 1e-6)
    h = max(float(thickness_mm), 1e-6)
    # Bending that resists a vertical load: axis lies in the plate.
    inertia = b * h**3 / 12.0
    # Saint-Venant torsion constant for a rectangle (h along the longer side
    # in the usual formula). Swap so a >= b_ in the approximation.
    a, c = (h, b) if h >= b else (b, h)
    ratio = c / a
    j = a * c**3 * (1.0 / 3.0 - 0.21 * ratio * (1.0 - ratio**4 / 12.0))
    return {"I": float(inertia), "J": float(max(j, 1e-12)), "A": float(b * h), "b": b, "h": h}


def _timoshenko_bend(E: float, I: float, A: float, G: float, L: float, kappa: float) -> np.ndarray:
    """4x4 for DOF [w1, θ1, w2, θ2], θ positive about the bending axis.

    Matches the Euler-Bernoulli cantilever δ = F L^3 / (3 E I) at phi = 0,
    and adds shear through phi = 12 E I / (kappa G A L^2).
    """
    phi = 12.0 * E * I / (kappa * G * A * L * L)
    k = E * I / ((1.0 + phi) * L**3)
    L2 = L * L
    return k * np.array([
        [12.0, 6.0 * L, -12.0, 6.0 * L],
        [6.0 * L, (4.0 + phi) * L2, -6.0 * L, (2.0 - phi) * L2],
        [-12.0, -6.0 * L, 12.0, -6.0 * L],
        [6.0 * L, (2.0 - phi) * L2, -6.0 * L, (4.0 + phi) * L2],
    ], dtype=float)


def grillage_deflection(
    nodes_xy,
    edges,
    widths,
    thickness_mm: float,
    *,
    E: float = 2340.0,
    nu: float = 0.36,
    load_N: float = 10.0,
    load_xy=(0.0, 0.0),
    load_radius_mm: float = 5.0,
    fixed_mask=None,
    kappa: float = 5.0 / 6.0,
    min_edge_mm: float = 0.35,
) -> dict:
    """Solve the grillage.

    nodes_xy: (N, 2) millimetres.
    edges: (M, 2) integer node indices.
    widths: (M,) in-plane strut width at each edge.
    fixed_mask: (N,) bool, clamped nodes. If omitted, nothing is fixed
    and the result is reported as not connected.

    The load is spread over free nodes within load_radius_mm of load_xy
    (the nearest free node if the disc is empty). Positive load_N pushes
    downward. max_disp_mm is the largest downward displacement.
    stiffness_N_per_mm is load_N / max_disp_mm.
    """
    nodes = np.asarray(nodes_xy, dtype=float).reshape(-1, 2)
    edges = np.asarray(edges, dtype=int).reshape(-1, 2) if len(edges) else np.zeros((0, 2), dtype=int)
    widths = np.asarray(widths, dtype=float).reshape(-1)
    n = len(nodes)
    empty = {
        "max_disp_mm": float("inf"),
        "stiffness_N_per_mm": 0.0,
        "connected": False,
        "n_nodes": n,
        "n_edges": int(len(edges)),
        "n_fixed": 0,
        "n_loaded": 0,
        "tip_disp_mm": None,
    }
    if n == 0 or len(edges) == 0:
        return empty
    if fixed_mask is None:
        fixed = np.zeros(n, dtype=bool)
    else:
        fixed = np.asarray(fixed_mask, dtype=bool).reshape(n)
    if not fixed.any():
        return empty

    G = E / (2.0 * (1.0 + nu))
    ndof = 3 * n
    # Sparse COO assembly.
    ii, jj, vv = [], [], []

    def add_local(dofs, Kloc):
        for a, da in enumerate(dofs):
            for b, db in enumerate(dofs):
                val = Kloc[a, b]
                if val != 0.0:
                    ii.append(da)
                    jj.append(db)
                    vv.append(val)

    used = 0
    for e, (a, b) in enumerate(edges):
        if a == b or a < 0 or b < 0 or a >= n or b >= n:
            continue
        p = nodes[b] - nodes[a]
        L = float(np.hypot(p[0], p[1]))
        if L < min_edge_mm:
            continue
        sec = section_properties(widths[e] if e < len(widths) else widths[-1], thickness_mm)
        Kb = _timoshenko_bend(E, sec["I"], sec["A"], G, L, kappa)
        Kt = (G * sec["J"] / L) * np.array([[1.0, -1.0], [-1.0, 1.0]])
        # local DOF order: w1, torsion1, bend1, w2, torsion2, bend2
        K = np.zeros((6, 6))
        bend_ix = [0, 2, 3, 5]
        tor_ix = [1, 4]
        for ia, i in enumerate(bend_ix):
            for ib, j in enumerate(bend_ix):
                K[i, j] = Kb[ia, ib]
        for ia, i in enumerate(tor_ix):
            for ib, j in enumerate(tor_ix):
                K[i, j] = Kt[ia, ib]
        c, s = p[0] / L, p[1] / L
        # local [w, torsion, bend] from global [w, θx, θy]
        # torsion = θ · tangent, bend = θ · left-normal (-s, c)
        T3 = np.array([
            [1.0, 0.0, 0.0],
            [0.0, c, s],
            [0.0, -s, c],
        ])
        T = np.zeros((6, 6))
        T[0:3, 0:3] = T3
        T[3:6, 3:6] = T3
        Kg = T.T @ K @ T
        dofs = [3 * a, 3 * a + 1, 3 * a + 2, 3 * b, 3 * b + 1, 3 * b + 2]
        add_local(dofs, Kg)
        used += 1
    if used == 0:
        return empty

    import scipy.sparse as sp
    from scipy.sparse.linalg import spsolve

    Kglob = sp.coo_matrix((vv, (ii, jj)), shape=(ndof, ndof)).tocsr()
    # Symmetrise against tiny assembly asymmetry.
    Kglob = 0.5 * (Kglob + Kglob.T)

    fixed_dof = np.zeros(ndof, dtype=bool)
    fixed_dof[0::3] = fixed
    fixed_dof[1::3] = fixed
    fixed_dof[2::3] = fixed
    free = np.where(~fixed_dof)[0]
    if len(free) == 0:
        out = dict(empty)
        out["n_fixed"] = int(fixed.sum())
        out["max_disp_mm"] = 0.0
        out["stiffness_N_per_mm"] = float("inf")
        out["connected"] = True
        return out

    # Connectivity: free loaded nodes must reach a fixed node.
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        if 0 <= a < n and 0 <= b < n and a != b:
            union(int(a), int(b))
    # Map every node to whether its component contains a support.
    supported_root = set()
    for i in np.where(fixed)[0]:
        supported_root.add(find(int(i)))

    F = np.zeros(ndof)
    target = np.asarray(load_xy, dtype=float)
    dist = np.hypot(nodes[:, 0] - target[0], nodes[:, 1] - target[1])
    near = (~fixed) & (dist <= load_radius_mm)
    loaded = np.where(near)[0]
    if len(loaded) == 0:
        free_nodes = np.where(~fixed)[0]
        if len(free_nodes) == 0:
            return empty
        loaded = np.array([free_nodes[np.argmin(dist[free_nodes])]])
    share = float(load_N) / len(loaded)
    for i in loaded:
        F[3 * int(i)] -= share  # downward

    reachable = all(find(int(i)) in supported_root for i in loaded)
    if not reachable:
        out = dict(empty)
        out["n_fixed"] = int(fixed.sum())
        out["n_loaded"] = int(len(loaded))
        out["connected"] = False
        return out

    Kff = Kglob[free][:, free]
    try:
        u = spsolve(Kff.tocsc(), F[free])
    except Exception:
        out = dict(empty)
        out["n_fixed"] = int(fixed.sum())
        out["connected"] = False
        return out
    if not np.all(np.isfinite(u)):
        out = dict(empty)
        out["connected"] = False
        return out
    disp = np.zeros(ndof)
    disp[free] = np.asarray(u).ravel()
    w = disp[0::3]
    downward = -w
    # Ignore tiny noise on fixed nodes (should be zero).
    downward = np.where(fixed, 0.0, downward)
    max_down = float(downward.max()) if n else 0.0
    if max_down < 1e-9:
        max_down = 1e-9
    loaded_down = float(np.max(-w[loaded]))
    return {
        "max_disp_mm": max_down,
        "loaded_disp_mm": loaded_down,
        "stiffness_N_per_mm": float(load_N) / max_down if max_down > 0 else float("inf"),
        "connected": True,
        "n_nodes": n,
        "n_edges": int(used),
        "n_fixed": int(fixed.sum()),
        "n_loaded": int(len(loaded)),
        "w_mm": w,
    }
