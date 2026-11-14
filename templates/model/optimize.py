#!/usr/bin/env python3
"""Search from requirements.yaml; record iterations under designs/<name>/."""
from __future__ import annotations
import argparse
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requirements", type=Path, default=Path(__file__).parent / "requirements.yaml")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("-o", "--out", type=Path, default=Path("out/search"))
    args = ap.parse_args()
    print("TODO: search from", args.requirements, "quick=", args.quick, "->", args.out)

if __name__ == "__main__":
    main()
