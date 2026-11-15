"""Corner proxies for a plan opening.

These are not a smoothness score. A fiber hooks a corner that sticks out
into the hole when the local radius is tighter than the hook radius. A
meniscus sits in an acute wedge of the opening when that wedge is tighter
than the water-holding radius. Rounding the corner raises the measured
radius, and the proxies fall. Nothing here rewards a fillet radius that
was typed in as a parameter: the radius is measured on the boundary.
"""
from __future__ import annotations

import numpy as np


def _turn(a, b, c):
    """Signed turn at b, in radians, and the local radius.

    Positive turn is a left turn when walking a -> b -> c. For a hole ring
    walked clockwise, a left turn is a corner of the opening (a pocket in
    the solid) and a right turn is a point of the solid sticking into the hole.
    """
    v1 = b - a
    v2 = c - b
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0, 1e6
    cross = float(v1[0] * v2[1] - v1[1] * v2[0])
    dot = float(v1[0] * v2[0] + v1[1] * v2[1])
    phi = float(np.arctan2(cross, dot))
    # A lone kink between long straight legs is sharp. A run of small
    # turns is an arc whose radius is leg / turn.
    if abs(phi) < 0.2:
        rho = (0.5 * (n1 + n2)) / max(abs(phi), 1e-3)
    elif min(n1, n2) < 0.45:
        rho = (0.5 * (n1 + n2)) / max(abs(phi), 1e-3)
    else:
        rho = 0.05
    return phi, float(rho)


def corner_proxies(rings, *, hook_radius_mm: float = 0.5, meniscus_radius_mm: float = 0.7):
    """Snag and retained-water proxies from opening rings.

    Rings are (N, 2) arrays in millimetres, without a repeated closing point.
    Walk direction does not matter: the sign of the turn is taken relative
    to the ring's own winding, and the two kinds of corner are separated by
    that sign.

    snag is the sum, over solid points that stick into a hole, of how far
    the local radius sits below hook_radius_mm. Zero when every such point
    is rounder than the hook radius.

    retained_mm2 is an area of water assigned to opening wedges tighter
    than meniscus_radius_mm. A sharp acute wedge holds the most. A corner
    already rounder than the meniscus radius holds none.
    """
    snag = 0.0
    retained = 0.0
    n_hooks = 0
    n_wedges = 0
    tightest = 1e6
    for ring in rings:
        pts = np.asarray(ring, dtype=float)
        if len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
            pts = pts[:-1]
        n = len(pts)
        if n < 3:
            continue
        # Winding: positive area is CCW. Hole pockets and solid points swap
        # with the winding, so fold the sign onto a CCW walk.
        area = 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1]))
        wind = 1.0 if area >= 0 else -1.0
        for i in range(n):
            phi, rho = _turn(pts[(i - 1) % n], pts[i], pts[(i + 1) % n])
            phi *= wind
            tightest = min(tightest, rho)
            # CCW walk, solid is outside the hole: a right turn (negative)
            # is a solid point jutting into the hole. A left turn is a wedge
            # of the opening.
            if abs(phi) > 0.35 and rho < hook_radius_mm:
                n_hooks += 1
                snag += (hook_radius_mm - rho) / hook_radius_mm
            if phi > 0.35:
                n_wedges += 1
                deficit = max(0.0, meniscus_radius_mm - rho)
                retained += (deficit ** 2) * min(abs(phi), 2.5)
    return {
        "snag": float(snag),
        "retained_mm2": float(retained),
        "n_hooks": int(n_hooks),
        "n_wedges": int(n_wedges),
        "tightest_radius_mm": float(tightest if tightest < 1e5 else 0.0),
    }
