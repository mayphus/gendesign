# Archive

Scripts that produced the older hair-catcher designs. They are records, kept so those designs can be re-run; new work goes through `gendesign analyze` / `round` and [model.py](../model.py).

| Folder / file | Produced | Run |
|---|---|---|
| [pebble-field/](pebble-field/README.md) | pebble-c and pebble-d (`build.py`, styles C and D), the original pebble-e script (`build_plate.py`), seed search, renders | from that folder, or `python models/hair-catcher/generate.py --design designs/pebble-d/design.json` |
| [methods/](methods/README.md) | smooth-v2 (`smooth_cad.py`, `smooth_search.py`), deep-v3, voronoi-a/b/c, generative-v1 rounds (`gen_grate.py`, `gen_search.py`, `gen_round03.py`), plate SIMP | through `optimize.py` here, or `generate.py` for smooth-v2 and generative-v1 |
| `optimize.py` | the per-method searches | `python models/hair-catcher/archive/optimize.py --method smooth --quick` |
| `compare.py` | v2 vs v3 comparison chart | prints the saved chart path |

`build_plate.py` is superseded: `model.py` reproduces pebble-e from it exactly (same 15 holes, 600,000 faces, 3450.5 mm³).
