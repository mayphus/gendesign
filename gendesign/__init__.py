"""AI + generative design: requirements in, seeded search and evaluators, picks for an AI review and an owner go, test feedback back into the evaluators."""

from .corners import corner_proxies
from .evaluate import evaluate_mesh, min_feature, overhang_report
from .flow2d import capillary_length_mm, capillary_transmission, drainage_report, orifice_flow
from .iterate import (
    IterationLog,
    contact_sheet,
    evolution_gif,
    load_iterations,
    score_chart,
    write_iteration,
)
from .field import mesh_field, mx, polygon_field, print_orientation, smax, smin, unsupported_area
from .loop import approve, load_model, parse_feedback, record_feedback, run_round, select_picks, status
from .process import (
    Calibration,
    Evaluator,
    FeedbackReport,
    Generator,
    RequirementFlag,
    Result,
    calibrate,
    flag_requirement,
    interpret_note,
    run,
)
from .requirements import Requirements, load_requirements, validate_mapping
from .lattice import gyroid_mesh, voronoi_lattice
from .search import cma_es, genetic_minimize, grid_search, nsga2, pareto_front, random_search
from .stiffness import grillage_deflection, section_properties
from .stress2d import plane_stress_peak
from .topopt2d import overhang_fraction, overhang_project, topopt_2d
from .topopt3d import topopt_3d

__all__ = [
    "approve",
    "load_model",
    "mesh_field",
    "mx",
    "parse_feedback",
    "polygon_field",
    "print_orientation",
    "record_feedback",
    "run_round",
    "select_picks",
    "smax",
    "smin",
    "status",
    "unsupported_area",
    "capillary_length_mm",
    "capillary_transmission",
    "cma_es",
    "Calibration",
    "Evaluator",
    "FeedbackReport",
    "Generator",
    "IterationLog",
    "RequirementFlag",
    "Requirements",
    "Result",
    "calibrate",
    "contact_sheet",
    "corner_proxies",
    "flag_requirement",
    "interpret_note",
    "load_requirements",
    "run",
    "validate_mapping",
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
    "plane_stress_peak",
    "random_search",
    "score_chart",
    "section_properties",
    "overhang_fraction",
    "overhang_project",
    "topopt_2d",
    "topopt_3d",
    "voronoi_lattice",
    "write_iteration",
]

__version__ = "0.2.0"
