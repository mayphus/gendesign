"""Stable process interfaces: requirements, search, and the two feedback paths."""
from __future__ import annotations

import unittest
from pathlib import Path

from gendesign.process import Generator, Evaluator, interpret_note, run
from gendesign.requirements import load_requirements, validate_mapping

ROOT = Path(__file__).resolve().parents[1]


class ToyGenerator(Generator):
    name = "toy"

    def bounds(self):
        return [(0.0, 1.0)]

    def generate(self, x, requirements):
        return {"params": {"x": float(x[0])}}


class ToyEvaluator(Evaluator):
    name = "value"

    def evaluate(self, design, requirements):
        x = design["params"]["x"]
        return {
            "objectives": [-(x - 0.3) ** 2],
            "violation": 0.0,
            "metrics": {"x": x, "feasible": True},
            "uncertainties": {"value": "toy quadratic, not a physical model"},
        }


class ProcessTests(unittest.TestCase):
    def test_schema_accepts_the_examples(self):
        for rel in ("models/hair-catcher/requirements.yaml", "templates/model/requirements.yaml"):
            req = load_requirements(ROOT / rel)
            self.assertEqual(req.errors, [], rel)
            self.assertTrue(req.ok)

    def test_schema_rejects_a_file_with_no_units(self):
        errors = validate_mapping({"name": "x", "purpose": "y", "constraints": {}})
        self.assertTrue(any("units" in e for e in errors))

    def test_seeded_search_is_repeatable_and_logs_config(self):
        from gendesign.requirements import Requirements

        req = Requirements("toy", "mm", "a test", {}, {"name": "toy", "units": "mm", "purpose": "a test", "constraints": {}})
        a = run(ToyGenerator(), [ToyEvaluator()], req, method="nsga2", pop=8, gens=2, seed=3)
        b = run(ToyGenerator(), [ToyEvaluator()], req, method="nsga2", pop=8, gens=2, seed=3)
        self.assertEqual(a.config["seed"], 3)
        self.assertEqual(a.config["generator"], "toy")
        self.assertEqual([round(t.x[0], 6) for t in a.trials], [round(t.x[0], 6) for t in b.trials])
        self.assertIn("toy quadratic", a.uncertainties["value"])

    def test_feedback_splits_model_correction_from_a_wrong_requirement(self):
        note = "Printed? Yes.\nThe flange diameter was assumed, not measured.\n"
        report = interpret_note(note)
        self.assertTrue(report.calibrations)
        self.assertTrue(report.requirement_flags)
        # Interpreting a note must not invent a requirements edit.
        self.assertFalse(hasattr(report, "rewritten_requirements"))


if __name__ == "__main__":
    unittest.main()
