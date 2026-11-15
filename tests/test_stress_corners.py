"""A sharp notch must stress higher, and snag more, than a round one."""
from __future__ import annotations

import unittest

import numpy as np

from gendesign.corners import corner_proxies
from gendesign.stress2d import plane_stress_peak


def _notched_bar(sharp: bool):
    ny, nx = 28, 56
    solid = np.ones((ny, nx), dtype=bool)
    # Edge notch on the top, midspan.
    if sharp:
        for i in range(8):
            solid[ny - 1 - i, nx // 2 - i : nx // 2 + i + 1] = False
    else:
        cy, cx = ny - 2, nx // 2
        yy, xx = np.mgrid[0:ny, 0:nx]
        solid &= (yy - cy) ** 2 + (xx - cx) ** 2 > 7.0 ** 2
        solid[ny - 6 :, :] = True
        solid &= ~(((yy - cy) ** 2 + (xx - cx) ** 2 <= 7.0 ** 2) & (yy >= cy - 1))
    support = np.zeros_like(solid)
    support[:, :2] = True
    return solid, support


class StressCornerTests(unittest.TestCase):
    def test_round_notch_is_less_stressed(self):
        sharp, sup = _notched_bar(True)
        smooth, _ = _notched_bar(False)
        a = plane_stress_peak(sharp, 1.0, load_N=20.0, support=sup, load_radius_px=3.0)
        # Load the right side by using support on the left only; the helper
        # loads the center. Compare the two masks with the same call.
        b = plane_stress_peak(smooth, 1.0, load_N=20.0, support=sup, load_radius_px=3.0)
        self.assertTrue(a["ok"] and b["ok"])
        self.assertGreater(a["p95_MPa"], b["p95_MPa"] * 1.05)

    def test_round_corner_holds_less_and_snags_less(self):
        # A square, walked CCW, has four right-angle solid points if we
        # treat it as a hole. A circle has no tight corner.
        square = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
        ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        circle = np.stack([2 + 2 * np.cos(ang), 2 + 2 * np.sin(ang)], axis=1)
        s = corner_proxies([square], hook_radius_mm=0.5, meniscus_radius_mm=0.7)
        c = corner_proxies([circle], hook_radius_mm=0.5, meniscus_radius_mm=0.7)
        self.assertGreater(s["snag"], c["snag"])
        self.assertGreater(s["retained_mm2"], c["retained_mm2"])


if __name__ == "__main__":
    unittest.main()
