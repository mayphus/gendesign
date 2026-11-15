"""The round runner: a toy model goes through round, status, approve, feedback."""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from gendesign.loop import analyze, approve, generate, report, parse_feedback, record_feedback, run_round, select_picks, status
from gendesign.search import Trial

TOY_MODEL = textwrap.dedent('''
    import numpy as np
    from gendesign.process import Evaluator, Generator

    class Box(Generator):
        name = "box"
        def bounds(self):
            return [(1.0, 5.0), (1.0, 5.0)]
        def generate(self, x, req=None):
            return {"params": {"w": round(float(x[0]), 3), "h": round(float(x[1]), 3)}}
        def x_from_params(self, p):
            return [p["w"], p["h"]]

    class Score(Evaluator):
        name = "score"
        objectives = ("area", "slenderness")
        def evaluate(self, d, req):
            w, h = d["params"]["w"], d["params"]["h"]
            k = req.calibrated("score.k", 1.0)
            return {"objectives": [k * w * h, -(w + h)], "violation": 0.0, "metrics": {"w": w}}

    class Toy:
        default_design = "box"
        def analyze(self, req):
            return {"targets": {"w_max": {"value": 5, "from": "constraints.max_w", "how": "copied"}},
                    "checks": [], "concepts": [{"name": "box", "verdict": "chosen", "why": "only one"}],
                    "chosen": "box", "generator": "box", "open_questions": []}
        def generator(self, req):
            return Box()
        def evaluators(self, req):
            return [Score()]
        def preview(self, d, png):
            from PIL import Image
            Image.new("RGB", (32, 32), "white").save(png)

    MODEL = Toy()
''')

REQ = "name: toy\nunits: mm\npurpose: test\nconstraints:\n  max_w: 5\n"


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model = Path(self.tmp.name) / "toy"
        self.model.mkdir()
        (self.model / "model.py").write_text(TOY_MODEL)
        (self.model / "requirements.yaml").write_text(REQ)
        analyze(self.model)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_writes_record_and_picks(self):
        it = run_round(self.model, pop=8, gens=2, seed=1, export=False, note="first round")
        self.assertEqual(it.name, "00")
        rec = json.loads((it / "round.json").read_text())
        self.assertEqual(rec["objectives"], ["area", "slenderness"])
        self.assertIn("knee", rec["picks"])
        self.assertTrue((it / "picks.png").exists() and (it / "pareto.png").exists())
        self.assertTrue((it / "picks" / "knee" / "params.json").exists())
        text = (it / "decisions.md").read_text()
        self.assertIn("first round", text)
        self.assertIn("_AI: pending._", text)
        # second round continues from the first
        it2 = run_round(self.model, pop=8, gens=1, seed=2, export=False, from_round=it)
        self.assertEqual(it2.name, "01")

    def test_round_needs_an_analysis(self):
        (self.model / "analysis.json").unlink()
        with self.assertRaises(FileNotFoundError):
            run_round(self.model, pop=4, gens=1, export=False)
        a = analyze(self.model)
        self.assertEqual(a["chosen"], "box")
        self.assertIn("w_max", (self.model / "analysis.md").read_text())
        rec = json.loads((run_round(self.model, pop=4, gens=1, export=False) / "round.json").read_text())
        self.assertEqual(rec["analysis"]["targets"], {"w_max": 5})

    def test_status_approve_and_feedback(self):
        it = run_round(self.model, pop=6, gens=1, export=False)
        s = status(self.model)
        self.assertFalse(s["designs"][0]["rounds"][0]["reviewed"])
        approve(it, "knee", note="print one")
        self.assertIn("Approved `knee`", (it / "decisions.md").read_text())
        self.assertEqual(status(self.model)["designs"][0]["rounds"][0]["approved"], ["knee"])

        test_md = it / "picks" / "knee" / "test.md"
        test_md.write_text("- **Printed?** Yes\n- calibrate: score.k = 2 (predicted 1) bench\n")
        record_feedback(test_md)
        self.assertEqual(analyze(self.model)["calibrations"], {"score.k": 2.0})
        it3 = run_round(self.model, pop=6, gens=1, export=False)
        rec = json.loads((it3 / "round.json").read_text())
        self.assertEqual(rec["calibrations"], {"score.k": 2.0})

    def test_report_and_generate(self):
        it = run_round(self.model, pop=6, gens=1, export=False, note="why this round")
        out, rep = generate(self.model, it / "picks" / "knee", Path(self.tmp.name) / "build")
        self.assertTrue((out / "preview.png").exists())
        self.assertEqual(rep["genes_outside_bounds"], [])
        text = report(self.model).read_text()
        for needle in ("## Requirements", "## Analysis", "w_max", "round 00", "picks.png", "#### Owner decision"):
            self.assertIn(needle, text)

    def test_parse_feedback(self):
        fb = parse_feedback(
            "- calibrate: drainage.cd = 0.55 (predicted 0.61) timed 100 ml\n"
            "- requirement: fit.flange_diameter_mm — calipered 44.8, 46 was assumed\n"
            "- Printed? yes\n"
        )
        self.assertEqual(fb["calibrations"][0]["measured"], 0.55)
        self.assertEqual(fb["calibrations"][0]["predicted"], 0.61)
        self.assertEqual(fb["requirement_flags"][0]["field"], "fit.flange_diameter_mm")

    def test_select_picks_knee_and_extremes(self):
        front = [Trial(x=[i], score=0, info={"objectives": [i, 10 - i]}) for i in range(11)]
        picks = select_picks(front, ["a", "b"], k=3)
        self.assertEqual(picks["knee"].info["objectives"], [5, 5])
        self.assertEqual(set(picks), {"knee", "best-a", "best-b"})


if __name__ == "__main__":
    unittest.main()
