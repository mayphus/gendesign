"""The AI + generative design loop, as code.

    requirements ─► analysis ─► round (generate + search) ─► picks ─► AI review
         ▲          (targets,          ▲                                 │
         │ rare      concept)          │ calibrations                    ▼
    requirement flag ◄──── test.md feedback ◄──── print ◄──── owner approves a pick

A model folder (`models/<name>/`) holds `requirements.yaml` and `model.py`.
`model.py` exposes `MODEL`, an object with:

    analyze(req) -> dict                  targets, checks, concepts, chosen generator
    generator(req) -> Generator           bounds() and generate(x, req)
    evaluators(req) -> [Evaluator]        each declares `objectives` names
    preview(design, png_path)             fast top-view render of a design
    export(design, out_dir) -> dict       mesh files + mesh report (optional)
    default_design: str                   designs/<name>/ the rounds go into

Every round writes `designs/<design>/iterations/NN/`:

    round.json      seed, config, search history, the whole front
    pareto.png      the front on the first two objectives
    picks.png       contact sheet of the picks, labelled with scores
    picks/<pick>/   params.json, stats.json, preview.png, mesh files
    decisions.md    what changed, result table, AI review, owner decision

The AI fills in the review sections of decisions.md. Only the owner runs
`gendesign approve`. Nothing here starts a print.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np

from .iterate import list_round_dirs, next_index
from .process import run as process_run
from .requirements import load_requirements

PENDING_REVIEW = "_AI: pending._"
PENDING_OWNER = "Pending."


# --------------------------------------------------------------------------- models
def load_model(model_dir):
    """Import models/<name>/model.py and return its MODEL object."""
    model_dir = Path(model_dir).resolve()
    path = model_dir / "model.py"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: a model folder needs model.py")
    spec = importlib.util.spec_from_file_location(f"gendesign_model_{model_dir.name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses in model.py look their module up here
    spec.loader.exec_module(mod)
    if not hasattr(mod, "MODEL"):
        raise AttributeError(f"{path} must define MODEL")
    return mod.MODEL


def load_model_requirements(model_dir):
    """Requirements plus every calibration recorded under designs/**/feedback.json."""
    model_dir = Path(model_dir)
    req = load_requirements(model_dir / "requirements.yaml")
    if req.errors:
        raise ValueError(f"{model_dir}/requirements.yaml: " + "; ".join(req.errors))
    for fb in sorted(model_dir.glob("designs/**/feedback.json")):
        for c in json.loads(fb.read_text()).get("calibrations", []):
            req.calibrations[f"{c['evaluator']}.{c['parameter']}"] = c["measured"]
    return req


def objective_names(evaluators):
    names = []
    for ev in evaluators:
        names.extend(getattr(ev, "objectives", ()) or ())
    return names


# --------------------------------------------------------------------------- analysis
def analyze(model_dir):
    """Requirements -> design targets -> concept choice. Runs before any geometry.

    The model's analyze(req) returns targets (each with value, the
    requirement it came from, and how), checks, concepts with a verdict, the
    chosen concept, the generator that implements it, and open questions.
    Writes models/<name>/analysis.json and analysis.md.
    """
    model_dir = Path(model_dir).resolve()
    model = load_model(model_dir)
    if not hasattr(model, "analyze"):
        raise AttributeError(f"{model_dir}/model.py: MODEL needs analyze(req); a round starts from an analysis")
    req = load_model_requirements(model_dir)
    a = dict(model.analyze(req))
    a["date"] = date.today().isoformat()
    a["requirements"] = str((model_dir / "requirements.yaml").relative_to(model_dir))
    a["calibrations"] = dict(req.calibrations)
    (model_dir / "analysis.json").write_text(json.dumps(_jsonable(a), indent=2))
    (model_dir / "analysis.md").write_text(_analysis_md(model_dir.name, a))
    return a


def load_analysis(model_dir):
    p = Path(model_dir) / "analysis.json"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing. Run `gendesign analyze {model_dir}` first: a round starts from requirements and analysis, not a drawing."
        )
    return json.loads(p.read_text())


def _analysis_md(name, a):
    rows = ["| Target | Value | From | How |", "|---|---:|---|---|"]
    for k, t in a.get("targets", {}).items():
        rows.append(f"| {k} | {t.get('value')} | {t.get('from', '')} | {t.get('how', '')} |")
    concepts = "\n".join(f"- **{c['name']}** ({c['verdict']}): {c['why']}" for c in a.get("concepts", []))
    checks = "\n".join(f"- {c}" for c in a.get("checks", []))
    qs = "\n".join(f"- {q}" for q in a.get("open_questions", [])) or "- none"
    return f"""# Analysis — {name}

