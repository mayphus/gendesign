#!/usr/bin/env python3
"""Search for a hair-catcher from requirements.

Methods:
  generative — AI + generative design. NSGA-II over a Voronoi density field.
               One short round; the AI reviews renders before the next round.
  smooth   — 7-hole dished bowl (the v2 winner family). Evolutionary search.
  deep     — deeper side-slot basket (v3). Evolutionary + grid seeds.
  grid     — evaluate the deep-basket grid seed pack only.
  voronoi  — two-level Voronoi grate (variants A/B/C). Uses saved plans.
  topopt   — plate SIMP on the grate disc (methods/topopt_plate.py).
  all      — run the cheap methods in sequence (--quick recommended).

Defaults finish in a few minutes on a laptop. --quick is smaller still.
Never starts a print.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "methods"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))


def load_req(path: Path) -> dict:
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def _run_generative(req, out: Path, quick: bool, round_index: str):
    import gen_search

    # Round 01 is the repaired search. --quick stays a smoke test.
    pop, gens = (8, 2) if quick else (24, 8)
    return gen_search.run_round(req, out, pop=pop, gens=gens, seed=11, round_index=round_index)


def _run_smooth(req, out: Path, quick: bool):
    import smooth_search as S

    rules = req.get("constraints") or req
    # overlay requirements onto the search module
    if "max_ball_mm" in rules or "max_sphere_mm" in rules:
        S.MAX_SPHERE_MM = float(rules.get("max_ball_mm") or rules["max_sphere_mm"])
    if "min_strut_mm" in rules:
        S.MIN_STRUT_MM = float(rules["min_strut_mm"])
    if "min_insert_mm" in rules:
        S.MIN_INSERT = float(rules["min_insert_mm"])
    if "max_insert_mm" in rules:
        S.MAX_INSERT = float(rules["max_insert_mm"])
    if "max_overhang_deg" in rules:
        S.MAX_OVERHANG_DEG = float(rules["max_overhang_deg"])
    S.OUT = out
    S.ITER = out / "iterations"
    S.ITER.mkdir(parents=True, exist_ok=True)
    if quick:
        S.N_GEN = 3
        S.POP = 12
    # rebuild raster grid in case fit changes (kept at module defaults)
    print(f"smooth search  N_GEN={S.N_GEN} POP={S.POP}  max_ball={S.MAX_SPHERE_MM}  min_strut={S.MIN_STRUT_MM}")
    S.main()
    return out


def _run_deep(req, out: Path, quick: bool):
    import deep_search as D
    import deep_geom as G

    rules = req.get("constraints") or req
    ball = float(rules.get("max_ball_mm") or rules.get("max_sphere_mm") or 8.6)
    max_depth = float(rules.get("max_insert_mm") or 35.0)
    D.IT = out / "iterations"
    D.IT.mkdir(parents=True, exist_ok=True)
    D.OUT = out
    pop, gens, n_seed = (16, 3, 60) if quick else (48, 10, 400)
    log = []
    print(f"deep search  pop={pop} gens={gens} n_seed={n_seed} ball={ball} max_depth={max_depth}")
    result = D.run_ga(ball, max_depth, seed=20261113, pop=pop, gens=gens, n_seed=n_seed, tag="deep", log=log)
    (out / "search-result.json").write_text(json.dumps(result, indent=2, default=str))
    print("wrote", out / "search-result.json")
    return result


def _run_grid(req, out: Path, quick: bool):
    import deep_geom as G
    from grid_seeds import grid_seeds

    rules = req.get("constraints") or req
    ball = float(rules.get("max_ball_mm") or 8.6)
    max_depth = float(rules.get("max_insert_mm") or 35.0)
    seeds = grid_seeds(ball)
    if quick:
        seeds = seeds[::8]
    rows = []
    best = None
    t0 = time.time()
    for g in seeds:
        m, _ = G.evaluate(g, ball, max_depth)
        rows.append(m)
        if best is None or m.get("score", -1e9) > best[0].get("score", -1e9):
            best = (m, g)
    out.mkdir(parents=True, exist_ok=True)
    (out / "grid-results.json").write_text(
        json.dumps({"n": len(rows), "elapsed_s": round(time.time() - t0, 1), "best": best[0] if best else None,
                    "best_genome": best[1] if best else None}, indent=2, default=str)
    )
    print("grid seeds evaluated:", len(rows), "best score", None if not best else best[0].get("score"))
    return best


def _run_voronoi(req, out: Path, variant: str):
    out.mkdir(parents=True, exist_ok=True)
    note = {
        "method": "voronoi",
        "variant": variant,
        "message": (
            "Voronoi variants A (organic small cells), B (larger drainage cells) "
            "and C (rounded pebble cells + branching struts) are in methods/voronoi_*.py. "
            "Saved winners and measured stats are under designs/voronoi-*/. "
            "Version C lives in models/hair-catcher/legacy-C/ "
            "(build.py, design.py, search.py, render.py). Run those scripts from that folder. "
            "Rebuilds of the saved A/B/C plans need the 2-D plans in those design folders."
        ),
        "designs": {
            "A": "designs/voronoi-a/design.json",
            "B": "designs/voronoi-b/design.json",
            "C": "designs/voronoi-c/design.json",
        },
    }
    (out / "voronoi-note.json").write_text(json.dumps(note, indent=2))
    print(note["message"])
    return note


def _run_topopt(req, out: Path, quick: bool):
    out.mkdir(parents=True, exist_ok=True)
    print(
        "Plate SIMP for this drain lives in methods/topopt_plate.py "
        "(Reissner-Mindlin plate, finger + water load cases). "
        "A generic 2-D/3-D SIMP toolkit is at the repo root: "
        "python -m gendesign topopt2d --quick"
    )
    (out / "topopt-note.json").write_text(json.dumps({
        "script": "methods/topopt_plate.py",
        "generic": "python -m gendesign topopt2d --quick",
    }, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Optimize a basin hair-catcher from requirements")
    ap.add_argument("--method", default="smooth",
                    choices=["generative", "smooth", "deep", "grid", "voronoi", "topopt", "all"])
    ap.add_argument("--requirements", type=Path, default=HERE / "requirements.yaml")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--quick", action="store_true", help="smaller population / fewer generations")
    ap.add_argument("--round", default="01", help="iteration folder name, e.g. 01")
    ap.add_argument("--variant", default="C", help="voronoi variant A|B|C")
    args = ap.parse_args()
    req = load_req(args.requirements)
    out = args.out or Path("out") / f"search-{args.method}"
    out.mkdir(parents=True, exist_ok=True)
    methods = ["smooth", "grid", "voronoi", "topopt"] if args.method == "all" else [args.method]
    # 'all' skips full deep unless not --quick, because deep is the expensive one
    if args.method == "all" and not args.quick:
        methods.append("deep")
    for m in methods:
        dest = out if len(methods) == 1 else out / m
        dest.mkdir(parents=True, exist_ok=True)
        print("==>", m, "->", dest)
        if m == "generative":
            _run_generative(req, dest, args.quick, args.round)
        elif m == "smooth":
            _run_smooth(req, dest, args.quick)
        elif m == "deep":
            _run_deep(req, dest, args.quick)
        elif m == "grid":
            _run_grid(req, dest, args.quick)
        elif m == "voronoi":
            _run_voronoi(req, dest, args.variant)
        elif m == "topopt":
            _run_topopt(req, dest, args.quick)
    print("done. nothing was sent to a printer.")


if __name__ == "__main__":
    main()
