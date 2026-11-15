"""One generative grate: finite scores, a closed mesh, insert within the bore."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "models" / "hair-catcher" / "archive" / "methods"))

from gen_grate import (  # noqa: E402
    build_meshes,
    decode,
    evaluate_design,
    fit_from_requirements,
    round_openings,
)
from shapely.geometry import Point, Polygon  # noqa: E402


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
        self.assertLessEqual(info["film_area_mm2"], 3.0)
        self.assertEqual(len(info["objectives"]), 2)
        self.assertGreaterEqual(design["strut"], 1.50)
        self.assertLessEqual(design["exponent"], 0.46)
        self.assertGreater(info["min_ball_mm"], 3.3)

    def test_film_crack_is_filled_and_corners_round(self):
        fit = fit_from_requirements({})
        big = Point(0, 0).buffer(4.2, quad_segs=8)
        crack = Polygon([(-2.0, 7.0), (2.2, 7.0), (2.2, 7.5), (-2.0, 7.5)])
        holes = round_openings([big, crack], fit, quad_segs=4)
        self.assertEqual(len(holes), 1)
        self.assertGreater(holes[0].area, 20.0)
        self.assertFalse(holes[0].buffer(-fit["opening_floor"] / 2.0).is_empty)
        sharp = Polygon([(-6.0, -4.0), (7.0, -3.5), (0.0, 7.0)])
        rounded = round_openings([sharp], fit, quad_segs=4)
        self.assertEqual(len(rounded), 1)
        self.assertGreater(len(rounded[0].exterior.coords), 8)


if __name__ == "__main__":
    unittest.main()
