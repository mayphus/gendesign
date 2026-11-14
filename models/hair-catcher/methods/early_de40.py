#!/usr/bin/env python3
"""
Washbasin hair catcher for a Chinese De40 / DN40 PVC-U waste (GB/T 5836.1-2018).

Sized for a measured open-hole inner diameter of about 35 mm (typical De40
ID is 35–36 mm). Original design — not a copy of a commercial STL.

Print orientation in the exported STL: visible flange top on the bed (Z=0),
basket pointing +Z. Flip over to install (basket drops into the waste,
flange lip sits on the rim). No supports required.

All dimensions are millimetres. Edit the parameters below and re-run:
    python3 catcher_de40.py
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq

# ---------------------------------------------------------------------------
# Parametric dimensions (mm)
# ---------------------------------------------------------------------------

# Fit — De40 washbasin waste
HOLE_ID_DESIGN = 36.0          # design to the larger of the 35–36 mm range
BODY_OD_TOP = 34.3             # rim-entry OD; 0.7–1.7 mm diametral clearance
BODY_OD_BOT = 33.6             # slight draft so it seats easily, not sloppy
ENTRY_CHAMFER = 0.7            # 45° at the seat-to-body junction
INSERT_CHAMFER = 1.2           # 45° lead-in at the basket bottom
FLANGE_OD = 46.0               # ASSUMED seat — not measured; see README
FLANGE_THICK = 2.0
FLANGE_TOP_CHAMFER = 0.4       # outer edge of the visible top face
FLANGE_SEAT_OUTER_CHAMFER = 0.3

# Walls / floor — slightly sturdy for PLA in a wet drain
WALL = 1.6
FLOOR = 1.6
INNER_DEPTH = 18.0             # from seating face down to inner floor

# Drainage slots — catch hair, don't choke the bore
SLOT_WIDTH = 1.8
FLOOR_SLOT_COUNT = 16
FLOOR_HUB_OD = 12.0            # solid centre for the lift rib
FLOOR_SLOT_OUTER_CLEAR = 1.6   # keep a rim of floor next to the wall
WALL_SLOT_COUNT = 12
WALL_SLOT_HEIGHT = 9.0
WALL_SLOT_ABOVE_FLOOR = 3.5    # solid cup so hair stays in the basket

# Lift rib with a U-shaped finger notch open at the flange top
# (no enclosed bridge — prints without supports). Flush with the rim.
RIB_THICK = 2.4
NOTCH_WIDTH = 13.0
NOTCH_DEPTH = 12.0             # from flange top down into the basket

# Tessellation
STL_LINEAR_DEFLECTION = 0.02
STL_ANGULAR_DEFLECTION = 0.08

OUT_DIR = Path(__file__).resolve().parent


def _r_outer_between(z: float, z_a: float, r_a: float, z_b: float, r_b: float) -> float:
    t = 0.0 if z_b == z_a else (z - z_a) / (z_b - z_a)
    return r_a * (1.0 - t) + r_b * t


def build() -> cq.Workplane:
    """Build the catcher in print orientation: flange top at Z=0, basket +Z."""
    # Print Z:
    #   0                  visible flange top (on the bed)
    #   FLANGE_THICK       seating face (sits on the waste rim after flipping)
    #   FLANGE_THICK + INNER_DEPTH
    #                      inner floor
    #   + FLOOR            outer bottom
    z_top = 0.0
    z_seat = FLANGE_THICK
    z_floor = z_seat + INNER_DEPTH
    z_bottom = z_floor + FLOOR

    body_top_r = BODY_OD_TOP / 2.0
    body_bot_r = BODY_OD_BOT / 2.0
    inner_top_r = body_top_r - WALL
    inner_bot_r = body_bot_r - WALL
    flange_r = FLANGE_OD / 2.0

    # Body outer wall runs from just below the entry chamfer to the insert chamfer.
    z_after_entry = z_seat + ENTRY_CHAMFER
    r_after_entry = body_top_r  # full 34.3 mm after the chamfer
    # At the seating plane the body starts a little smaller so it drops in easily.
    r_at_seat = body_top_r - ENTRY_CHAMFER

    z_before_insert = z_bottom - INSERT_CHAMFER
    r_insert = body_bot_r - INSERT_CHAMFER
    if r_insert < inner_bot_r + 0.4:
        r_insert = inner_bot_r + 0.4

    # Taper the outer wall from r_after_entry at z_after_entry to body_bot_r
    # at z_before_insert.
    r_before_insert = _r_outer_between(
        z_before_insert, z_after_entry, r_after_entry, z_bottom, body_bot_r
    )
    # Use body_bot_r at z_before_insert (the intended draft end).
    r_before_insert = body_bot_r

    # Exterior profile (XZ, +X = radius), closed back to the axis.
    # Seating face is the horizontal run at z_seat from flange OD in to r_at_seat.
    outer_pts = [
        (0.0, z_top),
        (flange_r - FLANGE_TOP_CHAMFER, z_top),
        (flange_r, z_top + FLANGE_TOP_CHAMFER),
        (flange_r, z_seat - FLANGE_SEAT_OUTER_CHAMFER),
        (flange_r - FLANGE_SEAT_OUTER_CHAMFER, z_seat),
        (r_at_seat, z_seat),
        (r_after_entry, z_after_entry),
        (r_before_insert, z_before_insert),
        (r_insert, z_bottom),
        (0.0, z_bottom),
    ]

    body = (
        cq.Workplane("XZ")
        .polyline(outer_pts)
        .close()
        .revolve(360)
    )

    # Inner cavity, open at the flange top, tapered, stops at the inner floor.
    # A small chamfer at the visible opening so the lip isn't sharp.
    opening_chamfer = 0.6
    cav_pts = [
        (0.0, z_top),
        (inner_top_r - opening_chamfer, z_top),
        (inner_top_r, z_top + opening_chamfer),
        (inner_bot_r, z_floor),
        (0.0, z_floor),
    ]
    cavity = (
        cq.Workplane("XZ")
        .polyline(cav_pts)
        .close()
        .revolve(360)
    )
    body = body.cut(cavity)

    # --- Floor slots (radial). Offset by half a pitch so they miss the lift rib. ---
    slot_inner_r = FLOOR_HUB_OD / 2.0
    slot_outer_r = inner_bot_r - FLOOR_SLOT_OUTER_CLEAR
    slot_len = slot_outer_r - slot_inner_r
    slot_mid_r = 0.5 * (slot_inner_r + slot_outer_r)
    floor_pitch = 360.0 / FLOOR_SLOT_COUNT
    slot_solid = (
        cq.Workplane("XY")
        .workplane(offset=z_floor - 0.15)
        .transformed(rotate=(0, 0, floor_pitch / 2.0))
        .center(slot_mid_r, 0)
        .rect(slot_len, SLOT_WIDTH)
        .extrude(FLOOR + 0.5)
    )
    floor_cutters = slot_solid
    for i in range(1, FLOOR_SLOT_COUNT):
        floor_cutters = floor_cutters.union(
            slot_solid.rotate((0, 0, 0), (0, 0, 1), i * floor_pitch)
        )
    body = body.cut(floor_cutters)

    # --- Wall slots. Offset so they miss the lift rib at 0° and 180°. ---
    slot_z1 = z_floor - WALL_SLOT_ABOVE_FLOOR
    slot_z0 = slot_z1 - WALL_SLOT_HEIGHT
    mid_z = 0.5 * (slot_z0 + slot_z1)
    mid_outer_r = _r_outer_between(
        mid_z, z_after_entry, r_after_entry, z_before_insert, r_before_insert
    )
    wall_pitch = 360.0 / WALL_SLOT_COUNT
    wall_slot = (
        cq.Workplane("XY")
        .workplane(offset=slot_z0)
        .transformed(rotate=(0, 0, wall_pitch / 2.0))
        .center(mid_outer_r, 0)
        .rect(WALL + 3.0, SLOT_WIDTH)
        .extrude(WALL_SLOT_HEIGHT)
    )
    wall_cutters = wall_slot
    for i in range(1, WALL_SLOT_COUNT):
        wall_cutters = wall_cutters.union(
            wall_slot.rotate((0, 0, 0), (0, 0, 1), i * wall_pitch)
        )
    body = body.cut(wall_cutters)

    # --- Lift rib with finger hole, flush with the flange top. ---
    rib_half = inner_top_r + 0.5  # slightly into the wall so it fuses
    rib = (
        cq.Workplane("XY")
        .workplane(offset=z_top)
        .rect(rib_half * 2, RIB_THICK)
        .extrude(z_floor + 0.05)
    )
    body = body.union(rib)
    # U-notch open at the flange top (print Z=0): straight sides plus a
    # semicircular bottom, cut after the fuse so the solid stays valid.
    # No enclosed bridge — prints without supports.
    z_arc = NOTCH_DEPTH - NOTCH_WIDTH / 2.0
    notch_box = (
        cq.Workplane("XY")
        .workplane(offset=-0.8)
        .rect(NOTCH_WIDTH, RIB_THICK + 3.0)
        .extrude(z_arc + 0.8)
    )
    notch_cyl = (
        cq.Workplane("XZ")
        .workplane(offset=-(RIB_THICK + 1.5))
        .center(0, z_arc)
        .circle(NOTCH_WIDTH / 2.0)
        .extrude((RIB_THICK + 1.5) * 2)
    )
    body = body.cut(notch_box.union(notch_cyl))

    return body


def export(body: cq.Workplane) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stl_path = OUT_DIR / "catcher-de40.stl"
    step_path = OUT_DIR / "catcher-de40.step"
    cq.exporters.export(
        body,
        str(stl_path),
        tolerance=STL_LINEAR_DEFLECTION,
        angularTolerance=STL_ANGULAR_DEFLECTION,
    )
    cq.exporters.export(body, str(step_path))
    return {"stl": stl_path, "step": step_path}


def dimensions() -> dict:
    z_seat = FLANGE_THICK
    z_floor = z_seat + INNER_DEPTH
    z_bottom = z_floor + FLOOR
    return {
        "hole_id_design_mm": HOLE_ID_DESIGN,
        "body_od_top_mm": BODY_OD_TOP,
        "body_od_bot_mm": BODY_OD_BOT,
        "entry_chamfer_mm": ENTRY_CHAMFER,
        "flange_od_mm": FLANGE_OD,
        "flange_thick_mm": FLANGE_THICK,
        "wall_mm": WALL,
        "floor_mm": FLOOR,
        "inner_depth_mm": INNER_DEPTH,
        "overall_height_mm": z_bottom,
        "seating_face_z_print_mm": z_seat,
        "insert_chamfer_mm": INSERT_CHAMFER,
        "slot_width_mm": SLOT_WIDTH,
        "floor_slot_count": FLOOR_SLOT_COUNT,
        "wall_slot_count": WALL_SLOT_COUNT,
        "wall_slot_height_mm": WALL_SLOT_HEIGHT,
        "notch_width_mm": NOTCH_WIDTH,
        "notch_depth_mm": NOTCH_DEPTH,
        "rib_thick_mm": RIB_THICK,
        "clearance_diametral_to_36_mm": round(HOLE_ID_DESIGN - BODY_OD_TOP, 2),
        "clearance_diametral_to_35_mm": round(35.0 - BODY_OD_TOP, 2),
    }


def main() -> None:
    body = build()
    paths = export(body)
    dims = dimensions()
    shp = body.val()
    bb = shp.BoundingBox()
    print("Exported:")
    for k, p in paths.items():
        print(f"  {k}: {p}  ({p.stat().st_size} bytes)")
    print(
        "Bounding box (mm): "
        f"X {bb.xmin:.3f}..{bb.xmax:.3f} ({bb.xlen:.3f})  "
        f"Y {bb.ymin:.3f}..{bb.ymax:.3f} ({bb.ylen:.3f})  "
        f"Z {bb.zmin:.3f}..{bb.zmax:.3f} ({bb.zlen:.3f})"
    )
    print("Dimensions:")
    for k, v in dims.items():
        print(f"  {k}: {v}")
    vol = shp.Volume()
    grams = vol / 1000.0 * 1.24
    print(f"Solid volume: {vol:.0f} mm^3  (~{grams:.2f} g at 1.24 g/cm3, pre-slice)")
    print(f"Valid: {shp.isValid()}  Closed: {shp.isClosed() if hasattr(shp, 'isClosed') else 'n/a'}")


if __name__ == "__main__":
    main()
