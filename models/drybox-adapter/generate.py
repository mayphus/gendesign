#!/usr/bin/env python3
"""PTFE bowden-insert pocket that presses into a dryer-wall grommet.

Default pocket size P=8.85 mm (v9). Printed holes come out about 0.1–0.2 mm
undersized — measure the pin and test-fit; do not assume a drawn 8.7 mm
pocket will accept an 8.7 mm insert.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import cadquery as cq


@dataclass
class Params:
    pocket: float = 8.85  # P, mm
    seat_extra: float = 2.3
    wall: float = 2.3
    stem: float = 4.7
    top: float = 10.6
    through_id: float = 2.6  # 1.3 radius * 2
    stl_linear: float = 0.01
    stl_angular: float = 0.1


def build(params: Params | None = None):
    p = params or Params()
    P, W, STEM, top = p.pocket, p.wall, p.stem, p.top
    pts = [(11.0, 0.55), (10.5, 1.55), (8.6, 2.5), (7.4, 4.2), (6.95, 7.0),
           (6.85, 9.4), (6.55, 10.3), (6.0, 10.6)]
    body = (
        cq.Workplane("XZ")
        .moveTo(0, 0).lineTo(11.0, 0)
        .spline(pts, includeCurrent=True)
        .lineTo(0, top).close()
        .revolve(360, (0, 0, 0), (0, 1, 0))
    )
    rs = STEM / 2
    stemp = (
        cq.Workplane("XZ")
        .moveTo(0, -W - 1.4).lineTo(rs - 0.35, -W - 1.4)
        .spline([(rs - 0.05, -W - 1.3), (rs + 0.05, -W - 1.05)], includeCurrent=True)
        .lineTo(rs + 0.25, -W - 0.7)
        .spline([(rs + 0.35, -W - 0.5), (rs + 0.3, -W - 0.25)], includeCurrent=True)
        .spline([(rs + 0.12, -W - 0.05), (rs, -W + 0.25)], includeCurrent=True)
        .lineTo(rs, 0.5).lineTo(0, 0.5).close()
        .revolve(360, (0, 0, 0), (0, 1, 0))
    )
    body = body.union(stemp)
    body = body.cut(cq.Workplane("XY").workplane(offset=-W - 1.5).rect(0.8, STEM + 2).extrude(W + 0.9))
    body = body.cut(cq.Workplane("XY").workplane(offset=-10).circle(p.through_id / 2).extrude(40))
    R = P / 2
    S = (P + p.seat_extra) / 2
    zt = top - 7.4
    zc = top - 6.6 - (R - 2.1)
    zb = top - 6.6
    cav = (
        cq.Workplane("XZ").moveTo(0, zc).lineTo(1.8, zc)
        .spline([(2.15, zc + 0.1), (2.45, zc + 0.35)], includeCurrent=True)
        .lineTo(R - 0.6, zb - 0.6)
        .spline([(R - 0.12, zb - 0.05), (R, zb + 0.5)], includeCurrent=True)
        .lineTo(R, top - 1.3)
        .spline([(S, top - 0.75), (S + 0.35, top - 0.2), (S + 0.9, top + 0.01)], includeCurrent=True)
        .lineTo(S + 0.9, top + 1).lineTo(0, top + 1).close()
        .revolve(360, (0, 0, 0), (0, 1, 0))
    )
    body = body.cut(cav)
    try:
        body = body.faces(">Z").edges().fillet(0.25)
    except Exception as e:
        print("fillet skip", e)
    return body, p


def generate(params: Params | None = None, out_dir="out/drybox", prefix=None):
    body, p = build(params)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = prefix or f"drybox_adapter_v9_{p.pocket:g}"
    stl = out / f"{prefix}.stl"
    step = out / f"{prefix}.step"
    cq.exporters.export(body, str(stl), tolerance=p.stl_linear, angularTolerance=p.stl_angular)
    cq.exporters.export(body, str(step))
    vol = round(float(body.val().Volume()), 1)
    stats = dict(params=asdict(p), volume_mm3=vol, pocket_mm=p.pocket,
                 note="Printed holes come out ~0.1–0.2 mm undersized. Measure and test-fit.")
    (out / f"{prefix}-stats.json").write_text(json.dumps(stats, indent=2))
    print(prefix, "vol", vol, "->", stl)
    return {"stl": str(stl), "step": str(step)}, stats


def main():
    ap = argparse.ArgumentParser(description="Generate the drybox PTFE-insert adapter (v9)")
    ap.add_argument("-P", "--pocket", type=float, default=8.85, help="pocket diameter in mm (default 8.85)")
    ap.add_argument("-o", "--out", default="out/drybox")
    args = ap.parse_args()
    generate(Params(pocket=args.pocket), out_dir=args.out)


if __name__ == "__main__":
    main()
