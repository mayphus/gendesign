"""Plane-stress response of a rasterized wall.

One solve, linear elastic Q4 elements. The load is an in-plane stand-in
for the membrane stress that accompanies a push on the web: the rim is
held and a patch near the center is pulled. It is not an out-of-plane
plate solve. What it does see is the material that is actually there, so
a re-entrant corner raises the peak von Mises stress and a fillet lowers it.

Units: lengths in mm, E in MPa, forces in N, stress in MPa.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def _q4(E: float, nu: float, a: float):
    """Stiffness and the four Gauss-point B matrices for a square of side a."""
    c = E / (1.0 - nu * nu)
    D = c * np.array([[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]])
    g = 1.0 / np.sqrt(3.0)
    KE = np.zeros((8, 8))
    Bs = []
    for xi, eta in ((-g, -g), (g, -g), (g, g), (-g, g)):
        dN_dxi = 0.25 * np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)])
        dN_deta = 0.25 * np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)])
        dN_dx = dN_dxi * (2.0 / a)
        dN_dy = dN_deta * (2.0 / a)
        B = np.zeros((3, 8))
        for i in range(4):
            B[0, 2 * i] = dN_dx[i]
            B[1, 2 * i + 1] = dN_dy[i]
            B[2, 2 * i] = dN_dy[i]
            B[2, 2 * i + 1] = dN_dx[i]
        KE += (B.T @ D @ B) * (a * a / 4.0)
        Bs.append(B)
    return KE, Bs, D


def plane_stress_peak(
    solid,
    pitch_mm: float,
    *,
    E: float = 2340.0,
    nu: float = 0.36,
    thickness_mm: float = 2.0,
    load_N: float = 10.0,
    support=None,
    load_radius_px: float | None = None,
):
    """Peak von Mises stress in a binary wall.

    `solid` is a boolean array, shape (nely, nelx), row 0 at minimum y.
    `support` is a boolean array of the same shape; elements under it are
    fixed. If omitted, the outer frame of elements is fixed.

    Two load cases, +x and +y, each of magnitude load_N, shared by the solid
    nodes inside load_radius_px of the center. The reported peak is the
    95th percentile of von Mises on solid elements outside that patch, so
    the number is the web, not the node where the force is applied.
    """
    solid = np.asarray(solid, dtype=bool)
    nely, nelx = solid.shape
    a = float(pitch_mm)
    if support is None:
        support = np.zeros_like(solid)
        support[0, :] = support[-1, :] = support[:, 0] = support[:, -1] = True
    else:
        support = np.asarray(support, dtype=bool)
    KE, Bs, D = _q4(E, nu, a)
    nnx, nny = nelx + 1, nely + 1
    ndof = 2 * nnx * nny

    elx = np.arange(nelx)
    ely = np.arange(nely)
    ELX, ELY = np.meshgrid(elx, ely, indexing="ij")
    # Node numbers, x fastest so node = ely * nnx + elx matches rows as y.
    # Element (elx, ely) uses nodes SW, SE, NE, NW.
    n_sw = ELY * nnx + ELX
    n_se = ELY * nnx + (ELX + 1)
    n_ne = (ELY + 1) * nnx + (ELX + 1)
    n_nw = (ELY + 1) * nnx + ELX

    def dofs(n):
        return np.stack([2 * n, 2 * n + 1], axis=-1)

    edof = np.concatenate([dofs(n_sw), dofs(n_se), dofs(n_ne), dofs(n_nw)], axis=-1)
    edof = edof.reshape(-1, 8)
    solid_el = solid.T.reshape(-1)  # elx-major, matching ELX, ELY with indexing ij then ravel
    # ELX, ELY from meshgrid ij have shape (nelx, nely); ravel C is elx-major, ely-minor.
    # solid.T has shape (nelx, nely) if solid is (nely, nelx). Yes.
    keep = np.flatnonzero(solid_el)
    if len(keep) < 4:
        return {"ok": False, "peak_MPa": float("inf"), "p95_MPa": float("inf"), "reason": "no solid"}

    edof_k = edof[keep]
    iK = np.repeat(edof_k, 8, axis=1).ravel()
    jK = np.tile(edof_k, 8).ravel()
    sK = np.tile(KE.ravel(), len(keep))
    # Void is simply absent. A tiny stiffness on the diagonal of free nodes
    # that ended up with no element is added after the solve check.
    K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
    K = (K + K.T) * 0.5

    # Support nodes: any node touching a support element.
    sup_node = np.zeros(nnx * nny, dtype=bool)
    used_node = np.zeros(nnx * nny, dtype=bool)
    ys, xs = np.nonzero(support & solid)
    for corners in (
        (ys * nnx + xs),
        (ys * nnx + xs + 1),
        ((ys + 1) * nnx + xs + 1),
        ((ys + 1) * nnx + xs),
    ):
        sup_node[corners] = True
    ys, xs = np.nonzero(solid)
    for corners in (
        (ys * nnx + xs),
        (ys * nnx + xs + 1),
        ((ys + 1) * nnx + xs + 1),
        ((ys + 1) * nnx + xs),
    ):
        used_node[corners] = True
    # Nodes that touch no solid element have no stiffness. Hold them.
    sup_node |= ~used_node
    fixed = np.zeros(ndof, dtype=bool)
    fixed[0::2] = sup_node
    fixed[1::2] = sup_node
    free = np.flatnonzero(~fixed)
    if len(free) < 2:
        return {"ok": False, "peak_MPa": float("inf"), "p95_MPa": float("inf"), "reason": "no free dofs"}

    cy = (np.arange(nny) - 0.0)
    cx = (np.arange(nnx) - 0.0)
    YY, XX = np.meshgrid(cy, cx, indexing="ij")
    # node (iy, ix) radius from the element-grid center
    center = np.array([(nelx) / 2.0, (nely) / 2.0])
    node_r = np.hypot(XX.T.ravel() - center[0], YY.T.ravel() - center[1])
    # XX meshgrid indexing ij with cx first argument... I mixed this up.
    # Rebuild plainly:
    ix = np.arange(nnx)
    iy = np.arange(nny)
    IX, IY = np.meshgrid(ix, iy, indexing="xy")
    node_r = np.hypot(IX - nelx / 2.0, IY - nely / 2.0).ravel()
    if load_radius_px is None:
        load_radius_px = max(2.0, 0.18 * min(nelx, nely))
    loaded_nodes = np.flatnonzero((node_r <= load_radius_px) & (~sup_node))
    if len(loaded_nodes) == 0:
        loaded_nodes = np.array([int(np.argmin(node_r))])
    share = float(load_N) / len(loaded_nodes)

    peaks = []
    for axis in (0, 1):
        F = np.zeros(ndof)
        F[2 * loaded_nodes + axis] = share
        try:
            u = spsolve(K[free][:, free], F[free])
        except Exception:
            return {"ok": False, "peak_MPa": float("inf"), "p95_MPa": float("inf"), "reason": "solve failed"}
        if not np.all(np.isfinite(u)):
            return {"ok": False, "peak_MPa": float("inf"), "p95_MPa": float("inf"), "reason": "non-finite"}
        U = np.zeros(ndof)
        U[free] = np.asarray(u).ravel()
        ue = U[edof_k]
        vm = np.zeros(len(keep))
        for gi, B in enumerate(Bs):
            sig = (D @ (B @ ue.T)).T  # (n, 3)
            vm += np.sqrt(sig[:, 0] ** 2 - sig[:, 0] * sig[:, 1] + sig[:, 1] ** 2 + 3.0 * sig[:, 2] ** 2)
        vm /= len(Bs)
        # Element centers, drop the loaded patch.
        el_iy = keep % nely
        el_ix = keep // nely
        el_r = np.hypot(el_ix + 0.5 - nelx / 2.0, el_iy + 0.5 - nely / 2.0)
        web = el_r > load_radius_px + 1.0
        use = vm[web] if web.any() else vm
        peaks.append(use)
    both = np.concatenate(peaks)
    both = both[np.isfinite(both)]
    if len(both) == 0:
        return {"ok": False, "peak_MPa": float("inf"), "p95_MPa": float("inf"), "reason": "no stress"}
    return {
        "ok": True,
        "peak_MPa": float(np.percentile(both, 99)),
        "p95_MPa": float(np.percentile(both, 95)),
        "median_MPa": float(np.median(both)),
        "n_elements": int(len(keep)),
        "pitch_mm": a,
    }
