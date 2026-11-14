"""Mesh evaluation: volume/mass, open area, min feature, overhang, optional slicer time."""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path


def evaluate_mesh(
    mesh_or_path,
    density_g_cm3: float = 1.24,
    max_overhang_deg: float = 45.0,
    build_dir=(0, 0, 1),
    min_feature_mm: float | None = None,
):
    import trimesh
    import numpy as np

    mesh = trimesh.load(str(mesh_or_path)) if not hasattr(mesh_or_path, "vertices") else mesh_or_path
    vol = float(mesh.volume) if mesh.is_watertight else float(abs(mesh.volume))
    mass_g = vol * density_g_cm3 / 1000.0
    overhang = overhang_report(mesh, max_overhang_deg=max_overhang_deg, build_dir=build_dir)
    feat = min_feature(mesh) if min_feature_mm is not None or True else None
    return {
        "watertight": bool(mesh.is_watertight),
        "volume_mm3": vol,
        "mass_g_est": mass_g,
        "extents_mm": mesh.extents.tolist(),
        "bounds": mesh.bounds.tolist(),
        "faces": int(len(mesh.faces)),
        "min_feature_mm": feat,
        "overhang": overhang,
    }


def min_feature(mesh, pitch=0.2):
    """Cheap min-feature estimate: min of a voxel EDT inside the mesh AABB."""
    import numpy as np
    import trimesh
    from scipy.ndimage import distance_transform_edt

    extents = mesh.extents
    # cap voxel count
    n = np.clip(np.ceil(extents / pitch), 8, 80).astype(int)
    try:
        vox = mesh.voxelized(pitch=max(pitch, extents.max() / 80))
        mat = vox.matrix
    except Exception:
        return None
    if mat is None or mat.size == 0 or not mat.any():
        return None
    edt = distance_transform_edt(mat) * (vox.scale if np.isscalar(vox.scale) else np.mean(vox.scale))
    # solid thickness ~ 2 * max radius along a skeleton would be better;
    # report 2*min positive boundary radius as a conservative "thinnest wall"
    # Use interior voxels only
    interior = edt.copy()
    interior[mat == 0] = np.nan
    # thin regions: look at 10th percentile of 2*edt on the solid
    vals = 2 * edt[mat]
    vals = vals[vals > 0]
    if len(vals) == 0:
        return None
    return float(np.percentile(vals, 5))


def overhang_report(mesh, max_overhang_deg=45.0, build_dir=(0, 0, 1)):
    """Area whose face normal leans more than max_overhang_deg from the build axis
    *and* faces down (unsupported). 0° is a horizontal top; 90° is a vertical wall;
    0° downward is a floor over air.

    We report faces whose downward tilt from vertical exceeds max_overhang_deg,
    i.e. angle between face normal and +build_dir is greater than (90 + max).
    For printing, a face is an overhang if the angle between its normal and the
    build direction is > 90° + (90°-max_overhang) ... Standard: the face's
    outward normal dotted with build_dir; if the face looks downward, n·z < 0.
    Overhang angle from vertical is acos(clip(-n·z,0,1)) wait.

    A downward-facing face (n·z < 0) has overhang angle = angle between the
    face and the vertical, = angle between -n and z? Easier: angle of the face
    from the horizontal is asin(n·z) etc.

    We use: slope from vertical = angle between the face normal projected...
    Common slicer: overhang = 90° - angle(face, bed). A 45° cone has 45° overhang.

    Face angle from the horizontal = acos(n·build). A floor has n = -z, angle 180.
    Overhang angle from vertical = 90 - (angle from horizontal of the *underside*).
    We take faces with n·z < 0 and angle_from_vertical = degrees(acos(clip(-n·z,0,1))).
    A horizontal floor: -n·z = 1, angle = 0 from downward, 90 from vertical.
    A 45° underside: -n·z = cos(45)=0.707, angle_from_down = 45, from vertical = 45.
    Let's report angle from vertical for downward faces: 90 - degrees(acos(-n·z)).
    Horizontal floor: acos(1)=0, 90-0=90° from vertical (bad).
    45° cone underside: -n·z = cos(45), acos=45, 90-45=45° from vertical (on the limit).
    Vertical wall: n·z=0, not downward, skip (or 0).
    """
    import numpy as np

    n = mesh.face_normals
    z = np.asarray(build_dir, dtype=float)
    z = z / (np.linalg.norm(z) or 1)
    area = mesh.area_faces
    ndot = n @ z
    down = ndot < -1e-6
    # angle from vertical of the face (0 = vertical wall, 90 = floor over air)
    # for downward faces: ang = degrees(acos(clip(-ndot, 0, 1)))  ? 
    # n = (0,0,-1): -ndot=1, acos 0, that's from downward axis.
    ang_from_vertical = 90.0 - np.degrees(np.arccos(np.clip(-ndot, 0, 1)))
    # n=(0,0,-1): 90-0=90. n at 45° down: -ndot=0.707, acos=45, 90-45=45. Good.
    out = {}
    for lim in (45, 50, 60, 70, 80):
        m = down & (ang_from_vertical > lim)
        out[f">{lim}deg_mm2"] = float(area[m].sum())
    out["downward_mm2"] = float(area[down].sum())
    out["max_overhang_deg"] = max_overhang_deg
    out[f"over_limit_mm2"] = float(area[down & (ang_from_vertical > max_overhang_deg)].sum())
    return out


def open_area_fraction(mask_void, mask_domain):
    import numpy as np
    d = np.asarray(mask_domain)
    if d.sum() == 0:
        return 0.0
    return float((np.asarray(mask_void) & d).sum() / d.sum())


def slice_estimate(stl_path, ini_path=None, timeout=180):
    """Call PrusaSlicer if present; otherwise return None. Never sends a print."""
    exe = shutil.which("prusa-slicer") or shutil.which("prusa-slicer-console")
    if not exe:
        return None
    stl_path = Path(stl_path)
    gcode = stl_path.with_suffix(".gcode")
    cmd = [exe, "--export-gcode", "--output", str(gcode), str(stl_path)]
    if ini_path:
        cmd[1:1] = ["--load", str(ini_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode or not gcode.exists():
        return {"ok": False, "stderr": (r.stderr or "")[-1500:]}
    import re
    g = gcode.read_text(errors="ignore")

    def grab(pat, default=None):
        m = re.search(pat, g)
        return m.group(1) if m else default

    return {
        "ok": True,
        "filament_mm": grab(r"filament used \[mm\] = ([0-9.]+)"),
        "filament_g": grab(r"filament used \[g\] = ([0-9.]+)"),
        "filament_cm3": grab(r"filament used \[cm3\] = ([0-9.]+)"),
        "time": grab(r"estimated printing time \(normal mode\) = ([^\n]+)"),
        "layers": g.count(";LAYER_CHANGE"),
        "note": "Stand-in slicer estimate only. Nothing was sent to a printer.",
    }
