"""One generative grate: finite scores, a closed mesh, insert within the bore."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "models" / "hair-catcher" / "methods"))

from gen_grate import (  # noqa: E402
    build_meshes,
    decode,
    evaluate_design,
    fit_from_requirements,
)


class GrateTests(unittest.TestCase):
    def test_mid_design_is_feasible_and_closed(self):
        fit = fit_from_requirements({})
        design = decode([12, 0.5, 0.4, 0.1, 1.6, 0.2, 2.2, 0.0], fit)
        ev = evaluate_design(design, fit, pitch=0.2)
        info = ev["info"]
        self.assertGreater(info["n_openings"], 0)
        self.assertGreater(info["flow_mm3_s"], 0.0)
        self.assertLessEqual(info["max_ball_mm"], fit["max_ball"] + 0.05)
        self.assertGreaterEqual(info["max_ball_mm"], fit["film_gap"])
        self.assertLessEqual(info["insert_depth_mm"], fit["max_insert"] + 0.05)
        self.assertGreaterEqual(design["strut"], fit["min_strut"] - 1e-6)
        use, printed = build_meshes(ev["holes"], fit, design["thickness"], n_outer=72)
        self.assertTrue(use.is_watertight)
        self.assertTrue(printed.is_watertight)
        self.assertGreater(use.volume, 1000.0)
        # 12 through-holes -> euler 2 - 2*holes. Allow the placed count.
        self.assertEqual(use.euler_number, 2 - 2 * info["n_openings"])


if __name__ == "__main__":
    unittest.main()
