"""Shared generative-design tools: topology optimization, lattices, search, evaluation, iteration logs."""

from .evaluate import evaluate_mesh, min_feature, overhang_report
from .iterate import (
    contact_sheet,
    evolution_gif,
    load_iterations,
    score_chart,
    write_iteration,
)
from .lattice import gyroid_mesh, voronoi_lattice
from .search import cma_es, genetic_minimize, grid_search, pareto_front, random_search
from .topopt2d import topopt_2d
from .topopt3d import topopt_3d

__all__ = [
    "cma_es",
    "contact_sheet",
    "evaluate_mesh",
    "evolution_gif",
    "genetic_minimize",
    "grid_search",
    "gyroid_mesh",
    "load_iterations",
    "min_feature",
    "overhang_report",
    "pareto_front",
    "random_search",
    "score_chart",
    "topopt_2d",
    "topopt_3d",
    "voronoi_lattice",
    "write_iteration",
]

__version__ = "0.1.0"
