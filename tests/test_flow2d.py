"""Drainage estimator: orifice formula, capillary cutoff, raster openings."""
from __future__ import annotations

import math
import unittest

import numpy as np

from gendesign.flow2d import (
    capillary_length_mm,
    capillary_transmission,
    drainage_report,
    orifice_flow,
)


class FlowTests(unittest.TestCase):
    def test_capillary_length_is_water(self):
        lam = capillary_length_mm()
        self.assertAlmostEqual(lam, math.sqrt(0.072 / 9810.0) * 1000.0, places=4)
        self.assertTrue(2.5 < lam < 2.9)

    def test_transmission_ramp(self):
        self.assertEqual(capillary_transmission(1.0, 2.7, 4.0), 0.0)
        self.assertEqual(capillary_transmission(4.0, 2.7, 4.0), 1.0)
        self.assertEqual(capillary_transmission(5.0, 2.7, 4.0), 1.0)
        mid = capillary_transmission(2.7 + 0.65, 2.7, 4.0)
        self.assertAlmostEqual(mid, 0.5, places=6)

    def test_orifice_formula(self):
        q = orifice_flow(58.0, head_mm=5.0, cd=0.61, g_mm_s2=9810.0, transmission=1.0)
        expect = 0.61 * 58.0 * math.sqrt(2.0 * 9810.0 * 5.0)
        self.assertAlmostEqual(q, expect, places=6)
        self.assertEqual(orifice_flow(58.0, 5.0, transmission=0.0), 0.0)
        self.assertEqual(orifice_flow(0.0, 5.0), 0.0)

    def test_circle_opening(self):
        pitch = 0.1
        R = 8.0
        n = int(round(2 * R / pitch))
        xs = (np.arange(n) + 0.5) * pitch - R
        X, Y = np.meshgrid(xs, xs, indexing="xy")
        domain = X**2 + Y**2 <= (6.5) ** 2
        void = X**2 + Y**2 <= (3.0) ** 2
        rep = drainage_report(void, domain, pitch, head_mm=5.0, film_gap_mm=2.7, film_full_mm=4.0)
        self.assertEqual(rep["n_openings"], 1)
        # Raster inscribed diameter sits about one pixel under the true 6 mm.
        self.assertAlmostEqual(rep["max_ball_mm"], 6.0, delta=0.25)
        area = math.pi * 3.0**2
        self.assertAlmostEqual(rep["open_area_mm2"], area, delta=area * 0.04)
        self.assertAlmostEqual(rep["flow_mm3_s"], orifice_flow(rep["open_area_mm2"], 5.0), delta=1.0)
        self.assertEqual(rep["film_area_mm2"], 0.0)
        self.assertGreater(rep["cells"][0]["hydraulic_d_mm"], 4.0)

    def test_small_cell_holds_a_film(self):
        pitch = 0.08
        R = 5.0
        n = int(round(2 * R / pitch))
        xs = (np.arange(n) + 0.5) * pitch - R
        X, Y = np.meshgrid(xs, xs, indexing="xy")
        domain = X**2 + Y**2 <= 4.0**2
        void = X**2 + Y**2 <= 0.6**2  # inscribed ~1.2 mm, under the film gap
        rep = drainage_report(void, domain, pitch, film_gap_mm=2.7, film_full_mm=4.0)
        self.assertEqual(rep["flow_mm3_s"], 0.0)
        self.assertGreater(rep["film_area_mm2"], 0.5)
        self.assertLess(rep["max_ball_mm"], 2.7)

    def test_max_ball_is_the_larger_opening(self):
        pitch = 0.1
        n = 80
        xs = (np.arange(n) + 0.5) * pitch - 4.0
        X, Y = np.meshgrid(xs, xs, indexing="xy")
        domain = np.ones_like(X, dtype=bool)
        void = ((X + 1.5) ** 2 + Y**2 <= 0.7**2) | ((X - 1.6) ** 2 + Y**2 <= 1.8**2)
        rep = drainage_report(void, domain, pitch, film_gap_mm=2.7, film_full_mm=4.0)
        self.assertEqual(rep["n_openings"], 2)
        self.assertAlmostEqual(rep["max_ball_mm"], 3.6, delta=0.3)
        # The small cell contributes no flow; the 3.6 mm cell is on the ramp.
        self.assertGreater(rep["flow_mm3_s"], 0.0)
        self.assertLess(rep["cells"][0]["transmission"] + rep["cells"][1]["transmission"], 2.0)


if __name__ == "__main__":
    unittest.main()
