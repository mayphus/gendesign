"""Shared generative-design tools: topology optimization, lattices, search, evaluation, iteration logs."""

from .evaluate import evaluate_mesh, min_feature, overhang_report
from .flow2d import capillary_length_mm, capillary_transmission, drainage_report, orifice_flow
from .iterate import (
    contact_sheet,
    evolution_gif,
    load_iterations,
    score_chart,
    write_iteration,
)
from .lattice import gyroid_mesh, voronoi_lattice
from .search import cma_es, genetic_minimize, grid_search, nsga2, pareto_front, random_search
from .stiffness import grillage_deflection, section_properties
from .topopt2d import topopt_2d
from .topopt3d import topopt_3d

__all__ = [
    "capillary_length_mm",
    "capillary_transmission",
    "cma_es",
    "contact_sheet",
    "drainage_report",
    "evaluate_mesh",
    "evolution_gif",
    "genetic_minimize",
    "grid_search",
    "grillage_deflection",
    "gyroid_mesh",
    "load_iterations",
    "min_feature",
    "nsga2",
    "orifice_flow",
    "overhang_report",
    "pareto_front",
    "random_search",
    "score_chart",
    "section_properties",
    "topopt_2d",
    "topopt_3d",
    "voronoi_lattice",
    "write_iteration",
]

__version__ = "0.1.0"
