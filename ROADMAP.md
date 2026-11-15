# Roadmap

The loop (requirements → analysis → round → AI review → owner go → test → feedback) is in place. The next work is better analysis and more generators inside it.

## Next for the examples

- **Hair catcher:** owner's go on the round 01 knee, then a print, a timed litre and a 30 N press as `calibrate:` lines. Replace the two assumed targets with a measured tap flow and the largest acceptable hole.
- **Search:** treat an integer layout seed as a discrete choice (multi-start over seeds, continuous genes per seed); a cold round 02 found no feasible design in its first two generations.

## Analysis and evaluation

- **3-D solid FEA** of an exported mesh (tetrahedral linear elasticity) as an evaluator, replacing closed-form plate estimates when a part is close to a limit.
- **Flow simulation** beyond the orifice model, where drainage binds.
- Coupled checks with the same pass/fail record as a print test.

## Generators

- **Topology optimization as a round generator.** Done for 2-D: [`models/cantilever-bracket/`](models/cantilever-bracket/) uses `topopt2d` as a `Generator` (genes: volfrac, filter radius, load height) with an optional +y overhang projection. Still to do: wire `topopt3d` the same way.
- **Level-set** topology optimization and an **MMA** update beside optimality criteria.
- **Shape and size optimization** as a general solver.
- **Graph / rule-based generation:** grow struts, junctions and ports under explicit rules, then mesh with `gendesign.field`.

## GPU

Everything runs on the CPU today. When 3-D FEA, 3-D topology optimization or surrogate training outgrow it, run those as batch jobs on a Kaggle GPU notebook (pushed and collected with the `kaggle` CLI) behind an optional remote evaluator. The interactive loop stays local.

## Surrogates

A learned surrogate of an expensive evaluator, trained on a model's own round history, so larger searches stay cheap. Only after 3-D FEA exists to train it on.
