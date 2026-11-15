#!/usr/bin/env python3
"""Rebuild the saved reference designs into out/ (a regression check for the generators)."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    for name in ("pebble-e", "smooth-v2"):
        print(f"==> hair-catcher {name}")
        sys.argv = [
            "generate.py",
            "--design",
            str(ROOT / f"models/hair-catcher/designs/{name}/design.json"),
            "-o",
            str(ROOT / f"out/hair-catcher-{name}"),
        ]
        runpy.run_path(str(ROOT / "models/hair-catcher/generate.py"), run_name="__main__")
    print("==> drybox-adapter v9")
    sys.argv = ["generate.py", "-P", "8.85", "-o", str(ROOT / "out/drybox-v9")]
    runpy.run_path(str(ROOT / "models/drybox-adapter/generate.py"), run_name="__main__")
    print("done")


if __name__ == "__main__":
    main()
