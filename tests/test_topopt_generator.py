"""Topology optimization as a round Generator (cantilever bracket)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from gendesign.loop import analyze, run_round
from gendesign.topopt2d import overhang_fraction, overhang_project, topopt_2d


class OverhangFilterTest(unittest.TestCase):
    def test_floating_blob_is_removed(self):
        x = np.zeros((6, 8))
        x[0, :] = 1.0  # build plate row
        x[4, 3:5] = 1.0  # floating
        y = overhang_project(x)
        self.assertLess(y[4].max(), 0.05)
        self.assertGreater(y[0].mean(), 0.9)

    def test_supported_column_survives(self):
        x = np.zeros((5, 5))
        x[:, 2] = 1.0
        y = overhang_project(x)
        self.assertGreater(y[:, 2].min(), 0.9)

    def test_overhang_fraction(self):
        x = np.zeros((4, 4))
        x[0, 1] = 1.0
        x[2, 1] = 1.0  # unsupported
        self.assertGreater(overhang_fraction(x), 0.0)


class TopOptRoundTest(unittest.TestCase):
    def test_analyze_and_tiny_round(self):
        import shutil

        src = Path(__file__).resolve().parents[1] / "models" / "cantilever-bracket"
        self.assertTrue((src / "model.py").exists())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cantilever-bracket"
            shutil.copytree(src, root, ignore=shutil.ignore_patterns("designs", "analysis.*", "REPORT.md"))
            a = analyze(root)
            self.assertEqual(a["generator"], "topopt-bracket")
            self.assertIn("volfrac_max", a["targets"])

            # Tiny search; export=False avoids PyVista 3-D preview (can segfault headless).
            it = run_round(root, pop=2, gens=1, seed=0, export=False, note="pytest topopt round")
            rec = json.loads((it / "round.json").read_text())
            self.assertEqual(rec["objectives"], ["stiffness", "lightness"])
            self.assertIn("knee", rec["picks"])
            knee = it / "picks" / "knee"
            self.assertTrue((knee / "params.json").exists())
            self.assertTrue((knee / "preview.png").exists())
            params = json.loads((knee / "params.json").read_text())
            self.assertIn("volfrac", params)
            self.assertIn("compliance", params)

            from gendesign.loop import load_model, load_model_requirements

            model = load_model(root)
            req = load_model_requirements(root)
            gen = model.generator(req)
            design = gen.generate(gen.x_from_params(params), req)
            self.assertEqual(design["density"].shape, (10, 30))
            out = Path(tmp) / "export"
            rep = model.export(design, out)
            self.assertTrue((out / "density.npy").exists())
            self.assertIn("volume_mm3", rep)


class TopOptSolverSmoke(unittest.TestCase):
    def test_overhang_flag_runs(self):
        res = topopt_2d(nelx=12, nely=4, volfrac=0.4, niter=5, rmin=1.5, overhang=True, verbose=False)
        self.assertEqual(res.density.shape, (4, 12))
        self.assertTrue(res.info.get("overhang"))


if __name__ == "__main__":
    unittest.main()
