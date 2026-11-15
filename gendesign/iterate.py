"""First-class design iteration logs.

Layout (under a saved design folder, e.g. models/hair-catcher/designs/smooth-v2/):

    design.json
    iterations/00/
        params.json
        stats.json
        critique.md      # one line: what failed, and the next change
        preview.png      # and any other renders
        test.md          # after a physical print: printed?, settings,
                         # measured vs designed, fit/function, photos,
                         # failure notes, next change
        diff.patch       # optional code/params diff from the previous round
    iterations/01/
    ...
    docs or the design folder may also hold contact-sheet.png, evolution.gif,
    and score-chart.png built by the helpers below.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def _design_root(path) -> Path:
    p = Path(path)
    if (p / "iterations").is_dir() or (p / "design.json").exists() or p.name == "iterations":
        return p if p.name != "iterations" else p.parent
    return p


def iterations_dir(design_dir) -> Path:
    d = _design_root(design_dir) / "iterations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_round_dirs(design_dir) -> list[Path]:
    it = iterations_dir(design_dir)
    rounds = [p for p in it.iterdir() if p.is_dir() and p.name.isdigit()]
    return sorted(rounds, key=lambda p: int(p.name))


def next_index(design_dir) -> str:
    existing = [int(p.name) for p in list_round_dirs(design_dir)]
    n = (max(existing) + 1) if existing else 0
    return f"{n:02d}"


def write_iteration(
    design_dir,
    *,
    params=None,
    stats=None,
    critique: str = "",
    next_step: str = "",
    preview=None,
    renders=None,
    code_diff: str | None = None,
    index: str | None = None,
) -> Path:
    """Record one design round. `preview` / `renders` are image paths to copy in."""
    idx = index or next_index(design_dir)
    dest = iterations_dir(design_dir) / idx
    dest.mkdir(parents=True, exist_ok=True)
    if params is not None:
        (dest / "params.json").write_text(json.dumps(params, indent=2, default=str))
    if stats is not None:
        (dest / "stats.json").write_text(json.dumps(stats, indent=2, default=str))
    body = critique.rstrip() + "\n"
    if next_step:
        body += "\n## Next step\n\n" + next_step.rstrip() + "\n"
    (dest / "critique.md").write_text(body)
    if code_diff:
        (dest / "diff.patch").write_text(code_diff if isinstance(code_diff, str) else str(code_diff))
    renders = list(renders or [])
    if preview:
        renders = [preview] + renders
    for i, src in enumerate(renders):
        src = Path(src)
        if not src.exists():
            continue
        name = "preview.png" if i == 0 else src.name
        shutil.copy2(src, dest / name)
    return dest


def load_iterations(design_dir) -> list[dict]:
    rows = []
    for d in list_round_dirs(design_dir):
        row = {"index": d.name, "path": str(d)}
        for fn, key in (("params.json", "params"), ("stats.json", "stats")):
            p = d / fn
            if p.exists():
                try:
                    row[key] = json.loads(p.read_text())
                except Exception:
                    row[key] = None
        c = d / "critique.md"
        if c.exists():
            row["critique"] = c.read_text()
        imgs = sorted([*d.glob("*.png"), *d.glob("*.jpg"), *d.glob("*.gif")])
        row["images"] = [str(x) for x in imgs]
        rows.append(row)
    return rows


def _score_of(row, key="score"):
    stats = row.get("stats") or {}
    if key in stats:
        return stats[key]
    # nested
    for v in stats.values():
        if isinstance(v, dict) and key in v:
            return v[key]
    return None


def contact_sheet(design_dir, out_path=None, cols: int = 5, thumb: int = 280, title: str | None = None):
    from PIL import Image, ImageDraw, ImageFont

    rows = load_iterations(design_dir)
    images = []
    labels = []
    for r in rows:
        img = None
        for p in r.get("images") or []:
            if p.lower().endswith((".png", ".jpg", ".jpeg")):
                img = p
                break
        if img:
            images.append(Image.open(img).convert("RGB"))
            sc = _score_of(r)
            labels.append(f"{r['index']}" + (f"  score {sc:.3f}" if isinstance(sc, (int, float)) else ""))
    if not images:
        raise RuntimeError(f"no iteration images under {design_dir}")
    w = thumb
    thumbs = []
    for im in images:
        t = im.copy()
        t.thumbnail((w, w))
        canvas = Image.new("RGB", (w, w), (247, 244, 239))
        canvas.paste(t, ((w - t.size[0]) // 2, (w - t.size[1]) // 2))
        thumbs.append(canvas)
    cols = max(1, min(cols, len(thumbs)))
    nrows = (len(thumbs) + cols - 1) // cols
    header = 36 if title else 8
    footer = 22
    sheet = Image.new("RGB", (cols * w + 8, header + nrows * (w + footer) + 8), (247, 244, 239))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
        font_t = ImageFont.truetype("DejaVuSans.ttf", 18)
    except Exception:
        font = font_t = ImageFont.load_default()
    if title:
        draw.text((8, 8), title, fill=(30, 30, 30), font=font_t)
    for i, (th, lab) in enumerate(zip(thumbs, labels)):
        r, c = divmod(i, cols)
        x, y = 4 + c * w, header + r * (w + footer)
        sheet.paste(th, (x, y))
        draw.text((x + 4, y + w + 2), lab, fill=(40, 40, 40), font=font)
    out = Path(out_path) if out_path else _design_root(design_dir) / "contact-sheet.png"
    sheet.save(out)
    return out


def evolution_gif(design_dir, out_path=None, duration_ms: int = 500, size=400):
    from PIL import Image

    rows = load_iterations(design_dir)
    frames = []
    for r in rows:
        imgs = [p for p in r.get("images") or [] if p.lower().endswith((".png", ".jpg", ".jpeg"))]
        if not imgs:
            continue
        im = Image.open(imgs[0]).convert("RGB")
        im.thumbnail((size, size))
        canvas = Image.new("RGB", (size, size), (247, 244, 239))
        canvas.paste(im, ((size - im.size[0]) // 2, (size - im.size[1]) // 2))
        frames.append(canvas)
    if not frames:
        raise RuntimeError(f"no iteration images under {design_dir}")
    out = Path(out_path) if out_path else _design_root(design_dir) / "evolution.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=duration_ms, loop=0)
    return out


class IterationLog:
    """The iteration folder for one design. Feedback notes land here too."""

    def __init__(self, design_dir):
        self.design_dir = Path(design_dir)

    def write(self, **kwargs):
        return write_iteration(self.design_dir, **kwargs)

    def sheet(self, **kwargs):
        return contact_sheet(self.design_dir, **kwargs)

    def gif(self, **kwargs):
        return evolution_gif(self.design_dir, **kwargs)

    def chart(self, **kwargs):
        return score_chart(self.design_dir, **kwargs)


def score_chart(design_dir, out_path=None, score_key: str = "score", title: str | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = load_iterations(design_dir)
    xs, ys = [], []
    for r in rows:
        s = _score_of(r, score_key)
        if s is not None:
            xs.append(int(r["index"]))
            ys.append(float(s))
    if not xs:
        raise RuntimeError(f"no '{score_key}' values in iteration stats under {design_dir}")
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
    ax.plot(xs, ys, "-o", color="#1F6B4A")
    ax.set_xlabel("iteration")
    ax.set_ylabel(score_key)
    ax.set_title(title or f"{score_key} over iterations")
    ax.set_facecolor("#FBFAF8")
    fig.patch.set_facecolor("#F7F4EF")
    fig.tight_layout()
    out = Path(out_path) if out_path else _design_root(design_dir) / "score-chart.png"
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out
