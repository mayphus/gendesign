#!/usr/bin/env python3
"""Rebuild a saved hair-catcher design (design.json) as print files + stats.

    python models/hair-catcher/generate.py                                   # pebble-e
    python models/hair-catcher/generate.py --design models/hair-catcher/designs/smooth-v2/design.json
    python models/hair-catcher/generate.py --design .../iterations/00/picks/knee/params.json

method in design.json picks the builder:
  pebble-plate   model.py (the current generator; also a round pick's params.json)
  pebble-field   archive/pebble-field/build.py (two-level C and D)
  smooth         archive/methods/smooth_cad.py (CadQuery bowl, v2)
  generative     archive/methods/gen_grate.py (generative-v1 cone)
Never starts a print.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "archive"))
sys.path.insert(0, str(REPO))

DEFAULT_DESIGN = HERE / "designs" / "pebble-e" / "design.json"


def generate_from_design(design: dict, out: Path, preview=False, slice_print=False):
    method = design.get("method") or ("pebble-plate" if "spacing" in design else "smooth")
    out.mkdir(parents=True, exist_ok=True)
    if method == "pebble-plate":
        from model import MODEL, PebblePlate, PlateParams

        params = design.get("params", design)
        d = PebblePlate().build(PlateParams(**params))
        rep = MODEL.export(d, out, h=float(design.get("grid_mm", 0.1)),
                           target_faces=int(design.get("target_faces", 300_000)))
        MODEL.preview(d, out / "preview-top.png")
        lay = {k: v for k, v in d["layout"].items()}
        (out / "metrics.json").write_text(json.dumps(lay, indent=1))
        (out / "mesh.json").write_text(json.dumps(rep, indent=1))
        return {"installed": out / "installed.stl", "print": out / "print.stl"}, {"layout": lay, "mesh": rep}
    if method == "pebble-field":
        b = design["build"]
        cmd = [sys.executable, "build.py", str(b["seed"]), str(b["top_spacing"]), str(b["bot_spacing"]),
               str(out.resolve()), str(b.get("grid_mm", 0.08)), b.get("style", "D")]
        subprocess.run(cmd, cwd=HERE / "archive" / "pebble-field", check=True)
        return ({"installed": out / "installed.stl", "print": out / "print.stl"},
                {"metrics": json.loads((out / "metrics.json").read_text()),
                 "mesh": json.loads((out / "mesh.json").read_text())})
    if method in ("smooth", "smooth-v2", "bowl"):
        from methods.smooth_cad import generate, params_from_mapping

        params = params_from_mapping(design.get("params") or design)
        prefix = design.get("prefix") or "basin_guard_smooth"
        return generate(params=params, out_dir=out, prefix=prefix, preview=preview, slice_print=slice_print)
    if method in ("generative", "gen"):
        from methods.gen_grate import rebuild

        return rebuild(design, out, preview=preview)
    raise SystemExit(f"{method}: no rebuild here. deep-v3 and voronoi-a/b/c are records; see archive/README.md.")


def main():
    ap = argparse.ArgumentParser(description="Rebuild a saved hair-catcher design")
    ap.add_argument("--design", type=Path, default=DEFAULT_DESIGN, help="design.json or a round pick's params.json")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--slice", action="store_true", help="stand-in slice estimate; never starts a print")
    args = ap.parse_args()
    design = json.loads(args.design.read_text())
    if args.design.name == "params.json":
        design = {"method": "pebble-plate", "params": design}
    out = args.out or REPO / "out" / (design.get("name") or args.design.parent.name)
    files, report = generate_from_design(design, out, preview=args.preview, slice_print=args.slice)
    print("wrote", out)
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=1, default=str)[:1500])
    for k, v in files.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
