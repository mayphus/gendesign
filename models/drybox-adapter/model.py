"""Drybox adapter for gendesign's round runner: a one-gene fit sweep.

Analysis: the pocket target is the calipered pin plus the printed-hole
undersize (0.1–0.2 mm). The PTFE pocket diameter P is the only searched
gene; the score is the distance from that target, and anything drawn
tighter than target - 0.15 mm is infeasible. After a coupon print, write
`- calibrate: fit.undersize_mm = <measured>` in its test.md; the next
`gendesign analyze` moves the target by that amount.

    gendesign round models/drybox-adapter --pop 6 --gens 2
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gendesign.process import Evaluator, Generator  # noqa: E402

class Pocket(Generator):
    name = "pocket"

    def bounds(self):
        return [(8.6, 9.1)]

    def x_from_params(self, params):
        return [float(params.get("pocket_mm", params.get("pocket", 8.85)))]

    def generate(self, x, requirements=None):
        return {"params": {"pocket_mm": round(float(x[0]), 3)}}


class Fit(Evaluator):
    name = "fit"
    objectives = ("fit",)

    def evaluate(self, design, req):
        pocket = design["params"]["pocket_mm"]
        target = float(req.analysis["targets"]["pocket_mm"]["value"])
        floor = target - 0.15
        violation = max(0.0, floor - pocket)
        return {
            "objectives": [-abs(pocket - target)],
            "violation": violation,
            "metrics": {"pocket_mm": pocket, "target_mm": round(target, 3), "feasible": violation <= 0},
            "uncertainties": {"fit": "Printed holes run about 0.1–0.2 mm small. Test-fit a coupon; CAD does not settle it."},
        }


def analyze(req):
    """Pocket target from the measured pin and the printed-hole undersize."""
    c = req.constraints or {}
    pin = float(c.get("pin_mm", 8.7))
    lo, hi = (c.get("print_hole_undersize_mm") or [0.1, 0.2])[:2]
    under = float(req.calibrated("fit.undersize_mm", (float(lo) + float(hi)) / 2))
    target = pin + under
    return {
        "targets": {
            "pocket_mm": {"value": round(target, 3), "from": "constraints.pin_mm + print_hole_undersize_mm",
                          "how": f"{pin} mm pin + {under:.2f} mm printed undersize"},
            "pocket_band_mm": {"value": [round(pin + float(lo), 2), round(pin + float(hi), 2)],
                               "from": "print_hole_undersize_mm", "how": "coupons to print around the target"},
            "cone_floor_deg": {"value": float(c.get("cone_floor_deg", 45)), "from": "constraints.cone_floor_deg",
                               "how": "no flat ledge over the through-bore"},
        },
        "checks": [f"v9 was drawn at {c.get('pocket_mm', 8.85)} mm, inside the band. Fit, not strength, decides this part."],
        "concepts": [
            {"name": "pocket sweep", "verdict": "chosen",
             "why": "One gene (P). A printed coupon settles it faster than any model of the hole."},
            {"name": "topology optimization", "verdict": "rejected",
             "why": "Nothing load-bearing to optimize: the insert sits in a pocket; the risk is tolerance."},
        ],
        "chosen": "pocket sweep",
        "generator": "pocket",
        "open_questions": ["Confirm the insert still does not go straight into the dryer wall hole; then the adapter is unneeded."],
    }


class Drybox:
    default_design = "pocket-sweep"

    def analyze(self, req):
        return analyze(req)

    def generator(self, req):
        return Pocket()

    def evaluators(self, req):
        return [Fit()]

    def export(self, design, out_dir):
        """STEP + STL through CadQuery (needs the `parts` extra)."""
        from generate import Params, generate

        files, stats = generate(Params(pocket=design["params"]["pocket_mm"]), out_dir=str(out_dir))
        return {"files": files, **{k: v for k, v in stats.items() if isinstance(v, (int, float, str, bool))}}

    def preview(self, design, png):
        """Pocket against the measured pin, to scale, with the print-undersize band."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle

        P = design["params"]["pocket_mm"]
        fig, ax = plt.subplots(figsize=(3, 3), dpi=150)
        ax.add_patch(Circle((0, 0), P / 2 + 2.3, color="#e9e4da"))
        ax.add_patch(Circle((0, 0), P / 2, color="white"))
        ax.add_patch(Circle((0, 0), (P - 0.2) / 2, fill=False, ls=":", color="#b0413e", lw=0.8))
        ax.add_patch(Circle((0, 0), 8.7 / 2, fill=False, color="#3b4a5a", lw=1.0))
        ax.set_xlim(-7.5, 7.5)
        ax.set_ylim(-7.5, 7.5)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(f"P {P} mm  (pin 8.7, dotted: printed -0.2)", fontsize=7)
        fig.tight_layout()
        fig.savefig(png)
        plt.close(fig)
        return png


MODEL = Drybox()
