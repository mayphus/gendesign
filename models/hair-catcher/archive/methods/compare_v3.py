#!/usr/bin/env python3
import json, re, math
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
OUT = Path(__file__).resolve().parent


def tmin(s):
    h = re.search(r"(\d+)h", s); m = re.search(r"(\d+)m", s); sec = re.search(r"(\d+)s", s)
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0) + (int(sec.group(1)) / 60 if sec else 0)


v3 = json.loads((OUT / "v3-deep-stats.json").read_text())
sm = json.loads((OUT / "smooth-stats.json").read_text())
res = json.loads((OUT / "iterations_deep" / "search-result.json").read_text())
v2r = res["v2"]
s2 = (OUT / "slice-report-smooth.txt").read_text()
v2_time = tmin(re.search(r"time:\s+([^\(]+)", s2).group(1)); v2_g = float(re.search(r"/ ([0-9.]+) g", s2).group(1))
m3 = v3["metrics"]; sl3 = v3["slice"]
rows = [
    ("Open area\n(% of Ø32 disc)", v2r["open_area_pct"], m3["open_area_pct"], "%"),
    ("Total open area", v2r["open_mm2"], m3["open_mm2"], "mm²"),
    ("Max passing ball\n(3-D voxel check)", v3["ball_3d_v2"][0], v3["ball_3d"][0], "mm"),
    ("Depth into drain\n(mesh)", 10.21, -v3["mesh"]["bounds"][0][2], "mm"),
    ("Mass (slicer)", v2_g, float(sl3["filament_g"]), "g"),
    ("Print time\n(PrusaSlicer stand-in)", v2_time, tmin(sl3["time"]), "min"),
    ("Drain est. clean\n(5 mm water)", v2r["q_clean_lpm"], m3["q_clean_lpm"], "L/min"),
    ("Drain est. floor\nholes matted", 0.0, m3["q_floor_blocked_lpm"], "L/min"),
]
fig = plt.figure(figsize=(16, 10), dpi=120)
fig.patch.set_facecolor("#F7F4EF")
for i, (lab, a, b, u) in enumerate(rows):
    ax = fig.add_axes([0.04 + (i % 4) * 0.24, 0.07 + (1 - i // 4) * 0.25, 0.19, 0.17])
    bars = ax.bar(["v2 bowl", "v3 deep"], [a, b], color=["#8A8F96", "#1F6B4A"])
    for bb, val in zip(bars, (a, b)):
        ax.text(bb.get_x() + bb.get_width() / 2, val, f"{val:.1f}" if val < 100 else f"{val:.0f}",
                ha="center", va="bottom", fontsize=10)
    ax.set_title(f"{lab} ({u})", fontsize=10); ax.set_facecolor("#FBFAF8")
    ax.set_ylim(0, max(a, b) * 1.25 + 1e-6); ax.tick_params(labelsize=9)
for j, (img, t) in enumerate(((OUT / "preview-34-smooth.png", "v2 smooth bowl (10.2 mm deep)"),
                             (OUT / "preview-section-v3-deep.png", "v3 deep basket, section"),
                             (OUT / "preview-34-v3-deep.png", "v3 deep basket"))):
    ax = fig.add_axes([0.02 + j * 0.33, 0.58, 0.31, 0.38]); ax.imshow(Image.open(img)); ax.axis("off")
    ax.set_title(t, fontsize=11)
fig.text(0.02, 0.01, "Drain figures are an idealised orifice estimate (Cd 0.6) of what the guard alone can pass; the trap and pipe "
         "usually limit flow first. Print figures: PrusaSlicer 2.9.2, stand-in for OrcaSlicer/Bambu Studio, PLA 0.20 mm.",
         fontsize=9, color="#444")
fig.savefig(OUT / "comparison-v2-vs-v3-deep.png", facecolor=fig.get_facecolor())
print("ok", rows)
