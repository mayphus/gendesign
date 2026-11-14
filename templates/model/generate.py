#!/usr/bin/env python3
"""Rebuild a saved design JSON to STL/STEP + stats."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", type=Path, required=False)
    ap.add_argument("-o", "--out", type=Path, default=Path("out/model"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    print("TODO: load", args.design, "and write files into", args.out)

if __name__ == "__main__":
    main()
