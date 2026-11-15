#!/usr/bin/env python3
"""Build the v3 deep-basket winner as smooth CadQuery CAD (same methods as
build_smooth.py: revolve with true arcs, cut holes, fillet hole lips),
then measure, check, render and slice. Nothing is sent to a printer."""
from __future__ import annotations
import json, math, re, subprocess, sys
from pathlib import Path
import numpy as np
import cadquery as cq
import trimesh

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import deep_geom as D

RES = json.loads((OUT / "iterations_deep" / "search-result.json").read_text())
BALL = 8.6
# winner = best feasible design found at ball <= 8.6, depth <= 35 across the main
# run and the depth-sweep run with the same limits
_c = [RES["best86"]["genome"]] + [json.loads(s["genome"]) for s in RES["sweep"]
                                  if s["ball_limit"] == 8.6 and s["max_depth"] == 35.0 and s["feasible"]]
G = max(_c, key=lambda g: D.evaluate(dict(g), BALL, 35.0)[0]["score"])
M, L = D.evaluate(dict(G), BALL, 35.0)
P = L["P"]
STL_LINEAR, STL_ANGULAR = 0.03, 0.08
NAME = "basin_guard_v3_deep"


def fillet_pts(Vp, Vc, Vn, R):
    Vp, Vc, Vn = map(lambda v: np.asarray(v, float), (Vp, Vc, Vn))
    u1 = (Vp - Vc) / np.linalg.norm(Vp - Vc); u2 = (Vn - Vc) / np.linalg.norm(Vn - Vc)
    phi = 0.5 * math.acos(float(np.clip(np.dot(u1, u2), -1, 1)))
    d = R / math.tan(phi)
    w = (u1 + u2) / np.linalg.norm(u1 + u2)
    C = Vc + w * R / math.sin(phi)
    return Vc + u1 * d, C - w * R, Vc + u2 * d, d


def path(wp, verts, radii, start_move=True):
    """verts closed polygon; radii per vertex (0 = sharp). Returns wire wp."""
    n = len(verts)
    segs = []
    for i in range(n):
        if radii[i] > 0:
            T1, mid, T2, d = fillet_pts(verts[i - 1], verts[i], verts[(i + 1) % n], radii[i])
            segs.append(("arc", T1, mid, T2))
        else:
            segs.append(("pt", np.asarray(verts[i], float)))
    pts = [i for i, s in enumerate(segs) if s[0] == "pt"]
    k0 = pts[0] if pts else 0
    order = segs[k0:] + segs[:k0]
    first = order[0]
    if first[0] == "pt":
        wp = wp.moveTo(*first[1])
    else:
        wp = wp.moveTo(*first[1]).threePointArc(tuple(first[2]), tuple(first[3]))
    for s in order[1:]:
        if s[0] == "pt":
            wp = wp.lineTo(*s[1])
        else:
            wp = wp.lineTo(*s[1]).threePointArc(tuple(s[2]), tuple(s[3]))
    return wp.close()


def body_solid():
    verts = [(0.0, P["O5"][1]), P["O4"], P["O3"], P["O2"], P["O1"], (D.R_FLANGE, 0.0),
             (D.R_FLANGE, D.FLANGE_T), (D.R_IN, D.FLANGE_T), P["Ij"], P["I3"], P["I4"], (0.0, P["I5"][1])]
    radii = [0, D.F_JUNCTION, D.F_JUNCTION, 0, 0, 0, 0.6, D.F_JUNCTION, D.F_JUNCTION,
             D.F_JUNCTION, D.F_JUNCTION, 0]
    verts = [tuple(map(float, v)) for v in verts]
    wp = path(cq.Workplane("XZ"), verts, radii)
    return wp.revolve(360), verts, radii


def side_cutter(th, zc):
    a, b, gam, rc = G["a"], G["b"], G["gam"], G["rc"]
    r0 = D.r_inner_side(P, zc - b) - 1.2
    r1 = D.r_outer_side(P, zc + b) + 1.2
    er = (math.cos(th), math.sin(th), 0.0); et = (-math.sin(th), math.cos(th), 0.0)
    pl = cq.Plane(origin=(r0 * er[0], r0 * er[1], zc), xDir=et, normal=er)
    V = [tuple(v) for v in D.hole_vertices(a, b, gam)]
    wp = path(cq.Workplane(pl), V, [rc] * len(V))
    return wp.extrude(r1 - r0)


