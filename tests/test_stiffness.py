"""Beam grillage against the cantilever formulas."""
from __future__ import annotations

import unittest

import numpy as np

from gendesign.stiffness import grillage_deflection, section_properties


class StiffnessTests(unittest.TestCase):
    def test_euler_cantilever_along_x(self):
        # Slender beam so shear is a small addition on top of F L^3 / 3 E I.
        L, b, h = 40.0, 2.0, 3.0
        E, nu = 2340.0, 0.36
        F = 10.0
        nodes = np.array([[0.0, 0.0], [L, 0.0]])
        res = grillage_deflection(
            nodes, [(0, 1)], [b], h,
            E=E, nu=nu, load_N=F, load_xy=(L, 0.0), load_radius_mm=1.0,
            fixed_mask=[True, False],
        )
        sec = section_properties(b, h)
        G = E / (2 * (1 + nu))
        kappa = 5.0 / 6.0
        delta = F * L**3 / (3 * E * sec["I"]) + F * L / (kappa * G * sec["A"])
        self.assertTrue(res["connected"])
        self.assertAlmostEqual(res["max_disp_mm"], delta, delta=delta * 0.02)

    def test_same_answer_along_y(self):
        L, b, h = 40.0, 2.0, 3.0
        E, nu, F = 2340.0, 0.36, 10.0
        nodes = np.array([[0.0, 0.0], [0.0, L]])
        res = grillage_deflection(
            nodes, [(0, 1)], [b], h,
            E=E, nu=nu, load_N=F, load_xy=(0.0, L), load_radius_mm=1.0,
            fixed_mask=[True, False],
        )
        sec = section_properties(b, h)
        G = E / (2 * (1 + nu))
        delta = F * L**3 / (3 * E * sec["I"]) + F * L / (kappa := 5.0 / 6.0) / (G * sec["A"])
        self.assertAlmostEqual(res["max_disp_mm"], delta, delta=delta * 0.02)

    def test_thicker_is_stiffer(self):
        nodes = np.array([[0.0, 0.0], [20.0, 0.0]])
        kw = dict(E=2340.0, load_N=10.0, load_xy=(20.0, 0.0), load_radius_mm=1.0,
                  fixed_mask=[True, False])
        thin = grillage_deflection(nodes, [(0, 1)], [2.0], 1.2, **kw)
        thick = grillage_deflection(nodes, [(0, 1)], [2.0], 3.0, **kw)
        self.assertLess(thick["max_disp_mm"], thin["max_disp_mm"] * 0.25)

    def test_disconnected_load(self):
        nodes = np.array([[0.0, 0.0], [5.0, 0.0], [20.0, 0.0], [25.0, 0.0]])
        edges = [(0, 1), (2, 3)]
        res = grillage_deflection(
            nodes, edges, [1.5, 1.5], 2.0,
            load_N=10.0, load_xy=(25.0, 0.0), load_radius_mm=1.0,
            fixed_mask=[True, False, False, False],
        )
        self.assertFalse(res["connected"])
        self.assertEqual(res["stiffness_N_per_mm"], 0.0)


if __name__ == "__main__":
    unittest.main()
