"""Cantilever bracket: topology optimization as the round generator.

Genes are volume fraction, filter radius (mm), and tip-load height on the
right edge. Each candidate runs 2-D SIMP; evaluators score stiffness and
lightness, and flag unsupported material when printing edge-on.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from gendesign.process import Evaluator, Generator
from gendesign.topopt2d import (
    export_density_stl,
    overhang_fraction,
    topopt_2d,
    _save_density_image,
)

# Coarse mesh for round search (each gene vector runs a full SIMP solve).
NELX, NELY, NITER = 30, 10, 20
BOUNDS = {
    "volfrac": (0.20, 0.40),
    "rmin_mm": (2.0, 5.0),
    "load_y_frac": (0.30, 0.70),
}


def _fit(req):
    return req.section("fit")


def _con(req, key, default):
    return float((req.constraints or {}).get(key, default))


def _geom(req):
    f = _fit(req)
    return {
        "L": float(f.get("length_mm", 120.0)),
        "H": float(f.get("height_mm", 40.0)),
        "t": float(f.get("thickness_mm", 5.0)),
        "bolt_d": float(f.get("bolt_diameter_mm", 8.0)),
        "bolt_cx": float(f.get("bolt_cx_mm", 10.0)),
        "bolt_cy": [float(v) for v in (f.get("bolt_cy_mm") or [10.0, 30.0])],
        "washer": float(f.get("washer_extra_mm", 3.0)),
    }


def _node(nelx, nely, ix, iy):
    return ix * (nely + 1) + iy


def _bolt_masks(nelx, nely, g):
    dx, dy = g["L"] / nelx, g["H"] / nely
    xs = (np.arange(nelx) + 0.5) * dx
    ys = (np.arange(nely) + 0.5) * dy
    X, Y = np.meshgrid(xs, ys)
    r_hole = g["bolt_d"] / 2.0
    r_washer = r_hole + g["washer"]
    void = np.zeros((nely, nelx), dtype=bool)
    solid = np.zeros((nely, nelx), dtype=bool)
    for cy in g["bolt_cy"]:
        r = np.hypot(X - g["bolt_cx"], Y - cy)
        void |= r <= r_hole
        solid |= (r > r_hole) & (r <= r_washer)
    solid &= ~void
    return solid, void


def _bolt_fixed(nelx, nely, g):
    dx, dy = g["L"] / nelx, g["H"] / nely
    r_hole = g["bolt_d"] / 2.0
    band = 0.6 * max(dx, dy)
    fixed = []
    for ix in range(nelx + 1):
        for iy in range(nely + 1):
            x, y = ix * dx, iy * dy
            for cy in g["bolt_cy"]:
                if abs(np.hypot(x - g["bolt_cx"], y - cy) - r_hole) <= band:
                    n = _node(nelx, nely, ix, iy)
                    fixed.append((n, 0))
                    fixed.append((n, 1))
    return list({(n, d) for n, d in fixed})


def _tip_load(nelx, nely, load_y_frac):
    iy = int(round(float(load_y_frac) * nely))
    iy = max(0, min(nely, iy))
    return [(_node(nelx, nely, nelx, iy), 1, -1.0)]


def analyze(req):
    g = _geom(req)
    c = req.constraints or {}
    phys = req.section("physics")
    fn = req.section("function")
    vol_max = float(c.get("volfrac_max", 0.40))
    print_flat = bool(fn.get("print_flat", True))
    F = float(fn.get("tip_load_N", c.get("tip_load_N", 50.0)))
    return {
        "targets": {
            "tip_load_N": {
                "value": F,
                "from": "function.tip_load_N",
                "how": "stated design load at the right edge",
            },
            "volfrac_max": {
                "value": vol_max,
                "from": "constraints.volfrac_max",
                "how": "SIMP volume upper bound; gene volfrac searches under this",
            },
            "min_feature_mm": {
                "value": float(c.get("rmin_mm_min", 2.0)),
                "from": "constraints.rmin_mm_min",
                "how": "density-filter radius sets minimum member width",
            },
            "domain_mm": {
                "value": [g["L"], g["H"], g["t"]],
                "from": "fit.length/height/thickness_mm",
                "how": "rectangular design space around two left bolt holes",
            },
        },
        "checks": [
            f"Load {F:.0f} N binds the layout; volume ≤ {vol_max:.0%} trades mass against stiffness.",
            f"Steel E={float(phys.get('E_GPa', 200))} GPa, σ_y≈{float(phys.get('sigma_y_MPa', 250))} MPa "
            "(yield not constrained in this round).",
            "Print flat (thickness = build Z): in-plane overhang filter off."
            if print_flat
            else "Print edge-on: SIMP uses the +y self-supporting overhang projection.",
        ],
        "concepts": [
            {
                "name": "2-D SIMP topology",
                "verdict": "chosen",
                "why": "Free material layout inside the rectangle under the bolt BCs and tip load; "
                "genes are volfrac, filter radius, and load height.",
            },
            {
                "name": "parametric two-bar truss",
                "verdict": "rejected",
                "why": "Assumes the load path shape; cannot discover bolt pads or branching members.",
            },
        ],
        "chosen": "2-D SIMP topology",
        "generator": "topopt-bracket",
        "open_questions": list(req.raw.get("open_questions") or []),
    }


class TopOptBracket(Generator):
    """SIMP cantilever bracket. Genes: volfrac, rmin_mm, load_y_frac."""

    name = "topopt-bracket"

    def __init__(self, req=None, *, nelx=NELX, nely=NELY, niter=NITER):
        self.req = req
        self.nelx = int(nelx)
        self.nely = int(nely)
        self.niter = int(niter)

    def bounds(self):
        c = (self.req.constraints if self.req else None) or {}
        return [
            (float(c.get("volfrac_min", BOUNDS["volfrac"][0])), float(c.get("volfrac_max", BOUNDS["volfrac"][1]))),
            (float(c.get("rmin_mm_min", BOUNDS["rmin_mm"][0])), float(c.get("rmin_mm_max", BOUNDS["rmin_mm"][1]))),
            BOUNDS["load_y_frac"],
        ]

    def params_from_x(self, x):
        return {
            "volfrac": round(float(x[0]), 4),
            "rmin_mm": round(float(x[1]), 3),
            "load_y_frac": round(float(x[2]), 4),
            "nelx": self.nelx,
            "nely": self.nely,
            "niter": self.niter,
        }

    def x_from_params(self, params):
        return [float(params["volfrac"]), float(params["rmin_mm"]), float(params["load_y_frac"])]

    def generate(self, x, requirements=None):
        req = requirements or self.req
        params = self.params_from_x(x)
        g = _geom(req)
        dx = g["L"] / self.nelx
        rmin = max(1.2, params["rmin_mm"] / dx)
        solid, void = _bolt_masks(self.nelx, self.nely, g)
        fixed = _bolt_fixed(self.nelx, self.nely, g)
        loads = _tip_load(self.nelx, self.nely, params["load_y_frac"])
        print_flat = bool((req.section("function") if req else {}).get("print_flat", True))
        res = topopt_2d(
            nelx=self.nelx,
            nely=self.nely,
            volfrac=params["volfrac"],
            penal=3.0,
            rmin=rmin,
            niter=self.niter,
            E0=1.0,
            Emin=1e-9,
            nu=float((req.section("physics") if req else {}).get("nu", 0.3)),
            passive_solid=solid,
            passive_void=void,
            fixed=fixed,
            loads=loads,
            overhang=not print_flat,
            verbose=False,
        )
        c_final = float(res.compliance[-1]) if res.compliance else float("inf")
        v_final = float(res.volume[-1]) if res.volume else float(params["volfrac"])
        return {
            "params": {
                **params,
                "rmin_elem": round(rmin, 3),
                "compliance": round(c_final, 6),
                "volume": round(v_final, 4),
                "overhang_frac": round(overhang_fraction(res.density), 4),
                "print_flat": print_flat,
                "L_mm": g["L"],
                "H_mm": g["H"],
                "thickness_mm": g["t"],
            },
            "density": res.density,
        }


class StiffnessMass(Evaluator):
    """Maximize stiffness (−compliance) and lightness (−volume)."""

    name = "stiffness-mass"
    objectives = ("stiffness", "lightness")

    def evaluate(self, design, req):
        p = design["params"]
        c = float(p.get("compliance", 1e9))
        v = float(p.get("volume", 1.0))
        return {
            "objectives": [-c, -v],
            "violation": 0.0,
            "metrics": {"compliance": c, "volume": v, "volfrac_gene": p.get("volfrac")},
            "uncertainties": {
                "stiffness-mass": "Compliance from unit-E SIMP FEA; ranks layouts, not physical tip deflection. "
                "Yield is not checked."
            },
        }


class PrintSupport(Evaluator):
    """Constraint: unsupported solid fraction when printing edge-on."""

    name = "print-support"
    objectives = ()

    def evaluate(self, design, req):
        p = design["params"]
        frac = float(p.get("overhang_frac", 0.0))
        limit = _con(req, "max_overhang_frac", 0.05)
        if p.get("print_flat", True):
            return {
                "objectives": [],
                "violation": 0.0,
                "metrics": {"overhang_frac": frac, "print_flat": True},
                "uncertainties": {
                    "print-support": "Flat print: in-plane overhang not binding. Edge-on would use the AM filter."
                },
            }
        return {
            "objectives": [],
            "violation": max(0.0, frac - limit),
            "metrics": {"overhang_frac": frac, "overhang_limit": limit, "print_flat": False},
            "uncertainties": {
                "print-support": "45° grid support proxy on the density field; not a slicer overhang report."
            },
        }


class CantileverBracket:
    default_design = "topopt-bracket"

    def analyze(self, req):
        return analyze(req)

    def generator(self, req):
        return TopOptBracket(req)

    def evaluators(self, req):
        return [StiffnessMass(), PrintSupport()]

    def export(self, design, out_dir):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        dens = design.get("density")
        p = design["params"]
        if dens is None:
            return {"error": "no density field"}
        np.save(out / "density.npy", dens)
        _save_density_image(dens, out / "density.png")
        pixel = float(p["L_mm"]) / int(p["nelx"])
        try:
            # part.stl / print.stl only — skip installed.stl so the round does not
            # invoke PyVista's 3-D sheet (unnecessary for a flat 2-D topology).
            export_density_stl(
                dens,
                out / "part.stl",
                pixel_mm=pixel,
                thickness_mm=float(p["thickness_mm"]),
                threshold=0.5,
            )
            import shutil

            shutil.copy(out / "part.stl", out / "print.stl")
            from gendesign.evaluate import evaluate_mesh

            rep = evaluate_mesh(out / "print.stl")
            rep["bodies"] = 1
            return rep
        except Exception as e:
            (out / "export_error.txt").write_text(str(e))
            return {"error": str(e), "watertight": False}

    def preview(self, design, png):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, FancyArrowPatch

        dens = design["density"]
        p = design["params"]
        L, H = float(p["L_mm"]), float(p["H_mm"])
        fig, ax = plt.subplots(figsize=(8, 2.8), dpi=120)
        ax.imshow(1.0 - dens, cmap="gray", origin="lower", extent=[0, L, 0, H], vmin=0, vmax=1, aspect="equal")
        for cy in (10.0, 30.0):
            ax.add_patch(Circle((10.0, cy), 4.0, fill=False, ec="#c0392b", lw=1.2))
        y_load = float(p["load_y_frac"]) * H
        ax.add_patch(
            FancyArrowPatch(
                (L + 2, y_load + 6),
                (L + 2, y_load - 1),
                arrowstyle="-|>",
                mutation_scale=12,
                color="#c0392b",
            )
        )
        ax.set_xlim(-2, L + 16)
        ax.set_ylim(-2, H + 2)
        ax.set_title(
            f"vol={p['volume']:.2f}  c={p['compliance']:.3g}  rmin={p['rmin_mm']} mm",
            fontsize=9,
        )
        ax.set_xlabel("mm")
        ax.set_aspect("equal")
        fig.tight_layout()
        Path(png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return png


MODEL = CantileverBracket()
