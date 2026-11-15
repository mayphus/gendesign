"""example-model for gendesign. Fill in the four parts in this order.

1. analyze(req): requirements -> design targets and a concept, before any geometry
2. a Generator that implements the chosen concept
3. Evaluators: each objective or check comes from a target in the analysis
4. export and preview, so a pick can be reviewed and printed

    gendesign analyze models/example-model
    gendesign round   models/example-model
    gendesign report  models/example-model
"""
from __future__ import annotations

from gendesign.process import Evaluator, Generator


def analyze(req):
    """Derive targets from requirements.yaml. Say where each number came from."""
    c = req.constraints or {}
    return {
        "targets": {
            # "open_area_min_mm2": {"value": 408, "from": "function.flow", "how": "A = Q / (Cd sqrt(2 g h))"},
        },
        "checks": ["Which requirement binds, and which has margin."],
        "concepts": [
            {"name": "concept A", "verdict": "chosen", "why": "Why it meets the targets."},
            {"name": "concept B", "verdict": "rejected", "why": "Which target it misses."},
        ],
        "chosen": "concept A",
        "generator": "example",
        "open_questions": ["Every number in requirements.yaml that was assumed, not measured."],
    }


class Example(Generator):
    name = "example"

    def bounds(self):
        return [(1.0, 10.0)]

    def x_from_params(self, params):
        return [params["size_mm"]]

    def generate(self, x, req=None):
        return {"params": {"size_mm": round(float(x[0]), 3)}}


class Check(Evaluator):
    name = "check"
    objectives = ("score",)

    def evaluate(self, design, req):
        size = design["params"]["size_mm"]
        return {"objectives": [-abs(size - 5.0)], "violation": 0.0, "metrics": {"size_mm": size},
                "uncertainties": {"check": "What this evaluator does not know."}}


class ExampleModel:
    default_design = "example"

    def analyze(self, req):
        return analyze(req)

    def generator(self, req):
        return Example()

    def evaluators(self, req):
        return [Check()]

    def export(self, design, out_dir):
        """Write the print files into out_dir and return a mesh report
        (watertight, bodies, volume_mm3, unsupported). See gendesign.field."""
        return {}

    def preview(self, design, png):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(3, 3), dpi=120)
        ax.text(0.5, 0.5, f"size {design['params']['size_mm']} mm", ha="center")
        ax.axis("off")
        fig.savefig(png)
        plt.close(fig)
        return png


MODEL = ExampleModel()