def floor_cutter(x, y, r):
    z0 = P["O5"][1] - 2.0
    return cq.Workplane("XY").transformed(offset=(x, y, z0)).circle(r).extrude(D.FLANGE_T + 2 - z0)


def lip_edges(body):
    out = []
    rf = G["d_f"] / 2
    for e in body.edges().vals():
        t = e.geomType()
        if t == "LINE":
            continue
        pts = [e.positionAt(s) for s in (0.0, 0.25, 0.5, 0.75, 1.0)]
        if all(abs(p.y) < 1e-5 for p in pts) and all(p.x >= -1e-6 for p in pts):
            continue  # revolve seam
        if t == "CIRCLE":
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            c = BRepAdaptor_Curve(e.wrapped).Circle()
            loc = c.Location()
            if math.hypot(loc.X(), loc.Y()) < 1e-4 and abs(c.Radius() - rf) > 0.05:
                continue  # revolve ring edges (fillet tangents, flange, collar)
        out.append(e)
    return out


def fillet_lips(body, R):
    edges = lip_edges(body)
    print("lip edges", len(edges))
    class Sel(cq.Selector):
        def __init__(self, es): self.ids = {e.hashCode() for e in es}
        def filter(self, ol): return [o for o in ol if o.hashCode() in self.ids]
    for rr in (R, 0.5, 0.4):
        try:
            b2 = body.edges(Sel(edges)).fillet(rr)
            print(f"filleted {len(edges)} lip edges at R={rr} in one op")
            return b2, len(edges), rr
        except Exception as ex:
            print("batch fillet failed at", rr, ex)
    return body, 0, 0.0


def export(body):
    f = {}
    f["use_step"] = OUT / f"{NAME}-use.step"; f["use_stl"] = OUT / f"{NAME}-use.stl"
    f["print_step"] = OUT / f"{NAME}-print.step"; f["print_stl"] = OUT / f"{NAME}-print.stl"
    cq.exporters.export(body, str(f["use_step"]))
    cq.exporters.export(body, str(f["use_stl"]), tolerance=STL_LINEAR, angularTolerance=STL_ANGULAR)
    bp = body.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, D.FLANGE_T))
    bb = bp.val().BoundingBox()
    if abs(bb.zmin) > 1e-4:
        bp = bp.translate((0, 0, -bb.zmin))
    cq.exporters.export(bp, str(f["print_step"]))
    cq.exporters.export(bp, str(f["print_stl"]), tolerance=STL_LINEAR, angularTolerance=STL_ANGULAR)
    return f


def overhang_report(stl):
    tm = trimesh.load(str(stl))
    n = tm.face_normals; a = tm.area_faces; c = tm.triangles_center
    ang = np.degrees(np.arcsin(np.clip(-n[:, 2], 0, 1)))  # 0 vertical wall, 90 flat ceiling
    mask = (n[:, 2] < -1e-3) & (c[:, 2] > 0.05)
    rep = {}
    for th in (45, 50, 60, 70, 80):
        m = mask & (ang > th + 0.5)
        rep[f">{th}deg_mm2"] = round(float(a[m].sum()), 1)
    return rep


def ball_check(stl, pipe_id=D.PIPE_ID, pitch=0.2, label=""):
    """3-D check: largest sphere that can travel from the basin (above the
    flange) to below the part, through the part only (drain modelled as
    Ø35.2 bore to 10.21 mm, then Ø32 pipe)."""
    from scipy.ndimage import distance_transform_edt, label as lab
    tm = trimesh.load(str(stl))
    lo = np.array([-25.0, -25.0, tm.bounds[0][2] - 4.0]); hi = np.array([25.0, 25.0, 8.0])
    n = np.ceil((hi - lo) / pitch).astype(int)
    vg = tm.voxelized(pitch).fill()
    solid = np.zeros(n, bool)
    idx = np.floor((vg.points - lo) / pitch + 0.5).astype(int)
    ok = np.all((idx >= 0) & (idx < n), axis=1)
    idx = idx[ok]
    solid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    xs = lo[0] + np.arange(n[0]) * pitch; ys = lo[1] + np.arange(n[1]) * pitch; zs = lo[2] + np.arange(n[2]) * pitch
    X, Y = np.meshgrid(xs, ys, indexing="ij"); Rr = np.hypot(X, Y)
    for k, z in enumerate(zs):
        if z < 0:
            lim = D.R_LOC + 0.02 if z >= -D.KNOWN_BORE_DEPTH else pipe_id / 2
            solid[:, :, k] |= Rr > lim
        elif z < D.FLANGE_T:
            solid[:, :, k] |= Rr > 24.2
    edt = distance_transform_edt(~solid) * pitch
    src_k = zs > 5.0; snk_k = zs < tm.bounds[0][2] - 1.5
    lo_d, hi_d = 2.0, 16.0
    for _ in range(14):
        d = 0.5 * (lo_d + hi_d)
        free = edt >= d / 2
        lb, _ = lab(free)
        s = set(np.unique(lb[:, :, src_k])) - {0}; t = set(np.unique(lb[:, :, snk_k])) - {0}
        if s & t:
            lo_d = d
        else:
            hi_d = d
    print(f"ball check {label}: passes {lo_d:.2f}, blocked {hi_d:.2f} (voxel {pitch} mm)")
    return round(lo_d, 2), round(hi_d, 2)


