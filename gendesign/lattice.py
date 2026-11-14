"""Lattice, Voronoi, and TPMS (gyroid) generators for shells and infill."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def gyroid(x, y, z, t: float = 0.0):
    """Gyroid implicit field. The surface is gyroid(...) = t; |t| < 1 is a thickened sheet."""
    return np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x) - t


def gyroid_mesh(
    period_mm: float = 10.0,
    size_mm=(30.0, 20.0, 16.0),
    wall_t: float = 0.8,
    pitch_mm: float | None = None,
    out_stl=None,
    n: int = 48,
):
    """Meshed gyroid sheet (or block infill) via marching cubes.

    wall_t is the approximate sheet thickness in mm (controlled by the
    iso-offset of the implicit field).
    """
    from skimage import measure
    import trimesh

    if pitch_mm is not None:
        period_mm = pitch_mm
    sx, sy, sz = size_mm
    # 2*pi / period * coord
    nx = max(16, int(round(n * sx / max(sy, sz, sx))))
    ny = max(16, int(round(n * sy / max(sy, sz, sx))))
    nz = max(16, int(round(n * sz / max(sy, sz, sx))))
    xs = np.linspace(0, sx, nx)
    ys = np.linspace(0, sy, ny)
    zs = np.linspace(0, sz, nz)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    k = 2 * np.pi / period_mm
    field = gyroid(k * X, k * Y, k * Z)
    # A thin sheet is the region |field| < tau. marching_cubes needs a single
    # iso; we mesh the solid band by taking min(tau - |field|) = 0.
    # d(field)/d(mm) ~ k, so tau ≈ wall_t * k / 2.
    tau = max(1e-3, wall_t * k / 2.0)
    solid = tau - np.abs(field)
    # One cell of "outside" on every side. Marching cubes leaves a hole
    # wherever the sheet meets the sample boundary; the empty pad closes
    # those faces so the exported block is a solid.
    solid = np.pad(solid, 1, mode="constant", constant_values=float(solid.min()) - 1.0)
    spacing = (float(xs[1] - xs[0]), float(ys[1] - ys[0]), float(zs[1] - zs[0]))
    try:
        verts, faces, *_ = measure.marching_cubes(solid, level=0.0, spacing=spacing)
    except Exception as e:
        raise RuntimeError(f"gyroid marching cubes failed (try a larger wall or grid): {e}") from e
    # Index 0 is the pad, one step before the original origin.
    verts -= np.array(spacing)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if mesh.volume < 0:
        mesh.invert()
    if out_stl:
        Path(out_stl).parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(out_stl))
    return mesh


def voronoi_lattice(
    size_mm=(30.0, 20.0, 16.0),
    n_seeds: int = 18,
    strut_r: float = 0.7,
    seed: int = 0,
    out_stl=None,
):
    """A box filled with Voronoi-edge struts (cylinders + joint balls)."""
    from scipy.spatial import Voronoi
    import trimesh

    rng = np.random.default_rng(seed)
    sx, sy, sz = size_mm
    # pad seeds outside the box so cells fill the domain
    pad = 0.25
    pts = rng.uniform(
        low=[-pad * sx, -pad * sy, -pad * sz],
        high=[sx * (1 + pad), sy * (1 + pad), sz * (1 + pad)],
        size=(n_seeds, 3),
    )
    vor = Voronoi(pts)
    parts = []
    seen = set()
    for i, j in vor.ridge_vertices:
        # ridge_vertices is a list of vertex index lists in 3D... actually
        # Voronoi.ridge_vertices is a list of lists of vertex indices (the
        # vertices of each ridge polygon). We want the edges of those polygons.
        pass
    # Iterate ridge polygons and emit each unique edge as a strut if it
    # intersects the box.
    def in_box(p, margin=0.0):
        return (-margin <= p[0] <= sx + margin and -margin <= p[1] <= sy + margin and -margin <= p[2] <= sz + margin)

    for verts in vor.ridge_vertices:
        if any(v < 0 for v in verts) or len(verts) < 2:
            continue
        cycle = list(verts) + [verts[0]]
        for a, b in zip(cycle, cycle[1:]):
            key = (min(a, b), max(a, b))
            if key in seen:
                continue
            seen.add(key)
            p1 = vor.vertices[a]
            p2 = vor.vertices[b]
            if not (in_box(p1, strut_r * 2) or in_box(p2, strut_r * 2)):
                continue
            # clip to box roughly by skipping very long ridges
            if np.linalg.norm(p2 - p1) > max(size_mm) * 1.5:
                continue
            mid = (p1 + p2) / 2
            if not in_box(mid, strut_r * 3):
                continue
            parts.append(trimesh.creation.cylinder(radius=strut_r, segment=(p1, p2), sections=8))
            parts.append(trimesh.creation.icosphere(subdivisions=1, radius=strut_r * 1.15))
            parts[-1].apply_translation(p1)
            parts.append(trimesh.creation.icosphere(subdivisions=1, radius=strut_r * 1.15))
            parts[-1].apply_translation(p2)
    if not parts:
        raise RuntimeError("no Voronoi struts landed in the box; try more seeds")
    mesh = trimesh.util.concatenate(parts)
    # clip to box
    box = trimesh.creation.box(extents=size_mm)
    box.apply_translation(np.array(size_mm) / 2)
    try:
        mesh = mesh.intersection(box)
    except Exception:
        pass
    if out_stl:
        Path(out_stl).parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(out_stl))
    return mesh


def infill_shell(shell: "trimesh.Trimesh", kind: str = "gyroid", period_mm: float = 8.0, wall_t: float = 0.7):
    """Intersect a gyroid (or similar) with an existing closed shell."""
    import trimesh

    b = shell.bounds
    size = b[1] - b[0]
    if kind == "gyroid":
        lattice = gyroid_mesh(period_mm=period_mm, size_mm=tuple(size), wall_t=wall_t, n=40)
        lattice.apply_translation(b[0])
    else:
        raise ValueError(f"unknown infill kind {kind}")
    try:
        return lattice.intersection(shell)
    except Exception:
        return lattice
