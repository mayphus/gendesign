"""2-D drainage estimate for a thin grate.

Sharp-orifice flow at a fixed head, with a capillary cutoff:

    Q = Cd * A * sqrt(2 * g * h) * T(d)

A is the cell area, h is the head, Cd defaults to 0.61, and g is
9810 mm/s^2 so Q is mm^3/s when A is mm^2 and h is mm. T(d) shuts
the cell off when its inscribed diameter d is small enough to hold a
water film:

    T = 0   if d <= film_gap
    T = 1   if d >= film_full
    linear in between

film_gap defaults to the capillary length of pure water,

    lambda = sqrt(sigma / (rho * g)) ≈ 2.71 mm

with sigma = 0.072 N/m. That is the scale at which a meniscus can
bridge an opening. It is a threshold, not a Young-Laplace solve:
soap, hair, and a real basin are outside the model. Voronoi A
(openings near 1 mm) held water; the cutoff is there so a search
cannot treat those cells as drainage.
"""
from __future__ import annotations

import math

import numpy as np

# sigma / (rho * g) with sigma = 0.072 N/m, rho = 1000 kg/m^3, g = 9.81 m/s^2.
WATER_CAPILLARY_M = math.sqrt(0.072 / (1000.0 * 9.81))


def capillary_length_mm(sigma_N_per_m: float = 0.072, rho: float = 1000.0, g: float = 9.81) -> float:
    """Capillary length sqrt(sigma / (rho g)), in millimetres."""
    return float(math.sqrt(sigma_N_per_m / (rho * g)) * 1000.0)


def capillary_transmission(inscribed_d_mm: float, film_gap_mm: float = 2.7, film_full_mm: float = 4.0) -> float:
    """Fraction of orifice flow credited to a cell of this inscribed diameter."""
    d = float(inscribed_d_mm)
    if film_full_mm <= film_gap_mm:
        return 1.0 if d >= film_gap_mm else 0.0
    if d <= film_gap_mm:
        return 0.0
    if d >= film_full_mm:
        return 1.0
    return (d - film_gap_mm) / (film_full_mm - film_gap_mm)


def orifice_flow(area_mm2: float, head_mm: float, cd: float = 0.61, g_mm_s2: float = 9810.0, transmission: float = 1.0) -> float:
    """Q = Cd * A * sqrt(2 g h) * T, in mm^3/s. Non-positive head or area is zero."""
    if area_mm2 <= 0 or head_mm <= 0 or transmission <= 0 or cd <= 0:
        return 0.0
    return float(cd * area_mm2 * math.sqrt(2.0 * g_mm_s2 * head_mm) * transmission)


def _component_table(void: np.ndarray, pitch_mm: float):
    """Connected openings. Returns list of dicts and the label image."""
    from skimage.measure import label, regionprops
    from scipy.ndimage import distance_transform_edt

    void = np.asarray(void, dtype=bool)
    lab = label(void, connectivity=1)
    if lab.max() == 0:
        return [], lab
    edt = distance_transform_edt(void) * float(pitch_mm)
    rows = []
    for prop in regionprops(lab):
        region = lab == prop.label
        peak = float(edt[region].max()) if region.any() else 0.0
        area = float(prop.area) * pitch_mm * pitch_mm
        per = float(prop.perimeter) * pitch_mm
        hy = (4.0 * area / per) if per > 1e-9 else 0.0
        cy, cx = prop.centroid
        rows.append({
            "area_mm2": area,
            "perimeter_mm": per,
            "inscribed_d_mm": 2.0 * peak,
            "hydraulic_d_mm": hy,
            "centroid_px": (float(cy), float(cx)),
        })
    return rows, lab


def drainage_report(
    void,
    domain,
    pitch_mm: float,
    *,
    head_mm: float = 5.0,
    cd: float = 0.61,
    g_mm_s2: float = 9810.0,
    film_gap_mm: float | None = None,
    film_full_mm: float = 4.0,
) -> dict:
    """Score a raster grate.

    `void` is open (True = hole). `domain` is the disc the open area is
    measured against. Both are boolean arrays of the same shape.
    pitch_mm is the pixel size.

    Openings are 4-connected components of void inside the domain.
    Inscribed diameter is twice the maximum Euclidean distance transform
    inside the cell (a raster under-reads a perfect circle by about a
    pixel). Hydraulic diameter is 4A/P from the pixel perimeter, which
    runs long on diagonals; it is reported, not used for the flow.
    """
    if film_gap_mm is None:
        film_gap_mm = capillary_length_mm()
    void = np.asarray(void, dtype=bool)
    domain = np.asarray(domain, dtype=bool)
    if void.shape != domain.shape:
        raise ValueError("void and domain shapes differ")
    pitch_mm = float(pitch_mm)
    open_mask = void & domain
    domain_px = int(domain.sum())
    domain_area = domain_px * pitch_mm * pitch_mm
    cells, _lab = _component_table(open_mask, pitch_mm)
    flow = 0.0
    draining_area = 0.0
    film_area = 0.0
    partial_area = 0.0
    for c in cells:
        t = capillary_transmission(c["inscribed_d_mm"], film_gap_mm, film_full_mm)
        q = orifice_flow(c["area_mm2"], head_mm, cd=cd, g_mm_s2=g_mm_s2, transmission=t)
        c["transmission"] = t
        c["flow_mm3_s"] = q
        flow += q
        if t <= 0.0:
            film_area += c["area_mm2"]
        elif t >= 1.0:
            draining_area += c["area_mm2"]
        else:
            partial_area += c["area_mm2"]
            draining_area += c["area_mm2"] * t
    open_area = float(open_mask.sum()) * pitch_mm * pitch_mm
    dias = [c["inscribed_d_mm"] for c in cells]
    return {
        "pitch_mm": pitch_mm,
        "head_mm": float(head_mm),
        "cd": float(cd),
        "film_gap_mm": float(film_gap_mm),
        "film_full_mm": float(film_full_mm),
        "domain_area_mm2": domain_area,
        "open_area_mm2": open_area,
        "open_area_frac": (open_area / domain_area) if domain_area > 0 else 0.0,
        "n_openings": len(cells),
        "max_ball_mm": float(max(dias) if dias else 0.0),
        "min_ball_mm": float(min(dias) if dias else 0.0),
        "flow_mm3_s": float(flow),
        "flow_cm3_s": float(flow) / 1000.0,
        "draining_area_mm2": float(draining_area),
        "film_area_mm2": float(film_area),
        "partial_area_mm2": float(partial_area),
        "film_area_frac": (film_area / open_area) if open_area > 0 else 0.0,
        "cells": cells,
    }
