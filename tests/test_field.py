"""Implicit modeling: smooth Booleans, meshing, overhang check."""
import unittest

import numpy as np

from gendesign.field import mesh_field, mx, print_orientation, smax, smin, unsupported_area


def _sphere(h=0.25, r=3.0):
    xs = np.arange(-4, 4 + 1e-9, h)
    X, Y, Z = np.meshgrid(xs, xs, xs, indexing="ij")
    return np.sqrt(X**2 + Y**2 + Z**2) - r, xs


class FieldTest(unittest.TestCase):
    def test_smooth_union_is_below_both(self):
        a = np.linspace(-1, 1, 50)
        b = a[::-1]
        u = smin(a, b, 0.5)
        self.assertTrue(np.all(u <= np.minimum(a, b) + 1e-12))
        self.assertTrue(np.all(smax(a, b, 0.5) >= np.maximum(a, b) - 1e-12))
        np.testing.assert_allclose(smin(a, b + 10, 0.5), a)  # far apart: exact min

    def test_mx_is_intersection(self):
        self.assertEqual(float(mx(np.array(1.0), np.array(-2.0), np.array(0.5))), 1.0)

    def test_sphere_mesh_volume(self):
        F, xs = _sphere()
        m = mesh_field(F, (xs[0], xs[0], xs[0]), 0.25)
        self.assertTrue(m.is_watertight)
        self.assertAlmostEqual(m.volume, 4 / 3 * np.pi * 27, delta=0.03 * 113)
        p = print_orientation(m)
        self.assertAlmostEqual(p.bounds[0][2], 0.0, places=6)

    def test_flat_face_on_grid_plane_is_closed(self):
        # z = 0 face sampled exactly on a grid plane used to leave open edges
        h = 0.1
        xs = np.arange(-3, 3 + 1e-9, h)
        zs = np.arange(-2, 0.3 + 1e-9, h)  # float noise: the z = 0 plane is ~1e-16
        X, Y, Z = np.meshgrid(xs, xs, zs, indexing="ij")
        F = mx(np.hypot(X, Y) - 2, Z, -1.5 - Z)
        m = mesh_field(F, (xs[0], xs[0], zs[0]), h)
        self.assertTrue(m.is_watertight)

    def test_overhang_flags_a_ledge(self):
        # Printed upside down (installed z = -print height): a thin post on the
        # bed that becomes a wide table puts the table rim over air.
        h = 0.1
        xs = np.arange(-5, 5 + 1e-9, h)
        zs = np.arange(-4, 0 + 1e-9, h)
        X, Y = np.meshgrid(xs, xs, indexing="ij")
        R = np.hypot(X, Y)
        straight = np.stack([R - 3 + 0 * z for z in zs], axis=2)
        table = np.stack([R - (1 if z > -1 else 4) for z in zs], axis=2)
        self.assertEqual(unsupported_area(straight, zs, h, height=4)["total_mm2"], 0.0)
        self.assertGreater(unsupported_area(table, zs, h, height=4)["total_mm2"], 10.0)


if __name__ == "__main__":
    unittest.main()
