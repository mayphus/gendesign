"""Render top, angled, underside and cut-away previews: python render.py <outdir>"""
import sys
import numpy as np
import pyvista as pv
from PIL import Image

OUT = sys.argv[1]
m = pv.read(f"{OUT}/installed.stl")
views = {
    "top": dict(pos=(0, 0, 80), up=(0, 1, 0)),
    "iso": dict(pos=(55, -55, 50), up=(0, 0, 1)),
    "under": dict(pos=(30, -40, -60), up=(0, 0, 1)),
}
imgs = []
for name, v in views.items():
    p = pv.Plotter(off_screen=True, window_size=(900, 900))
    p.set_background("white")
    p.enable_lightkit() if name == "under" else None
    p.add_mesh(m, color="#f2efe8", smooth_shading=True, specular=0.35, specular_power=20,
               ambient=0.18, diffuse=0.8)
    p.enable_ssao(radius=1.5) if hasattr(p, "enable_ssao") else None
    p.camera_position = [v["pos"], (0, 0, -4.3), v["up"]]
    if name == "top":
        p.enable_parallel_projection(); p.camera.parallel_scale = 25
    else:
        p.camera.zoom(1.25)
    p.screenshot(f"{OUT}/{name}.png")
    imgs.append(Image.open(f"{OUT}/{name}.png"))
    p.close()
# cut-away (half model) to show the graded 3D foam
half = m.clip(normal=(0, 1, 0), origin=(0, 0.5, 0), invert=False)
p = pv.Plotter(off_screen=True, window_size=(900, 900))
p.set_background("white")
p.add_mesh(half, color="#f2efe8", smooth_shading=True, specular=0.3, ambient=0.2)
p.camera_position = [(10, -70, 22), (0, 0, -4.3), (0, 0, 1)]
p.camera.zoom(1.4)
p.screenshot(f"{OUT}/cut.png"); imgs.append(Image.open(f"{OUT}/cut.png")); p.close()
W = Image.new("RGB", (1800, 1800), "white")
for i, im in enumerate(imgs):
    W.paste(im.convert("RGB"), ((i % 2) * 900, (i // 2) * 900))
W.save(f"{OUT}/sheet.png")