Requirements → design targets → concept. Written by `gendesign analyze` on {a['date']}; no geometry was drawn to get here.
Rounds read these targets. Re-run after requirements.yaml or a calibration changes.

## Design targets

{chr(10).join(rows)}

## Checks

{checks}

## Concepts

{concepts}

Chosen: **{a.get('chosen')}**, generated by `{a.get('generator')}`.

## Open questions for the owner

{qs}
"""


# --------------------------------------------------------------------------- picks
def select_picks(front, names, k=3):
    """The knee plus the best design on each objective, without duplicates.

    Objectives are maximized. The knee is the point closest to the ideal
    after scaling each objective to [0, 1] across the front.
    """
    if not front:
        return {}
    F = np.array([t.info["objectives"] for t in front], float)
    lo, hi = F.min(0), F.max(0)
    span = np.where(hi > lo, hi - lo, 1.0)
    N = (F - lo) / span
    picks = {"knee": int(np.argmin(np.linalg.norm(1.0 - N, axis=1)))}
    for j, name in enumerate(names or [f"obj{j}" for j in range(F.shape[1])]):
        i = int(np.argmax(F[:, j]))
        if i not in picks.values():
            picks[f"best-{name.split('_')[0]}"] = i
        if len(picks) >= k:
            break
    return {name: front[i] for name, i in picks.items()}


# --------------------------------------------------------------------------- round
def run_round(model_dir, *, design=None, pop=12, gens=4, seed=0, picks=3, export=True,
              from_round=None, note=""):
    """One search round. Returns the iteration folder.

    from_round seeds the population with the picks of an earlier round
    (an iteration folder or its round.json) or with a saved design.json,
    so a round continues the direction the review chose instead of
    starting cold.
    """
    model_dir = Path(model_dir).resolve()
    model = load_model(model_dir)
    req = load_model_requirements(model_dir)
    req.analysis = load_analysis(model_dir)
    gen = model.generator(req)
    evs = model.evaluators(req)
    names = objective_names(evs)

    x0 = _seed_from(from_round, gen) if from_round else None
    result = process_run(gen, evs, req, method="nsga2", pop=pop, gens=gens, seed=seed, x0=x0)

    design_dir = model_dir / "designs" / (design or model.default_design)
    index = next_index(design_dir)
    it = design_dir / "iterations" / index
    it.mkdir(parents=True, exist_ok=True)

    chosen = select_picks(result.pareto, names, k=picks)
    rows = []
    for pname, trial in chosen.items():
        pd = it / "picks" / pname
        pd.mkdir(parents=True, exist_ok=True)
        d = gen.generate(trial.x, req)
        params = d.get("params") or {}
        metrics = _jsonable({k: v for k, v in (trial.info or {}).items() if k not in ("uncertainties",)})
        (pd / "params.json").write_text(json.dumps(_jsonable(params), indent=2))
        report = {}
        if export and hasattr(model, "export"):
            report = model.export(d, pd) or {}
        (pd / "stats.json").write_text(json.dumps({"metrics": metrics, "mesh": _jsonable(report)}, indent=2))
        if hasattr(model, "preview"):
            model.preview(d, pd / "preview.png")
        _preview_3d(pd, f"{model_dir.name} {design_dir.name} round {index}: {pname}")
        rows.append((pname, params, metrics, report))

    record = {
        "model": model_dir.name,
        "design": design_dir.name,
        "round": index,
        "date": date.today().isoformat(),
        "note": note,
        "objectives": names,
        "config": result.config,
        "from_round": str(from_round) if from_round else None,
        "history": result.history,
        "uncertainties": result.uncertainties,
        "calibrations": dict(req.calibrations),
        "analysis": {"date": req.analysis.get("date"), "chosen": req.analysis.get("chosen"),
                     "targets": {k: t.get("value") for k, t in req.analysis.get("targets", {}).items()}},
        "front": [_trial_row(t) for t in result.pareto],
        "picks": {p: _trial_row(t) for p, t in chosen.items()},
    }
    (it / "round.json").write_text(json.dumps(_jsonable(record), indent=2))
    _pareto_png(result.pareto, chosen, names, it / "pareto.png")
    _picks_png(it, rows, names, it / "picks.png")
    (it / "decisions.md").write_text(_decisions_template(record, rows, names, note))
    return it


def _preview_3d(folder, title):
    """Top, 3/4, underside and section views of folder/installed.stl, if PyVista is there."""
    stl = Path(folder) / "installed.stl"
    if not stl.exists():
        return None
    try:
        from .render import preview_sheet

        return preview_sheet(stl, Path(folder) / "preview-3d.png", title=title)
    except ImportError:
        return None


def _seed_from(path, gen=None):
    """Starting genes from an earlier round's picks, or from a saved design.json.

    A design.json needs a generator with x_from_params(params).
    """
    p = Path(path)
    p = p / "round.json" if p.is_dir() else p
    data = json.loads(p.read_text())
    if "picks" in data:
        return np.array([row["x"] for row in data["picks"].values()], float)
    if "params" in data and hasattr(gen, "x_from_params"):
        lo = np.array([b[0] for b in gen.bounds()], float)
        hi = np.array([b[1] for b in gen.bounds()], float)
        return np.clip(np.asarray(gen.x_from_params(data["params"]), float), lo, hi)[None, :]
    raise ValueError(f"{p}: neither a round.json nor a design.json with params")


def _trial_row(t):
    info = t.info or {}
    return {
        "x": [float(v) for v in t.x],
        "objectives": [float(v) for v in info.get("objectives", [])],
        "params": info.get("params") or {},
        "feasible": bool(info.get("feasible", True)),
    }


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


# --------------------------------------------------------------------------- renders
def _pareto_png(front, chosen, names, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not front:
        return None
    F = np.array([t.info["objectives"] for t in front], float)
    fig, ax = plt.subplots(figsize=(5, 4), dpi=120)
    if F.shape[1] >= 2:
        ax.scatter(F[:, 0], F[:, 1], s=18, color="#9aa0a6", label="front")
        for name, t in chosen.items():
            o = t.info["objectives"]
            ax.scatter([o[0]], [o[1]], s=60, color="#1a73e8")
            ax.annotate(name, (o[0], o[1]), textcoords="offset points", xytext=(6, 4), fontsize=8)
        ax.set_xlabel(names[0] if names else "objective 0")
        ax.set_ylabel(names[1] if len(names) > 1 else "objective 1")
    else:
        ax.hist(F[:, 0], bins=12, color="#9aa0a6")
        ax.set_xlabel(names[0] if names else "objective 0")
    ax.set_title("Pareto front (maximized)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def _picks_png(it, rows, names, out, thumb=360):
    from PIL import Image, ImageDraw, ImageFont

    tiles = []
    for pname, _params, metrics, _rep in rows:
        p = it / "picks" / pname / "preview.png"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((thumb, thumb))
        canvas = Image.new("RGB", (thumb, thumb + 44), "white")
        canvas.paste(im, ((thumb - im.size[0]) // 2, 0))
        d = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        objs = metrics.get("objectives") or []
        line2 = "  ".join(f"{n}={v:.3g}" for n, v in zip(names, objs))
        d.text((6, thumb + 4), pname, fill=(20, 20, 20), font=font)
        d.text((6, thumb + 22), line2, fill=(60, 60, 60), font=font)
        tiles.append(canvas)
    if not tiles:
        return None
    sheet = Image.new("RGB", (thumb * len(tiles), thumb + 44), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * thumb, 0))
    sheet.save(out)
    return out


def _decisions_template(record, rows, names, note):
    cfg = record["config"]
    head = ["Pick"] + names + ["Parameters"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for pname, params, metrics, _rep in rows:
        objs = metrics.get("objectives") or []
        ps = ", ".join(f"{k}={v}" for k, v in params.items())
        lines.append("| " + " | ".join([pname] + [f"{v:.4g}" for v in objs] + [ps]) + " |")
    unc = "\n".join(f"- **{k}**: {v}" for k, v in (record.get("uncertainties") or {}).items()) or "- none recorded"
    cal = "\n".join(f"- `{k}` = {v}" for k, v in (record.get("calibrations") or {}).items()) or "- none"
    mesh = "\n".join(_mesh_line(pname, rep) for pname, _p, _m, rep in rows if rep) or "- not exported (--no-export)"
    return f"""# Round {record['round']} — {record['design']}

