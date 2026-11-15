"""NSGA-II finds a non-dominated front and respects a constraint."""
from __future__ import annotations

import unittest

import numpy as np

from gendesign.search import nsga2, pareto_front


def _zdt_like(x):
    # Maximize f1 = x0 and f2 = 1 - sqrt(x0). Front is x0 in [0, 1].
    x0 = float(np.clip(x[0], 0.0, 1.0))
    return [x0, 1.0 - np.sqrt(x0)]


class NsgaTests(unittest.TestCase):
    def test_front_is_nondominated_and_spread(self):
        res = nsga2(_zdt_like, [(0.0, 1.0), (0.0, 1.0)], pop=24, gens=18, seed=2)
        self.assertGreaterEqual(len(res.front), 6)
        vals = np.array([t.info["objectives"] for t in res.front])
        for i in range(len(vals)):
            for j in range(len(vals)):
                if i == j:
                    continue
                dominated = np.all(vals[j] >= vals[i] - 1e-9) and np.any(vals[j] > vals[i] + 1e-9)
                self.assertFalse(dominated)
        self.assertLess(vals[:, 0].min(), 0.25)
        self.assertGreater(vals[:, 0].max(), 0.75)
        # The scalar pareto helper agrees on the named keys.
        for t in res.trials:
            t.info["a"] = t.info["objectives"][0]
            t.info["b"] = t.info["objectives"][1]
        again = pareto_front(res.population, ["a", "b"])
        self.assertGreaterEqual(len(again), 4)

    def test_constraint_cuts_the_low_end(self):
        def fun(x):
            f = _zdt_like(x)
            violation = max(0.0, 0.35 - float(x[0]))
            return {"objectives": f, "violation": violation}

        res = nsga2(fun, [(0.0, 1.0), (0.0, 1.0)], pop=20, gens=12, seed=1)
        self.assertTrue(res.front)
        for t in res.front:
            self.assertTrue(t.info["feasible"])
            self.assertGreaterEqual(t.x[0], 0.35 - 1e-6)

    def test_history_covers_each_generation(self):
        seen = []

        def cb(gen, front, pop):
            seen.append(gen)

        res = nsga2(_zdt_like, [(0.0, 1.0)], pop=8, gens=3, seed=0, callback=cb)
        self.assertEqual(seen, [0, 1, 2, 3])
        self.assertEqual(len(res.history), 4)
        self.assertGreater(res.history[-1]["n_feasible"], 0)


if __name__ == "__main__":
    unittest.main()
