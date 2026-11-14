# Roadmap

The `gendesign` package already runs 2-D and 3-D SIMP with an optimality-criteria update, Voronoi and gyroid lattices, grid / random / genetic / CMA-ES search (Optuna TPE when it is installed), mesh smoothing, and printability checks. The methods below are the next general solvers. Part-specific scripts in `models/` are not a substitute for them.

## Level-set topology optimization

Evolve the boundary as a level set, instead of only a element-wise SIMP density. The current solvers are `gendesign/topopt2d.py` and `gendesign/topopt3d.py`.

## MMA

Method of moving asymptotes as an update rule beside the optimality-criteria loop those solvers use now.

## Shape and size optimization

A general solver for boundary moves and for dimensions. The hair-catcher bowl search and the drybox pocket sweep are part-specific parametric searches, not this solver.

## Implicit / field modeling

A shared signed-distance or other field modeler, with meshing and Boolean operations the examples can call. Version C of the hair catcher is a one-off field script in `models/hair-catcher/legacy-C/`.

## Graph and rule-based generation

Build a part by growing or rewriting a graph (struts, junctions, ports) under explicit rules, then mesh the result.

## Multi-physics checks

Flow, heat, and coupled structural checks with the same pass/fail record as a print test. `gendesign/evaluate.py` today reports volume, a min-feature estimate, overhang area, and an optional PrusaSlicer time.
