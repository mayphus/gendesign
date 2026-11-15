#!/usr/bin/env python3
"""Reproduce a saved hair-catcher design (JSON) as STL + STEP + stats."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

DEFAULT_DESIGN = HERE / "designs" / "smooth-v2" / "design.json"


def load_design(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def generate_from_design(design: dict, out: Path, preview=False, slice_print=False):
    method = design.get("method") or design.get("kind") or "smooth"
    out.mkdir(parents=True, exist_ok=True)
    if method in ("smooth", "smooth-v2", "bowl"):
        from methods.smooth_cad import generate, params_from_mapping, Params

        src = design.get("params") or design
        params = params_from_mapping(src)
        prefix = design.get("prefix") or "basin_guard_smooth"
        return generate(params=params, out_dir=out, prefix=prefix, preview=preview, slice_print=slice_print)
    if method in ("generative", "gen"):
        from methods.gen_grate import rebuild

        return rebuild(design, out, preview=preview)
    if method in ("deep", "deep-v3"):
        # The deep builder is a script with a fixed genome; we write the genome
        # next to the output and invoke the CAD build after injecting it.
        raise SystemExit(
            "deep-v3 CAD replay is wired through methods/deep_build.py; "
            "use: python optimize.py --method deep --from-design "
            f"{design.get('name', 'deep-v3')}  (or open methods/deep_build.py). "
            "The default command reproduces the smooth v2 winner."
        )
    raise SystemExit(f"unknown design method: {method}")


def main():
    ap = argparse.ArgumentParser(description="Generate a hair-catcher from a saved design JSON")
    ap.add_argument("--design", type=Path, default=DEFAULT_DESIGN, help="designs/<name>/design.json")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--slice", action="store_true", help="stand-in slice estimate; never starts a print")
    args = ap.parse_args()
    design = load_design(args.design)
    out = args.out or Path("out") / (design.get("name") or args.design.parent.name)
    files, report = generate_from_design(design, out, preview=args.preview, slice_print=args.slice)
    m = report["measure"]
    print("wrote", out)
    print(
        f"max_ball={m['max_sphere_mm']} mm  strut={m['min_strut_mm']} mm  "
        f"open={m['open_area_pct']}%  volume={m.get('volume_mm3')} mm3"
    )
    for k, v in files.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
