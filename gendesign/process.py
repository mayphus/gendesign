"""The process: generators, evaluators, a seeded search, a result, feedback.

Objectives are maximized. A constraint violation of 0 is feasible. A
generator parameter that only changes shape is not an objective. Feedback
either calibrates an evaluator or flags a requirement. Those are different
paths.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class Generator:
    """bounds() is a sequence of (lo, hi). generate(x) returns a design dict."""

    name = "generator"

    def bounds(self):
        raise NotImplementedError

    def generate(self, x, requirements) -> dict:
        raise NotImplementedError


class Evaluator:
    """evaluate(design) returns objectives, violation, metrics, uncertainties."""

    name = "evaluator"
    objectives: tuple = ()  # names of the objectives this evaluator returns, in order

    def evaluate(self, design, requirements) -> dict:
        raise NotImplementedError


@dataclass
class Calibration:
    """A measured print correcting an evaluator. Does not edit requirements."""

    evaluator: str
    parameter: str
    measured: float | str
    predicted: float | str | None = None
    note: str = ""


@dataclass
class RequirementFlag:
    """The rare path: the input itself was wrong."""

    field: str
    reason: str


@dataclass
class FeedbackReport:
    calibrations: list
    requirement_flags: list


@dataclass
class Result:
    pareto: list
    trials: list
    config: dict
    uncertainties: dict = field(default_factory=dict)
    reasons: str = ""
    history: list = field(default_factory=list)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": self.config,
            "reasons": self.reasons,
            "uncertainties": self.uncertainties,
            "pareto": [_public_trial(t) for t in self.pareto],
        }
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path


def _public_trial(trial):
    info = dict(getattr(trial, "info", {}) or {})
    info.pop("objectives", None)
    return {"x": [float(v) for v in trial.x], "score": float(trial.score), "info": info}


def _combine(generator, evaluators, requirements):
    def fun(x):
        design = generator.generate(x, requirements)
        objectives = []
        violation = 0.0
        metrics = {"params": design.get("params") or {}}
        uncertainties = {}
        for ev in evaluators:
            out = ev.evaluate(design, requirements)
            objectives.extend(out.get("objectives") or [])
            violation += float(out.get("violation") or 0.0)
            metrics.update(out.get("metrics") or {})
            uncertainties.update(out.get("uncertainties") or {})
        metrics["uncertainties"] = uncertainties
        metrics["objectives"] = [float(v) for v in objectives]
        return {"objectives": objectives, "violation": violation, "info": metrics}

    return fun


def run(generator, evaluators, requirements, *, method="nsga2", pop=12, gens=4, seed=0, n_each=5, x0=None):
    """Seeded search. method is nsga2 or grid. The config is part of the result."""
    from .search import nsga2

    bounds = list(generator.bounds())
    fun = _combine(generator, evaluators, requirements)
    if method == "grid":
        found = _grid(fun, bounds, n_each=n_each)
    elif method == "nsga2":
        found = nsga2(fun, bounds, pop=pop, gens=gens, seed=seed, x0=x0)
    else:
        raise ValueError(f"unknown search method {method}")
    raw_front = list(getattr(found, "front", None) or found.trials)
    front = [t for t in raw_front if (t.info or {}).get("feasible", True)]
    if not front:
        front = list(raw_front[:1])
    uncertainties = {}
    for t in front:
        uncertainties.update((t.info or {}).get("uncertainties") or {})
    config = {
        "seed": seed,
        "method": method,
        "pop": pop,
        "gens": gens,
        "n_each": n_each,
        "generator": generator.name,
        "evaluators": [e.name for e in evaluators],
        "bounds": [[float(a), float(b)] for a, b in bounds],
        "requirements": getattr(requirements, "name", None),
    }
    reasons = _reasons(front)
    return Result(
        pareto=front,
        trials=list(getattr(found, "trials", [])),
        config=config,
        uncertainties=uncertainties,
        reasons=reasons,
        history=list(getattr(found, "history", []) or []),
    )


def _grid(fun, bounds, n_each):
    """Grid over the bounds. Keeps the full objective vector on each trial."""
    from .search import Trial, SearchResult
    import numpy as np

    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    axes = [np.linspace(a, b, n_each) for a, b in zip(lo, hi)]
    trials = []
    best = None
    for pts in np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(bounds), -1).T:
        out = fun(pts)
        info = dict(out.get("info") or {})
        score = float(sum(out["objectives"])) if out.get("violation", 0) <= 0 else -1e6
        t = Trial(np.asarray(pts, dtype=float), score, info)
        trials.append(t)
        if best is None or t.score > best.score:
            best = t
    return SearchResult(best, trials, "grid")


def _reasons(front):
    if not front:
        return "No feasible design."
    lines = []
    for t in front[:6]:
        info = t.info or {}
        params = info.get("params") or {}
        bits = [f"{k}={v}" for k, v in list(params.items())[:6]]
        lines.append(", ".join(bits) if bits else "unlabeled")
    return "Pareto candidates: " + "; ".join(lines)


def calibrate(evaluator: str, parameter: str, measured, predicted=None, note: str = "") -> Calibration:
    return Calibration(evaluator, parameter, measured, predicted, note)


def flag_requirement(field: str, reason: str) -> RequirementFlag:
    return RequirementFlag(field, reason)


def interpret_note(text: str) -> FeedbackReport:
    """Split a test note into model corrections and requirement flags.

    A printed measurement corrects an evaluator. Wording that the input was
    assumed, or that a requirement was wrong, is the rare path back to
    requirements. This does not edit the requirements file.
    """
    calibrations = []
    flags = []
    low = text.lower()
    if "printed?" in low and "yes" in low:
        calibrations.append(calibrate("process", "from-test", measured="see test.md", note=text.strip().splitlines()[0][:160]))
    if "requirement was wrong" in low or "assumed, not measured" in low:
        flags.append(flag_requirement("see note", "The note says an input was assumed or a requirement was wrong."))
    return FeedbackReport(calibrations, flags)
