#!/usr/bin/env python3
"""Alias: run the bolted-bracket worked example."""
from pathlib import Path
import runpy
import sys

sys.exit(runpy.run_path(str(Path(__file__).with_name("worked_example.py")), run_name="__main__") or 0)