Search: {cfg['method']}, population {cfg['pop']}, {cfg['gens']} generations, seed {cfg['seed']}.
Generator `{cfg['generator']}`; evaluators {', '.join(f'`{e}`' for e in cfg['evaluators'])}.
{('Seeded from ' + record['from_round'] + '.') if record.get('from_round') else 'Cold start.'}
Concept **{record['analysis']['chosen']}** from `analysis.md` ({record['analysis']['date']}). Targets: {', '.join(f'{k} {v}' for k, v in record['analysis']['targets'].items())}.

## What changed, and why

{note or PENDING_REVIEW}

## Result

{len(record['front'])} design{'' if len(record['front']) == 1 else 's'} on the final front. Objectives are maximized. Renders: `picks.png`, `pareto.png`, `picks/<pick>/preview.png`.

{chr(10).join(lines)}

Mesh check of each pick:
{mesh}

Calibrations in effect:
{cal}

What the evaluators do not know:
{unc}

## AI review of the renders and the scores

{PENDING_REVIEW}

## Proposed next

{PENDING_REVIEW}

## Owner decision

{PENDING_OWNER} Only the owner records this: `gendesign approve <this folder> <pick>`. Nothing is printed before that.
"""


def mesh_problems(rep):
    """What would stop a pick's mesh from going to a slicer."""
    probs = []
    if rep.get("watertight") is False:
        probs.append("not watertight")
    if rep.get("bodies", 1) != 1:
        probs.append(f"{rep['bodies']} bodies")
    un = (rep.get("unsupported") or {}).get("total_mm2")
    if un:
        probs.append(f"{un} mm² printed over air")
    return probs


