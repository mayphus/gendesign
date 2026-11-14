#!/usr/bin/env python3
"""Rebuild the v2-bowl vs v3-deep comparison chart from saved stats and previews."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The original script (methods/compare_v3.py) expected files next to it.
# Prefer the already-rendered chart in docs/ unless --rebuild is passed.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    chart = HERE / "docs" / "comparison-v2-vs-v3-deep.png"
    if not args.rebuild:
        if chart.exists():
            print(chart)
            return
        print("no saved chart; pass --rebuild if you have the original stats files", file=sys.stderr)
        sys.exit(1)
    print("Point methods/compare_v3.py at a directory that has smooth-stats.json,")
    print("v3-deep-stats.json and the preview PNGs, or use the saved docs chart.")
    print(chart if chart.exists() else "missing")


if __name__ == "__main__":
    main()
