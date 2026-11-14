"""2-D SIMP topology optimization (Q4 plane-stress elements).

Minimizes compliance for a prescribed volume fraction. Linear-elastic FEA
with a density filter and an optimality-criteria (OC) update. This is a
laptop-friendly educational/design-exploration tool, not a substitute for
validated structural analysis.

Default problem: a cantilever (left edge fixed, downward tip load).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def _element_stiffness(nu: float = 0.3) -> np.ndarray:
    k = np.array(
        [
            1 / 2 - nu / 6,
            1 / 8 + nu / 8,
            -1 / 4 - nu / 12,
            -1 / 8 + 3 * nu / 8,
            -1 / 4 + nu / 12,
            -1 / 8 - nu / 8,
            nu / 6,
            1 / 8 - 3 * nu / 8,
        ]
    )
    KE = (
        1
        / (1 - nu**2)
        * np.array(
            [
                [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
                [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
                [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
                [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
                [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
                [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
                [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
                [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
            ]
        )
    )
    return KE


def _filter_matrix(nelx: int, nely: int, rmin: float):
    nfilter = int(nelx * nely * ((2 * (np.ceil(rmin) - 1) + 1) ** 2))
    iH = np.zeros(nfilter, dtype=int)
    jH = np.zeros(nfilter, dtype=int)
    sH = np.zeros(nfilter)
    cc = 0
    for i in range(nelx):
        for j in range(nely):
            row = i * nely + j
            for k in range(max(i - int(np.ceil(rmin)) + 1, 0), min(i + int(np.ceil(rmin)), nelx)):
                for l in range(max(j - int(np.ceil(rmin)) + 1, 0), min(j + int(np.ceil(rmin)), nely)):
                    col = k * nely + l
                    fac = rmin - np.sqrt((i - k) ** 2 + (j - l) ** 2)
                    if fac > 0:
                        iH[cc] = row
                        jH[cc] = col
                        sH[cc] = fac
                        cc += 1
    H = coo_matrix((sH[:cc], (iH[:cc], jH[:cc])), shape=(nelx * nely, nelx * nely)).tocsc()
    Hs = np.array(H.sum(1)).flatten()
    return H, Hs


@dataclass
class TopOpt2DResult:
    density: np.ndarray
    compliance: list
    volume: list
    nelx: int
    nely: int
    volfrac: float
    residual: float = 0.0
    info: dict = field(default_factory=dict)

    def save(self, out_dir, pixel_mm: float = 1.0, thickness_mm: float = 2.0, threshold: float = 0.5):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "density.npy", self.density)
        (out / "stats.json").write_text(
            json.dumps(
                {
                    "nelx": self.nelx,
                    "nely": self.nely,
                    "volfrac": self.volfrac,
                    "compliance": self.compliance,
                    "volume": self.volume,
                    "final_compliance": self.compliance[-1] if self.compliance else None,
                    "final_volume": self.volume[-1] if self.volume else None,
                    "pixel_mm": pixel_mm,
                    "thickness_mm": thickness_mm,
                    "info": self.info,
                },
                indent=2,
            )
        )
        _save_density_image(self.density, out / "density.png")
        try:
            mesh_path = export_density_stl(
                self.density, out / "part.stl", pixel_mm=pixel_mm, thickness_mm=thickness_mm, threshold=threshold
            )
            err = out / "export_error.txt"
            if err.exists():
                err.unlink()
        except Exception as e:
            mesh_path = None
            (out / "export_error.txt").write_text(str(e))
        return out, mesh_path


def _save_density_image(x: np.ndarray, path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, max(2.2, 8 * x.shape[0] / max(x.shape[1], 1))), dpi=140)
    ax.imshow(1 - x, cmap="gray", origin="lower", vmin=0, vmax=1)
    ax.set_axis_off()
    fig.tight_layout(pad=0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)


def export_density_stl(density, path, pixel_mm=1.0, thickness_mm=2.0, threshold=0.5):
    """Marching-squares contour, extruded to a thin solid STL."""
    from skimage import measure
    import trimesh

    x = np.asarray(density, dtype=float)
    padded = np.pad(x, 1, mode="constant")
    contours = measure.find_contours(padded, threshold)
    if not contours:
        raise RuntimeError("no solid contour at this threshold")
    polys = []
    for c in contours:
        # skimage coords are (row, col) = (y, x); drop padding
        pts = np.column_stack([c[:, 1] - 1, c[:, 0] - 1]) * pixel_mm
        if len(pts) >= 3:
            polys.append(pts)
    path_2d = trimesh.path.Path2D(
        entities=[trimesh.path.entities.Line(np.arange(len(p) + 1) % (len(p) + 1)) for p in []],
        vertices=np.zeros((0, 2)),
    )
    # Build via polygons for robustness
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    shapes = []
    for p in polys:
        if len(p) < 3:
            continue
        poly = Polygon(p)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            continue
        shapes.append(poly)
    if not shapes:
        raise RuntimeError("contour polygons were empty")
    union = unary_union(shapes)
    geoms = list(union.geoms) if hasattr(union, "geoms") else [union]
    meshes = []
    for g in geoms:
        if g.is_empty or g.area <= 0:
            continue
        ext = np.array(g.exterior.coords)
        holes = [np.array(h.coords) for h in g.interiors]
        m = trimesh.creation.extrude_polygon(Polygon(ext, holes), height=thickness_mm)
        meshes.append(m)
    mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(path))
    return Path(path)


def topopt_2d(
    nelx: int = 60,
    nely: int = 20,
    volfrac: float = 0.35,
    penal: float = 3.0,
    rmin: float = 1.5,
    ft: int = 1,
    niter: int = 80,
    E0: float = 1.0,
    Emin: float = 1e-9,
    nu: float = 0.3,
    move: float = 0.2,
    # Passive regions as boolean arrays (nely, nelx): True = forced solid / void
    passive_solid: np.ndarray | None = None,
    passive_void: np.ndarray | None = None,
    # Optional custom BCs. If None, use the default cantilever.
    # fixed: list of (node, dof) with dof in {0,1}; loads: list of (node, dof, value)
    fixed=None,
    loads=None,
    verbose: bool = True,
) -> TopOpt2DResult:
    """Run 2-D SIMP. Density array is shaped (nely, nelx), x to the right, y up."""
    nelx, nely = int(nelx), int(nely)
    KE = _element_stiffness(nu)
    ndof = 2 * (nelx + 1) * (nely + 1)
    edofMat = np.zeros((nelx * nely, 8), dtype=int)
    for elx in range(nelx):
        for ely in range(nely):
            el = elx * nely + ely
            n1 = (nely + 1) * elx + ely
            n2 = (nely + 1) * (elx + 1) + ely
            edofMat[el, :] = np.array(
                [
                    2 * n1 + 2,
                    2 * n1 + 3,
                    2 * n2 + 2,
                    2 * n2 + 3,
                    2 * n2,
                    2 * n2 + 1,
                    2 * n1,
                    2 * n1 + 1,
                ]
            )
    iK = np.kron(edofMat, np.ones((8, 1), dtype=int)).flatten()
    jK = np.kron(edofMat, np.ones((1, 8), dtype=int)).flatten()

    if fixed is None:
        # left edge fully fixed
        fixed = [(nely * 0 + iy, 0) for iy in range(nely + 1)] + [
            (nely * 0 + iy, 1) for iy in range(nely + 1)
        ]
        # node numbers on left: iy  (elx=0)
        fixed = []
        for iy in range(nely + 1):
            n = iy  # elx = 0
            fixed.append((n, 0))
            fixed.append((n, 1))
    if loads is None:
        # downward load at the bottom-right tip? Sigmund default is mid-right or bottom-right.
        # Classic MBB is different; cantilever: load at right-middle, downward.
        n_load = (nelx) * (nely + 1) + nely // 2
        loads = [(n_load, 1, -1.0)]

    fixeddofs = np.array(sorted({2 * n + d for n, d in fixed}), dtype=int)
    alldofs = np.arange(ndof)
    freedofs = np.setdiff1d(alldofs, fixeddofs)
    F = np.zeros(ndof)
    for n, d, val in loads:
        F[2 * n + d] += val

    H, Hs = _filter_matrix(nelx, nely, rmin)
    x = np.full((nely, nelx), volfrac, dtype=float)
    if passive_solid is not None:
        x[np.asarray(passive_solid, dtype=bool)] = 1.0
    if passive_void is not None:
        x[np.asarray(passive_void, dtype=bool)] = 1e-3
    xPhys = x.copy()
    loop, change = 0, 1.0
    compl, vols = [], []
    dc = np.zeros((nely, nelx))
    dv = np.ones((nely, nelx))

    while change > 0.01 and loop < niter:
        loop += 1
        E = Emin + (xPhys.T.reshape(-1) ** penal) * (E0 - Emin)  # column-wise (elx major)
        # xPhys is (nely, nelx); element order is elx-major, ely-minor, matching edofMat
        xcol = xPhys.T.ravel(order="C")  # elx slow? Wait: xPhys[ely, elx], .T is (nelx, nely), ravel C is elx-major, ely-minor. Yes.
        E = Emin + (xcol**penal) * (E0 - Emin)
        sK = (KE.flatten()[np.newaxis, :] * E[:, np.newaxis]).flatten()
        K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
        K = (K + K.T) * 0.5
        U = np.zeros(ndof)
        U[freedofs] = spsolve(K[freedofs, :][:, freedofs], F[freedofs])

        ce = np.zeros(nelx * nely)
        for el in range(nelx * nely):
            ue = U[edofMat[el, :]]
            ce[el] = ue @ KE @ ue
        ce = ce.reshape((nelx, nely)).T  # back to (nely, nelx)
        dc = -penal * (E0 - Emin) * xPhys ** (penal - 1) * ce
        dv = np.ones((nely, nelx))
        c = float((xPhys**penal * ce).sum())
        # filter
        if ft == 1:
            dc = (H @ (dc.T.ravel() / Hs)).reshape((nelx, nely)).T
        else:
            dc = (H @ (x.T.ravel() * dc.T.ravel() / Hs / np.maximum(1e-3, x.T.ravel()))).reshape((nelx, nely)).T
            dv = (H @ (dv.T.ravel() / Hs)).reshape((nelx, nely)).T

        # OC
        l1, l2 = 0.0, 1e9
        xnew = x.copy()
        while (l2 - l1) > 1e-4:
            lmid = 0.5 * (l2 + l1)
            xnew = np.clip(
                x * np.sqrt(np.maximum(1e-30, -dc / (dv * lmid))),
                x - move,
                x + move,
            )
            xnew = np.clip(xnew, 0.0, 1.0)
            if passive_solid is not None:
                xnew[np.asarray(passive_solid, dtype=bool)] = 1.0
            if passive_void is not None:
                xnew[np.asarray(passive_void, dtype=bool)] = 1e-3
            if ft == 1:
                xPhys = (H @ xnew.T.ravel() / Hs).reshape((nelx, nely)).T
            else:
                xPhys = xnew.copy()
            if xPhys.mean() > volfrac:
                l1 = lmid
            else:
                l2 = lmid
        change = float(np.abs(xnew - x).max())
        x = xnew
        compl.append(c)
        vols.append(float(xPhys.mean()))
        if verbose and (loop % 5 == 0 or loop == 1):
            print(f"it {loop:3d}  c={c:.4f}  vol={xPhys.mean():.3f}  change={change:.3f}")

    return TopOpt2DResult(
        density=xPhys,
        compliance=compl,
        volume=vols,
        nelx=nelx,
        nely=nely,
        volfrac=volfrac,
        residual=change,
        info={"iters": loop, "penal": penal, "rmin": rmin},
    )


def default_cantilever_nodes(nelx, nely):
    """Helper documenting the default BC: left edge fixed, mid-right downward load."""
    fixed = [(iy, 0) for iy in range(nely + 1)] + [(iy, 1) for iy in range(nely + 1)]
    n_load = nelx * (nely + 1) + nely // 2
    loads = [(n_load, 1, -1.0)]
    return fixed, loads