def _mesh_line(pname, rep):
    probs = mesh_problems(rep)
    vol = rep.get("volume_mm3")
    head = f"- **{pname}**: " + (f"{vol} mm³, " if vol is not None else "")
    return head + ("**" + "; ".join(probs) + "**" if probs else "watertight, one body, nothing over air")


# --------------------------------------------------------------------------- owner + feedback
def approve(iteration_dir, pick, *, note=""):
    """Record the owner's go for one pick. The CLI is the owner's tool, not the agent's."""
    it = Path(iteration_dir)
    pd = it / "picks" / pick
    if not pd.is_dir():
        raise FileNotFoundError(f"no pick {pick!r} in {it}")
    stamp = date.today().isoformat()
    (pd / "approval.json").write_text(json.dumps({"approved": True, "date": stamp, "note": note}, indent=2))
    dm = it / "decisions.md"
    if dm.exists():
        text = dm.read_text()
        entry = f"Approved `{pick}` on {stamp}." + (f" {note}" if note else "")
        text = re.sub(r"(## Owner decision\n\n)" + re.escape(PENDING_OWNER) + r"[^\n]*", r"\g<1>" + entry, text)
        if entry not in text:
            text += f"\n{entry}\n"
        dm.write_text(text)
    return pd / "approval.json"


_CAL = re.compile(r"^\s*-\s*calibrate:\s*([\w-]+)\.([\w-]+)\s*=\s*([^\s(]+)(?:\s*\(predicted\s*([^)]+)\))?\s*(.*)$", re.I)
_REQ = re.compile(r"^\s*-\s*requirement:\s*([\w.-]+)\s*[:—-]\s*(.+)$", re.I)


def parse_feedback(text):
    """Explicit feedback lines in a test.md.

        - calibrate: drainage.cd = 0.55 (predicted 0.61) timed 100 ml through the grate
        - requirement: fit.flange_diameter_mm — calipered 44.8, the 46 was assumed

    A calibration corrects an evaluator for the next round. A requirement
    flag says the input was wrong; only the owner edits requirements.yaml.
    """
    cals, flags = [], []
    for line in text.splitlines():
        m = _CAL.match(line)
        if m:
            measured = _num(m.group(3))
            cals.append({"evaluator": m.group(1), "parameter": m.group(2), "measured": measured,
                         "predicted": _num(m.group(4)) if m.group(4) else None, "note": m.group(5).strip()})
            continue
        m = _REQ.match(line)
        if m:
            flags.append({"field": m.group(1), "reason": m.group(2).strip()})
    return {"calibrations": cals, "requirement_flags": flags}


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return s.strip() if isinstance(s, str) else s


