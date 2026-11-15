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
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))
from generate import Params, generate  # noqa: E402
from gendesign.process import Evaluator, Generator, run as process_run  # noqa: E402
from gendesign.requirements import load_requirements  # noqa: E402

# Recommended trial pockets around a measured insert of ~8.7 mm:
# a drawn 8.7 mm pocket will usually be tight; 8.85 was the working pick.
DEFAULT_SWEEP = [8.6, 8.7, 8.75, 8.8, 8.85, 8.9, 9.0]


class PocketGenerator(Generator):
    name = "pocket"

    def bounds(self):
        return [(8.6, 9.0)]

    def generate(self, x, requirements):
        return {"params": {"pocket_mm": round(float(x[0]), 3)}}


class PocketFit(Evaluator):
    name = "fit"

    def evaluate(self, design, requirements):
        pocket = design["params"]["pocket_mm"]
        target = float((requirements.constraints or {}).get("pocket_mm") or 8.85)
        # A pocket drawn at the pin size prints tight. Stay at or above the known working size.
        violation = 0.0 if pocket + 1e-9 >= target - 0.15 else (target - 0.15) - pocket
        return {
            "objectives": [-abs(pocket - target)],
            "violation": violation,
            "metrics": {"pocket_mm": pocket, "feasible": violation <= 0.0},
            "uncertainties": {"fit": "Printed holes run about 0.1–0.2 mm undersize. Test-fit. Do not trust CAD."},
        }


def main():
    ap = argparse.ArgumentParser(description="Sweep drybox adapter pocket sizes")
    ap.add_argument("--pockets", type=float, nargs="*", default=DEFAULT_SWEEP)
    ap.add_argument("-o", "--out", default="out/drybox-sweep")
    ap.add_argument("--quick", action="store_true", help="only 8.75, 8.85, 8.95")
    args = ap.parse_args()
    out = Path(args.out)
    requirements = load_requirements(HERE / "requirements.yaml")
    if requirements.errors:
        raise SystemExit("requirements: " + "; ".join(requirements.errors))
    found = process_run(
        PocketGenerator(),
        [PocketFit()],
        requirements,
        method="grid",
        n_each=3 if args.quick else 7,
        seed=1,
    )
    found.save(out / "result.json")
    rows = []
    for trial in found.trials:
        pocket = float(trial.info["pocket_mm"])
        _files, stats = generate(Params(pocket=pocket), out_dir=out)
        rows.append(stats)
    (out / "sweep.json").write_text(json.dumps(rows, indent=2))
    print("wrote", out / "result.json")
    print("Test-fit the printed parts on the real insert. Nothing was sent to a printer.")


if __name__ == "__main__":
    main()