def slice_stl(stl, tag):
    ini = OUT / "slicer-a1mini-pla-basic.ini"
    gcode = OUT / f"{NAME}-print.gcode"
    r = subprocess.run(["prusa-slicer", "--load", str(ini), "--export-gcode", "--output", str(gcode), str(stl)],
                       capture_output=True, text=True, timeout=300)
    g = gcode.read_text(errors="ignore") if gcode.exists() else ""
    grab = lambda p: (re.search(p, g).group(1) if re.search(p, g) else "—")
    res = dict(filament_mm=grab(r"; filament used \[mm\] = ([0-9.]+)"), filament_g=grab(r"; filament used \[g\] = ([0-9.]+)"),
               filament_cm3=grab(r"; filament used \[cm3\] = ([0-9.]+)"),
               time=grab(r"; estimated printing time \(normal mode\) = ([^\n]+)"),
               layers=g.count(";LAYER_CHANGE"), support_lines=g.count(";TYPE:Support material"),
               exit=r.returncode)
    text = ("Basin guard v3 DEEP — slice estimate\n====================================\n"
            "Slicer:    PrusaSlicer 2.9.2 CLI — STAND-IN for OrcaSlicer / Bambu Studio\n"
            "Profile:   slicer-a1mini-pla-basic.ini (A1 mini, PLA Basic, 0.20 mm, 4 walls, 20% gyroid, no supports, no brim)\n"
            f"File:      {stl.name}  (flange top on the bed, basket grows upward)\n\n"
            f"  filament: {float(res['filament_mm'])/1000:.3f} m / {res['filament_cm3']} cm3 / {res['filament_g']} g\n"
            f"  time:     {res['time']} (normal mode)\n  layers:   {res['layers']}\n"
            f"  support material lines in G-code: {res['support_lines']} (support_material = 0)\n"
            "  Nothing was sent to the printer.\n")
    (OUT / "slice-report-v3-deep.txt").write_text(text)
    print(text)
    return res


