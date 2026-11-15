"""Implicit (signed-distance) modeling: smooth Booleans, meshing, print checks.

Convention: a field is negative inside material and positive outside, in mm.
Generators build a field on a regular grid, then `mesh_field` turns it into a
watertight mesh. The hair-catcher pebble designs (C, D, E) all use this.
"""
from __future__ import annotations

from functools import reduce

import numpy as np


def mx(*fields):
    """Sharp intersection of any number of fields."""
    return reduce(np.maximum, fields)


def smin(a, b, k):
    """Smooth union with blend radius k (polynomial smooth minimum)."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    """Smooth intersection with blend radius k."""
    return -smin(-a, -b, k)


def mask_field(mask, h):
    """Signed distance (mm) from a boolean raster: <0 where mask is True."""
    from scipy import ndimage

    mask = np.asarray(mask, bool)
    return (ndimage.distance_transform_edt(~mask) - ndimage.distance_transform_edt(mask)) * h


def polygon_field(X, Y, polygons, *, near=None, far=-5.0):
    """Exact 2-D signed distance to shapely polygons: >0 inside a polygon.

    `near` limits the (slow) exact evaluation to a boolean region; elsewhere
    the field is `far`. Holes in a plate are usually built this way, so the
    mesh has no pixel staircase.
    """
    import shapely
    from shapely.geometry import MultiPolygon

    out = np.full(X.shape, float(far))
    if not polygons:
        return out
    mp = MultiPolygon(list(polygons))
    sel = np.ones(X.shape, bool) if near is None else np.asarray(near, bool)
    pts = shapely.points(X[sel], Y[sel])
    dist = shapely.distance(pts, mp.boundary)
    inside = shapely.contains_xy(mp, X[sel], Y[sel])
    out[sel] = np.where(inside, dist, -dist)
    return out


def mesh_field(F, origin, h, *, target_faces=None):
    """Marching cubes on a 3-D field (<0 inside), cleaned to one body.

    origin is the (x, y, z) of F[0, 0, 0]. Returns a trimesh.Trimesh with
    outward normals. Small decimation crumbs are dropped.
    """
    import trimesh
    from skimage import measure

    Fp = np.pad(np.asarray(F, np.float32), 1, constant_values=1.0)
    # A flat face that lands on a grid plane gives samples of (almost) exactly 0,
    # and marching cubes leaves a seam there. Nudge them just outside.
    Fp[np.abs(Fp) < 1e-6] = 1e-6
    v, f, _, _ = measure.marching_cubes(Fp, 0.0, spacing=(h, h, h))
    v += np.asarray(origin, float) - h
    m = _clean(trimesh.Trimesh(v, f, process=True))
    if target_faces and len(m.faces) > target_faces:
        import fast_simplification

        v2, f2 = fast_simplification.simplify(
            np.asarray(m.vertices, np.float32),
            np.asarray(m.faces, np.int32),
            1 - target_faces / len(m.faces),
        )
        m = _clean(trimesh.Trimesh(v2, f2, process=True))
    parts = m.split(only_watertight=False)
    if len(parts) > 1:
        m = max(parts, key=lambda p: len(p.faces))
    if m.volume < 0:
        m.invert()
    return m


def _clean(m):
    m.update_faces(m.nondegenerate_faces())
    m.merge_vertices()
    m.remove_unreferenced_vertices()
    return m


def print_orientation(mesh):
    """Flip about x (top face down) and sit the part on z = 0."""
    import trimesh

    mp = mesh.copy()
    mp.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    mp.apply_translation([0, 0, -mp.bounds[0][2]])
    return mp


def unsupported_area(F, zs, h, *, height, layer=0.2, max_deg=55.0):
    """Area each print layer adds outside the previous one, past max_deg.

    The part prints upside down: print height p is installed z = -p. Returns
    total and worst-layer area in mm^2, and a per-layer list. Bridges and
    flat overhangs show up here; a self-supporting part is ~0.
    """
    from scipy import ndimage

    zs = np.asarray(zs)
    tol = layer * np.tan(np.radians(max_deg)) + h
    prev = None
    per_layer = []
    for pz in np.arange(layer / 2, height, layer):
        M = F[:, :, int(np.argmin(np.abs(zs + pz)))] < 0
        if prev is not None:
            bad = M & (ndimage.distance_transform_edt(~prev) * h > tol)
            per_layer.append(float(bad.sum() * h * h))
        prev = M
    return {
        "total_mm2": round(sum(per_layer), 1),
        "worst_layer_mm2": round(max(per_layer, default=0.0), 2),
        "per_layer_mm2": [round(a, 2) for a in per_layer],
    }


def mesh_report(mesh):
    """Watertight, bodies, volume, extents of a mesh."""
    bodies = mesh.split(only_watertight=False)
    return {
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "bodies": int(len(bodies)),
        "volume_mm3": round(float(mesh.volume), 1),
        "extents": [round(float(e), 2) for e in mesh.extents],
    }
