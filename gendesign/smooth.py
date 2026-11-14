"""Shape smoothing and fillet-style passes on meshes (and notes for CAD fillets)."""
from __future__ import annotations

from pathlib import Path


def laplacian_smooth(mesh_or_path, iterations: int = 5, lamb: float = 0.5, out=None):
    import trimesh

    mesh = trimesh.load(str(mesh_or_path)) if not hasattr(mesh_or_path, "vertices") else mesh_or_path.copy()
    try:
        mesh = trimesh.smoothing.filter_laplacian(mesh, lamb=lamb, iterations=iterations)
    except TypeError:
        mesh = trimesh.smoothing.filter_laplacian(mesh, iterations=iterations)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(out))
    return mesh


def taubin_smooth(mesh_or_path, iterations: int = 8, out=None):
    import trimesh

    mesh = trimesh.load(str(mesh_or_path)) if not hasattr(mesh_or_path, "vertices") else mesh_or_path.copy()
    try:
        mesh = trimesh.smoothing.filter_taubin(mesh, iterations=iterations)
    except Exception:
        mesh = trimesh.smoothing.filter_laplacian(mesh, iterations=iterations)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(out))
    return mesh


def close_and_smooth(mesh_or_path, iterations: int = 3, out=None):
    """Fill small holes if possible, then a light Laplacian pass."""
    import trimesh

    mesh = trimesh.load(str(mesh_or_path)) if not hasattr(mesh_or_path, "vertices") else mesh_or_path.copy()
    try:
        mesh.fill_holes()
    except Exception:
        pass
    return laplacian_smooth(mesh, iterations=iterations, out=out)


# CAD fillets belong in the CadQuery generators (see models/*/generate.py).
# Mesh smoothing cannot replace a real fillet on a STEP model; use it only
# to tidy a voxel / marching-cubes export before a visual check.