def render(tm_use, files):
    import pyvista as pv
    pv.OFF_SCREEN = True
    mesh = pv.wrap(tm_use).compute_normals(split_vertices=True, feature_angle=30)
    PART = dict(color="#E6E3DC", specular=0.55, specular_power=50, ambient=0.10, diffuse=0.72, smooth_shading=True)

    def plotter():
        p = pv.Plotter(off_screen=True, window_size=(1800, 1350), lighting="none")
        p.set_background("#ECE8E1", top="#FBFAF8")
        p.add_light(pv.Light(position=(70, -90, 160), focal_point=(0, 0, 0), intensity=0.95))
        p.add_light(pv.Light(position=(-120, 40, 80), focal_point=(0, 0, 0), intensity=0.45))
        p.add_light(pv.Light(position=(40, 80, -60), focal_point=(0, 0, -10), intensity=0.30))
        p.add_light(pv.Light(light_type="headlight", intensity=0.28))
        p.enable_anti_aliasing("ssaa")
        return p

    # 3/4 view: part alone (basket is hidden once installed)
    p = plotter(); p.add_mesh(mesh, **PART)
    p.camera_position = [(62, -88, 38), (0, 0, -14), (0, 0, 1)]
    p.screenshot(str(files["preview_34"])); p.close()
    # top view installed in the basin (as in v2 previews)
    p = plotter()
    ceramic = pv.Disc(inner=24.2, outer=70, c_res=240).translate((0, 0, D.FLANGE_T))
    p.add_mesh(ceramic.triangulate(), color="#CBC6BC", specular=0.4, ambient=0.25)
    bore = pv.Cylinder(center=(0, 0, -25), direction=(0, 0, 1), radius=17.85, height=50, resolution=240, capping=False)
    p.add_mesh(bore.triangulate(), color="#4A4E54", ambient=0.2)
    p.add_mesh(mesh, **PART)
    p.camera_position = [(0, 0, 120), (0, 0, 0), (0, 1, 0)]
    p.screenshot(str(files["preview_top"])); p.close()
    # section: half cut through the part + assumed drain
    half = mesh.clip(normal=(0, 1, 0), origin=(0, 0, 0), invert=False)
    p = plotter()
    p.add_mesh(half, **PART)
    # cap color for section: slice outline
    sec = mesh.slice(normal=(0, 1, 0), origin=(0, 0, 0))
    p.add_mesh(sec, color="#B5562B", line_width=4)
    # assumed drain wall (cut)
    zmin = float(tm_use.bounds[0][2]) - 6
    for r_in, z0, z1 in ((D.R_LOC + 0.02, -D.KNOWN_BORE_DEPTH, 0.0), (D.PIPE_ID / 2, zmin, -D.KNOWN_BORE_DEPTH)):
        tube = pv.Cylinder(center=(0, 0, (z0 + z1) / 2), direction=(0, 0, 1), radius=r_in, height=z1 - z0,
                           resolution=240, capping=False).clip(normal=(0, 1, 0), origin=(0, 0, 0), invert=False)
        p.add_mesh(tube, color="#9AA3AD", opacity=0.35)
    p.camera_position = [(0, -120, -10), (0, 0, -14), (0, 0, 1)]
    p.screenshot(str(files["preview_section"])); p.close()


def main():
    body, verts, radii = body_solid()
    side = L["side"]
    N = G["N"]
    # rotate side holes half a pitch so none sits on the revolve seam
    side = [(th + math.pi / N, zc) for th, zc in side]
    cutters = [side_cutter(th, zc) for th, zc in side] + [floor_cutter(*h) for h in L["floor"]]
    tool = cutters[0]
    for c in cutters[1:]:
        tool = tool.union(c)
    body = body.cut(tool)
    print("holes cut:", len(side), "side,", len(L["floor"]), "floor")
    body, nlip, rlip = fillet_lips(body, D.F_LIP)
    files = export(body)
    files.update(preview_34=OUT / "preview-34-v3-deep.png", preview_top=OUT / "preview-top-v3-deep.png",
                 preview_section=OUT / "preview-section-v3-deep.png")
    tm = trimesh.load(str(files["use_stl"]))
    vol = float(tm.volume)
    print("mesh watertight", tm.is_watertight, "volume", vol, "bounds", tm.bounds.tolist())
    oh = overhang_report(files["print_stl"])
    oh_v2 = overhang_report(OUT / "basin_guard_v2_smooth-print.stl")
    print("overhang v3", oh, "v2", oh_v2)
    ball = ball_check(files["use_stl"], label="v3")
    ball_v2 = ball_check(OUT / "basin_guard_v2_smooth-use.stl", label="v2")
    render(tm, files)
    sl = slice_stl(files["print_stl"], "v3")
    rep = dict(genome=G, metrics=M, lip_edges_filleted=nlip, lip_radius=rlip,
               fillets=dict(junctions=D.F_JUNCTION, flange_top_outer=0.6, hole_lips=rlip,
                            side_hole_corners=G["rc"], lead_in="0.7 mm 45° start of the shoulder cone (sharp)",
                            flange_seat="flat"),
               mesh=dict(watertight=bool(tm.is_watertight), volume_mm3=round(vol, 1),
                         mass_solid_g=round(vol * D.PLA_DENS, 2), bounds=tm.bounds.tolist()),
               overhang_print=oh, overhang_print_v2=oh_v2, ball_3d=ball, ball_3d_v2=ball_v2, slice=sl,
               side_holes_rotated_half_pitch=True,
               files={k: str(v) for k, v in files.items()})
    (OUT / "v3-deep-stats.json").write_text(json.dumps(rep, indent=2, default=float))
    print(json.dumps({k: rep[k] for k in ("mesh", "overhang_print", "ball_3d", "ball_3d_v2", "slice", "lip_edges_filleted")}, indent=1, default=float))


if __name__ == "__main__":
    main()
