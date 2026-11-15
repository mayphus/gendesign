"""3-D preview of a part: top, 3/4, underside and a half-section on one sheet.

    from gendesign.render import preview_sheet
    preview_sheet("installed.stl", "preview-3d.png", title="round 01 knee")

Off-screen PyVista (the `parts` extra). Installed orientation: +z up, the
part centred on the origin.
"""
from __future__ import annotations

from pathlib import Path


def preview_sheet(mesh_path, png, *, title=None, size=700, color="#ece6da"):
    import numpy as np
    import pyvista as pv
    from PIL import Image, ImageDraw, ImageFont

    m = pv.read(str(mesh_path))
    lo, hi = np.array(m.bounds[0::2]), np.array(m.bounds[1::2])
    c = (lo + hi) / 2
    r = float(np.linalg.norm(hi - lo)) / 2
    views = [
        ("top", (c[0], c[1], c[2] + 4 * r), (0, 1, 0), m),
        ("3/4", (c[0] + 2.2 * r, c[1] - 2.2 * r, c[2] + 1.8 * r), (0, 0, 1), m),
        ("underside", (c[0] + 1.4 * r, c[1] - 1.8 * r, c[2] - 2.4 * r), (0, 0, 1), m),
        ("section", (c[0] + 0.3 * r, c[1] - 3.2 * r, c[2] + 1.0 * r), (0, 0, 1),
         m.clip(normal=(0, 1, 0), origin=tuple(c), invert=False)),
    ]
    tiles = []
    for name, pos, up, mesh in views:
        p = pv.Plotter(off_screen=True, window_size=(size, size))
        p.set_background("white")
        p.add_mesh(mesh, color=color, smooth_shading=True, specular=0.3, specular_power=20, ambient=0.2, diffuse=0.8)
        p.camera_position = [pos, tuple(c), up]
        if name == "top":
            p.enable_parallel_projection()
            p.camera.parallel_scale = r * 0.78
        else:
            p.camera.zoom(1.15 if name != "section" else 1.3)
        img = Image.fromarray(p.screenshot(return_img=True))
        p.close()
        d = ImageDraw.Draw(img)
        d.text((10, 8), name, fill=(90, 90, 90), font=ImageFont.load_default())
        tiles.append(img)
    head = 30 if title else 0
    sheet = Image.new("RGB", (2 * size, 2 * size + head), "white")
    if title:
        ImageDraw.Draw(sheet).text((10, 8), title, fill=(30, 30, 30), font=ImageFont.load_default())
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * size, head + (i // 2) * size))
    png = Path(png)
    sheet.save(png)
    return png