def record_feedback(test_md):
    """Parse a test.md and write feedback.json beside it. Returns the dict."""
    p = Path(test_md)
    fb = parse_feedback(p.read_text())
    (p.parent / "feedback.json").write_text(json.dumps(fb, indent=2))
    return fb


# --------------------------------------------------------------------------- status
def status(model_dir):
    """Where a model stands: designs, rounds, review state, approvals, tests."""
    model_dir = Path(model_dir)
    req = load_requirements(model_dir / "requirements.yaml")
    out = {"model": model_dir.name, "requirements_ok": req.ok, "requirement_errors": req.errors,
           "has_model_py": (model_dir / "model.py").exists(),
           "analysis": (json.loads((model_dir / "analysis.json").read_text()).get("date")
                        if (model_dir / "analysis.json").exists() else None),
           "designs": []}
    for d in sorted(p for p in (model_dir / "designs").iterdir() if p.is_dir()):
        entry = {"design": d.name, "tests": [str(t.relative_to(model_dir)) for t in d.rglob("test.md")], "rounds": []}
        if (d / "iterations").is_dir():
            for r in list_round_dirs(d):
                dm = r / "decisions.md"
                text = dm.read_text() if dm.exists() else ""
                entry["rounds"].append({
                    "round": r.name,
                    # older rounds kept a one-line critique.md instead of decisions.md
                    "reviewed": (bool(text) and PENDING_REVIEW not in text) or (r / "critique.md").exists(),
                    "approved": sorted(a.parent.name for a in r.glob("picks/*/approval.json")),
                })
        out["designs"].append(entry)
    return out


# --------------------------------------------------------------------------- generate
def generate(model_dir, source, out_dir=None):
    """Rebuild a pick (params.json or its folder) or a saved design.json to print files.

    Goes through the model, so the same generator that the round searched
    makes the file that gets printed.
    """
    model_dir = Path(model_dir).resolve()
    model = load_model(model_dir)
    req = load_model_requirements(model_dir)
    src = Path(source)
    if src.is_dir():
        src = src / ("params.json" if (src / "params.json").exists() else "design.json")
    data = json.loads(src.read_text())
    params = data.get("params", data)
    gen = model.generator(req)
    if not hasattr(gen, "x_from_params"):
        raise AttributeError(f"{gen.name}: needs x_from_params(params) to rebuild a saved design")
    lo = [b[0] for b in gen.bounds()]
    hi = [b[1] for b in gen.bounds()]
    x = gen.x_from_params(params)
    outside = [i for i, (v, a, b) in enumerate(zip(x, lo, hi)) if not a <= v <= b]
    d = gen.build_from_params(params) if hasattr(gen, "build_from_params") else gen.generate(x, req)
    out = Path(out_dir) if out_dir else model_dir.parents[1] / "out" / model_dir.name / src.parent.name
    out.mkdir(parents=True, exist_ok=True)
    rep = model.export(d, out) if hasattr(model, "export") else {}
    if hasattr(model, "preview"):
        model.preview(d, out / "preview.png")
    _preview_3d(out, f"{model_dir.name}: {src.parent.name}")
    report = {"source": str(src), "params": _jsonable(d.get("params")), "mesh": _jsonable(rep),
              "mesh_problems": mesh_problems(rep or {}), "genes_outside_bounds": outside}
    (out / "generate.json").write_text(json.dumps(report, indent=2))
    return out, report


