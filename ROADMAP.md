# Roadmap

The loop (requirements → analysis → round → AI review → owner go → test → feedback) is in place. The next work is better analysis and more generators inside it.

## Next for the examples

- **Hair catcher:** add `gendesign.corners` (hair snag, corner water) as an objective, so hole rounding has to compete with drainage (round 00 and 01 reviews). Replace the two assumed targets with a measured tap flow and the largest acceptable hole. Calibrate the 20 MPa allowable with a 30 N press on a coupon.

## Analysis and evaluation

- **3-D solid FEA** of an exported mesh (tetrahedral linear elasticity) as an evaluator, replacing closed-form plate estimates when a part is close to a limit.
- **Flow simulation** beyond the orifice model, where drainage binds.
- Coupled checks with the same pass/fail record as a print test.

## Generators

- **Topology optimization as a round generator.** `topopt2d` and `topopt3d` (SIMP, optimality criteria) run today from the CLI; wire them as a `Generator` whose genes are volume fraction, filter radius and load cases, with an overhang filter for printing.
- **Level-set** topology optimization and an **MMA** update beside optimality criteria.
- **Shape and size optimization** as a general solver.
- **Graph / rule-based generation:** grow struts, junctions and ports under explicit rules, then mesh with `gendesign.field`.

## GPU

Everything runs on the CPU today. When 3-D FEA, 3-D topology optimization or surrogate training outgrow it, run those as batch jobs on a Kaggle GPU notebook (pushed and collected with the `kaggle` CLI) behind an optional remote evaluator. The interactive loop stays local.

## Surrogates

A learned surrogate of an expensive evaluator, trained on a model's own round history, so larger searches stay cheap. Only after 3-D FEA exists to train it on.
