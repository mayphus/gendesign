#!/usr/bin/env python3
"""Rebuild every model's default saved design into out/."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    print("==> hair-catcher smooth-v2")
    sys.argv = [
        "generate.py",
        "--design",
        str(ROOT / "models/hair-catcher/designs/smooth-v2/design.json"),
        "-o",
        str(ROOT / "out/hair-catcher-smooth-v2"),
    ]
    runpy.run_path(str(ROOT / "models/hair-catcher/generate.py"), run_name="__main__")
    print("==> drybox-adapter v9")
    sys.argv = ["generate.py", "-P", "8.85", "-o", str(ROOT / "out/drybox-v9")]
    runpy.run_path(str(ROOT / "models/drybox-adapter/generate.py"), run_name="__main__")
    print("done")


if __name__ == "__main__":
    main()
