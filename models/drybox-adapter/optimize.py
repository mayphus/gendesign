#!/usr/bin/env python3
"""Pocket-size sweep for the drybox adapter.

This part is a fit/tolerance problem, not a topology problem: sweep P,
rebuild, record volume, and (when you have the physical insert) test-fit.
Account for printed holes coming out ~0.1–0.2 mm undersized.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from generate import Params, generate  # noqa: E402

# Recommended trial pockets around a measured insert of ~8.7 mm:
# a drawn 8.7 mm pocket will usually be tight; 8.85 was the working pick.
DEFAULT_SWEEP = [8.6, 8.7, 8.75, 8.8, 8.85, 8.9, 9.0]


def main():
    ap = argparse.ArgumentParser(description="Sweep drybox adapter pocket sizes")
    ap.add_argument("--pockets", type=float, nargs="*", default=DEFAULT_SWEEP)
    ap.add_argument("-o", "--out", default="out/drybox-sweep")
    ap.add_argument("--quick", action="store_true", help="only 8.75, 8.85, 8.95")
    args = ap.parse_args()
    pockets = [8.75, 8.85, 8.95] if args.quick else args.pockets
    out = Path(args.out)
    rows = []
    for P in pockets:
        files, stats = generate(Params(pocket=P), out_dir=out)
        rows.append(stats)
    (out / "sweep.json").write_text(json.dumps(rows, indent=2))
    print("wrote", out / "sweep.json")
    print("Test-fit the printed parts on the real insert. Nothing was sent to a printer.")


if __name__ == "__main__":
    main()
