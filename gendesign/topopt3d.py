"""Simple 3-D voxel SIMP (8-node hex elements, linear elasticity).

Intended for small laptop-scale grids (e.g. 16x8x8). Same caveats as the
2-D solver: linear-elastic compliance minimization, not validated FEA.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def _hex_stiffness(nu: float = 0.3) -> np.ndarray:
    """Analytical 24x24 stiffness for an 8-node hex of size 1x1x1, E=1."""
    # Gauss 2x2x2 integration of the standard isoparametric hex.
    g = 1.0 / np.sqrt(3.0)
    gauss = [(-g, -g, -g), (g, -g, -g), (g, g, -g), (-g, g, -g),
             (-g, -g, g), (g, -g, g), (g, g, g), (-g, g, g)]
    # node coords of the reference element [0,1]^3 (same order as n1..n8 below)
    nodes = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)
    # map to [-1,1] for shape functions
    # We build N in xi,eta,zeta in [-1,1] and Jacobian from physical [0,1].
    lam = nu / ((1 + nu) * (1 - 2 * nu))
    mu = 1.0 / (2 * (1 + nu))
    D = np.array([
        [lam + 2 * mu, lam, lam, 0, 0, 0],
        [lam, lam + 2 * mu, lam, 0, 0, 0],
        [lam, lam, lam + 2 * mu, 0, 0, 0],
        [0, 0, 0, mu, 0, 0],
        [0, 0, 0, 0, mu, 0],
        [0, 0, 0, 0, 0, mu],
    ])
    KE = np.zeros((24, 24))
    for xi, eta, zeta in gauss:
        dN_dxi = np.zeros((3, 8))
        # standard hex shape derivatives in [-1,1]
        # nodes in order: (-1-1-1),(1-1-1),(1 1-1),(-1 1-1),(-1-1 1),(1-1 1),(1 1 1),(-1 1 1)
        signs = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
        ], dtype=float)
        for a, (sx, sy, sz) in enumerate(signs):
            dN_dxi[0, a] = sx * (1 + sy * eta) * (1 + sz * zeta) / 8
            dN_dxi[1, a] = sy * (1 + sx * xi) * (1 + sz * zeta) / 8
            dN_dxi[2, a] = sz * (1 + sx * xi) * (1 + sy * eta) / 8
        # physical coords of reference [0,1] cube: x = (xi+1)/2, J = 0.5 I, detJ = 0.125
        Jinv = np.eye(3) * 2.0
        detJ = 0.125
        dN = Jinv @ dN_dxi
        B = np.zeros((6, 24))
        for a in range(8):
            i = 3 * a
            dNx, dNy, dNz = dN[0, a], dN[1, a], dN[2, a]
            B[0, i] = dNx
            B[1, i + 1] = dNy
            B[2, i + 2] = dNz
            B[3, i] = dNy
            B[3, i + 1] = dNx
            B[4, i + 1] = dNz
            B[4, i + 2] = dNy
            B[5, i] = dNz
            B[5, i + 2] = dNx
        KE += (B.T @ D @ B) * detJ
    return KE


def _nnode(ix, iy, iz, nely, nelz):
    return iz * (nely + 1) * (nelx_dummy := 0) if False else iz * (nely + 1) * 0


def _node(ix, iy, iz, nelx, nely, nelz):
    return ix * (nely + 1) * (nelz + 1) + iy * (nelz + 1) + iz


def _edof_mat(nelx, nely, nelz):
    # 8 nodes of element (ex,ey,ez), 3 dofs each
    nels = nelx * nely * nelz
    edof = np.zeros((nels, 24), dtype=int)
    e = 0
    for ex in range(nelx):
        for ey in range(nely):
            for ez in range(nelz):
                n000 = _node(ex, ey, ez, nelx, nely, nelz)
                n100 = _node(ex + 1, ey, ez, nelx, nely, nelz)
                n110 = _node(ex + 1, ey + 1, ez, nelx, nely, nelz)
                n010 = _node(ex, ey + 1, ez, nelx, nely, nelz)
                n001 = _node(ex, ey, ez + 1, nelx, nely, nelz)
                n101 = _node(ex + 1, ey, ez + 1, nelx, nely, nelz)
                n111 = _node(ex + 1, ey + 1, ez + 1, nelx, nely, nelz)
                n011 = _node(ex, ey + 1, ez + 1, nelx, nely, nelz)
                nodes = [n000, n100, n110, n010, n001, n101, n111, n011]
                dofs = []
                for n in nodes:
                    dofs.extend([3 * n, 3 * n + 1, 3 * n + 2])
                edof[e, :] = dofs
                e += 1
    return edof


def _filter(nelx, nely, nelz, rmin):
    nels = nelx * nely * nelz
    radius = int(np.ceil(rmin))
    iH, jH, sH = [], [], []

    def eid(x, y, z):
        return x * nely * nelz + y * nelz + z

    for ex in range(nelx):
        for ey in range(nely):
            for ez in range(nelz):
                row = eid(ex, ey, ez)
                for i in range(max(0, ex - radius), min(nelx, ex + radius + 1)):
                    for j in range(max(0, ey - radius), min(nely, ey + radius + 1)):
                        for k in range(max(0, ez - radius), min(nelz, ez + radius + 1)):
                            fac = rmin - np.sqrt((ex - i) ** 2 + (ey - j) ** 2 + (ez - k) ** 2)
                            if fac > 0:
                                iH.append(row)
                                jH.append(eid(i, j, k))
                                sH.append(fac)
    H = coo_matrix((sH, (iH, jH)), shape=(nels, nels)).tocsc()
    Hs = np.array(H.sum(1)).flatten()
    return H, Hs


@dataclass
class TopOpt3DResult:
    density: np.ndarray  # (nelx, nely, nelz)
    compliance: list
    volume: list
    nelx: int
    nely: int
    nelz: int
    volfrac: float
    info: dict = field(default_factory=dict)

    def save(self, out_dir, voxel_mm: float = 1.0, threshold: float = 0.5):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "density.npy", self.density)
        (out / "stats.json").write_text(
            json.dumps(
                {
                    "shape": list(self.density.shape),
                    "volfrac": self.volfrac,
                    "compliance": self.compliance,
                    "volume": self.volume,
                    "final_compliance": self.compliance[-1] if self.compliance else None,
                    "voxel_mm": voxel_mm,
                },
                indent=2,
            )
        )
        _save_midplane(self.density, out / "density_midplane.png")
        try:
            p = export_density_stl_3d(self.density, out / "part.stl", voxel_mm=voxel_mm, threshold=threshold)
            err = out / "export_error.txt"
            if err.exists():
                err.unlink()
        except Exception as e:
            p = None
            (out / "export_error.txt").write_text(str(e))
        return out, p


def _save_midplane(x, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mid = x[:, :, x.shape[2] // 2].T
    fig, ax = plt.subplots(figsize=(7, 4), dpi=130)
    ax.imshow(1 - mid, cmap="gray", origin="lower", vmin=0, vmax=1)
    ax.set_title("mid-plane density (z)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def export_density_stl_3d(density, path, voxel_mm=1.0, threshold=0.5):
    from skimage import measure
    import trimesh

    x = np.pad(np.asarray(density, dtype=float), 1, mode="constant")
    verts, faces, *_ = measure.marching_cubes(x, level=threshold, spacing=(voxel_mm,) * 3)
    # undo padding
    verts -= voxel_mm
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    try:
        mesh = trimesh.smoothing.filter_laplacian(mesh, iterations=3)
    except Exception:
        pass
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(path))
    return Path(path)


def topopt_3d(
    nelx: int = 16,
    nely: int = 8,
    nelz: int = 8,
    volfrac: float = 0.3,
    penal: float = 3.0,
    rmin: float = 1.4,
    niter: int = 25,
    E0: float = 1.0,
    Emin: float = 1e-9,
    nu: float = 0.3,
    move: float = 0.2,
    verbose: bool = True,
    # default: cantilever, fix x=0 face, downward load at x=nelx, y=0, mid z
) -> TopOpt3DResult:
    nelx, nely, nelz = int(nelx), int(nely), int(nelz)
    KE = _hex_stiffness(nu)
    edof = _edof_mat(nelx, nely, nelz)
    nels = nelx * nely * nelz
    ndof = 3 * (nelx + 1) * (nely + 1) * (nelz + 1)
    iK = np.kron(edof, np.ones((24, 1), dtype=int)).flatten()
    jK = np.kron(edof, np.ones((1, 24), dtype=int)).flatten()

    fixed = []
    for iy in range(nely + 1):
        for iz in range(nelz + 1):
            n = _node(0, iy, iz, nelx, nely, nelz)
            fixed.extend([3 * n, 3 * n + 1, 3 * n + 2])
    fixeddofs = np.unique(np.array(fixed, dtype=int))
    freedofs = np.setdiff1d(np.arange(ndof), fixeddofs)
    F = np.zeros(ndof)
    nload = _node(nelx, 0, nelz // 2, nelx, nely, nelz)
    F[3 * nload + 1] = -1.0  # -Y

    H, Hs = _filter(nelx, nely, nelz, rmin)
    x = np.full(nels, volfrac)
    xPhys = x.copy()
    compl, vols = [], []
    change, loop = 1.0, 0
    while change > 0.02 and loop < niter:
        loop += 1
        E = Emin + (xPhys**penal) * (E0 - Emin)
        sK = (KE.flatten()[np.newaxis, :] * E[:, np.newaxis]).flatten()
        K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
        K = (K + K.T) * 0.5
        U = np.zeros(ndof)
        U[freedofs] = spsolve(K[freedofs, :][:, freedofs], F[freedofs])
        ce = np.empty(nels)
        for e in range(nels):
            ue = U[edof[e]]
            ce[e] = ue @ KE @ ue
        c = float((xPhys**penal * ce).sum())
        dc = -penal * (E0 - Emin) * xPhys ** (penal - 1) * ce
        dv = np.ones(nels)
        dc = np.array(H @ (dc / Hs)).flatten()
        dv = np.array(H @ (dv / Hs)).flatten()
        l1, l2 = 0.0, 1e9
        xnew = x.copy()
        while l2 - l1 > 1e-4:
            lmid = 0.5 * (l2 + l1)
            xnew = np.clip(x * np.sqrt(np.maximum(1e-30, -dc / (dv * lmid))), x - move, x + move)
            xnew = np.clip(xnew, 0.0, 1.0)
            xPhys = np.array(H @ (xnew / Hs)).flatten()
            if xPhys.mean() > volfrac:
                l1 = lmid
            else:
                l2 = lmid
        change = float(np.abs(xnew - x).max())
        x = xnew
        compl.append(c)
        vols.append(float(xPhys.mean()))
        if verbose:
            print(f"it {loop:3d}  c={c:.4f}  vol={xPhys.mean():.3f}  change={change:.3f}")
    dens = xPhys.reshape((nelx, nely, nelz))
    return TopOpt3DResult(dens, compl, vols, nelx, nely, nelz, volfrac, info={"iters": loop, "penal": penal, "rmin": rmin})
