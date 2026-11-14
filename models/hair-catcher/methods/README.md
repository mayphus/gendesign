# Methods (source)

Usable redesign methods for this model. Prefer the CLIs in the parent
folder (`generate.py`, `optimize.py`) over calling these scripts raw —
some still have their original standalone `main()` and write into the
working directory.

| File | Method |
|---|---|
| `smooth_cad.py` | Filleted 7-hole bowl (CadQuery). Used by `generate.py`. |
| `smooth_search.py` | Evolutionary search that found v2 (holes / radial / bowl). |
| `deep_geom.py`, `deep_search.py`, `deep_build.py`, `grid_seeds.py` | Deep side-slot basket (v3) and its grid seeds. |
| `voronoi_A.py`, `voronoi_B_*.py`, `voronoi_C_*.py` | Two-level Voronoi hair catchers. |
| `topopt_plate.py` | Plate SIMP on the grate disc. |
| `early_de40.py` | Early solid De40 catcher. |
| `compare_v3.py` | v2 vs v3 comparison chart (needs local stats/previews). |