# --------------------------------------------------------------------------- report
def report(model_dir):
    """Write models/<name>/REPORT.md: requirements, analysis, every round, tests.

    The review document for the owner. Images are linked from the design
    folders, so it renders on GitHub. Regenerate after each round or review.
    """
    model_dir = Path(model_dir).resolve()
    req = load_requirements(model_dir / "requirements.yaml")
    a = json.loads((model_dir / "analysis.json").read_text()) if (model_dir / "analysis.json").exists() else None
    s = status(model_dir)
    L = [f"# {model_dir.name} — design report", "",
         f"Generated by `gendesign report` on {date.today().isoformat()}. Source of truth: `requirements.yaml`, "
         "`analysis.md`, and each round's `decisions.md`. Nothing here was printed unless a test record says so.", ""]

    L += ["## Requirements", "", req.purpose, ""]
    fn = req.section("function")
    if fn:
        L += ["| Function | Value |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in fn.items()] + [""]
    fit = req.section("fit")
    if fit:
        L += ["Fit: " + ", ".join(f"{k} {v}" for k, v in fit.items()), ""]

    L += ["## Analysis", ""]
    if a:
        L += [f"From `analysis.md` ({a.get('date')}). Concept: **{a.get('chosen')}** (generator `{a.get('generator')}`).", "",
              "| Target | Value | From |", "|---|---:|---|"]
        L += [f"| {k} | {t.get('value')} | {t.get('from', '')} |" for k, t in a.get("targets", {}).items()]
        L += [""] + [f"- {c}" for c in a.get("checks", [])] + [""]
        L += [f"- **{c['name']}** ({c['verdict']})" for c in a.get("concepts", [])] + [""]
        if a.get("open_questions"):
            L += ["Open questions for the owner:", ""] + [f"- {q}" for q in a["open_questions"]] + [""]
    else:
        L += ["No analysis yet. Run `gendesign analyze` before a round.", ""]

    L += ["## Rounds", ""]
    any_round = False
    for d in s["designs"]:
        ddir = model_dir / "designs" / d["design"]
        for r in d["rounds"]:
            it = ddir / "iterations" / r["round"]
            rec_p = it / "round.json"
            if not rec_p.exists():
                continue
            any_round = True
            rec = json.loads(rec_p.read_text())
            rel = it.relative_to(model_dir)
            text = (it / "decisions.md").read_text() if (it / "decisions.md").exists() else ""
            state = "approved: " + ", ".join(r["approved"]) if r["approved"] else (
                "reviewed, awaiting owner" if r["reviewed"] else "awaiting AI review")
            L += [f"### {d['design']} / round {r['round']} — {state}", "",
                  f"{rec.get('date')} · {rec['config']['method']} pop {rec['config']['pop']} × {rec['config']['gens']} gens, "
                  f"seed {rec['config']['seed']} · front {len(rec['front'])} · [decisions]({rel}/decisions.md)", ""]
            if (it / "picks.png").exists():
                L += [f"![round {r['round']} picks]({rel}/picks.png)", ""]
            knee3d = it / "picks" / "knee" / "preview-3d.png"
            if knee3d.exists():
                L += [f'<img src="{rel}/picks/knee/preview-3d.png" width="520" alt="round {r["round"]} knee, 3-D">', ""]
            names = rec.get("objectives") or []
            if rec.get("picks"):
                L += ["| Pick | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
                for p, row in rec["picks"].items():
                    L.append(f"| {p} | " + " | ".join(f"{v:.3g}" for v in row["objectives"]) + " |")
                L.append("")
            for section in ("AI review of the renders and the scores", "Proposed next", "Owner decision"):
                body = _section(text, section)
                if body:
                    L += [f"#### {section}", "", body, ""]
    if not any_round:
        L += ["No rounds through `gendesign round` yet.", ""]

    L += ["## Records", "", "Designs kept as history. Each folder has its own design.json and, if printed, test.md.", "",
          "| Design | Preview | Rounds | Tests |", "|---|---|---:|---|"]
    for d in s["designs"]:
        ddir = model_dir / "designs" / d["design"]
        img = next((p for p in ("preview-top.png", "preview.png", "preview-34.png") if (ddir / p).exists()), None)
        if img is None:  # newest pick render, if the design only has rounds
            found = sorted(ddir.glob("iterations/*/picks/knee/preview*.png"))
            img = str(found[-1].relative_to(ddir)) if found else None
        cell = f'<img src="designs/{d["design"]}/{img}" width="140">' if img else ""
        tests = ", ".join(f"[{Path(t).parent.name}]({t})" for t in d["tests"]) or "—"
        L.append(f"| [{d['design']}](designs/{d['design']}/) | {cell} | {len(d['rounds'])} | {tests} |")
    L.append("")
    out = model_dir / "REPORT.md"
    out.write_text("\n".join(L))
    return out


def _section(text, title):
    m = re.search(r"^## " + re.escape(title) + r"\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""

