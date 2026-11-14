"""Parameter search: grid, random, a simple GA, CMA-ES, optional Bayesian (optuna)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class Trial:
    x: np.ndarray
    score: float  # higher is better
    info: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    best: Trial
    trials: list
    method: str

    def pareto(self, keys):
        return pareto_front(self.trials, keys)


def _bounds_arr(bounds):
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    return lo, hi


def grid_search(fun: Callable, bounds, n_each=5, maximize=True) -> SearchResult:
    lo, hi = _bounds_arr(bounds)
    axes = [np.linspace(a, b, n_each) for a, b in zip(lo, hi)]
    trials = []
    best = None
    for pts in np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(bounds), -1).T:
        s = fun(pts)
        if not maximize:
            s = -s
        t = Trial(np.asarray(pts, dtype=float), float(s))
        trials.append(t)
        if best is None or t.score > best.score:
            best = t
    return SearchResult(best, trials, "grid")


def random_search(fun, bounds, n=40, seed=0, maximize=True) -> SearchResult:
    rng = np.random.default_rng(seed)
    lo, hi = _bounds_arr(bounds)
    trials, best = [], None
    for _ in range(n):
        x = rng.uniform(lo, hi)
        s = fun(x)
        if not maximize:
            s = -s
        t = Trial(x, float(s))
        trials.append(t)
        if best is None or t.score > best.score:
            best = t
    return SearchResult(best, trials, "random")


def genetic_minimize(fun, bounds, pop=24, gens=12, seed=0, maximize=True, elite=2) -> SearchResult:
    """Simple real-valued GA. `fun` is maximized unless maximize=False."""
    rng = np.random.default_rng(seed)
    lo, hi = _bounds_arr(bounds)
    dim = len(bounds)
    pop_x = rng.uniform(lo, hi, size=(pop, dim))
    trials, best = [], None

    def eval_x(x):
        s = fun(x)
        if not maximize:
            s = -s
        t = Trial(np.array(x, dtype=float), float(s))
        trials.append(t)
        return t

    scores = []
    for x in pop_x:
        t = eval_x(x)
        scores.append(t.score)
        if best is None or t.score > best.score:
            best = t
    scores = np.array(scores)
    for _ in range(gens):
        order = np.argsort(-scores)
        pop_x = pop_x[order]
        scores = scores[order]
        new = list(pop_x[:elite])
        new_s = list(scores[:elite])
        # tournament
        while len(new) < pop:
            i, j = rng.integers(0, pop, size=2)
            p1 = pop_x[i if scores[i] >= scores[j] else j]
            i, j = rng.integers(0, pop, size=2)
            p2 = pop_x[i if scores[i] >= scores[j] else j]
            alpha = rng.random(dim)
            child = alpha * p1 + (1 - alpha) * p2
            child = child + rng.normal(0, 0.08, size=dim) * (hi - lo)
            child = np.clip(child, lo, hi)
            t = eval_x(child)
            new.append(child)
            new_s.append(t.score)
            if t.score > best.score:
                best = t
        pop_x = np.array(new[:pop])
        scores = np.array(new_s[:pop])
    return SearchResult(best, trials, "ga")


def cma_es(fun, bounds, x0=None, sigma=0.25, pop=None, gens=15, seed=0, maximize=True) -> SearchResult:
    """A compact CMA-ES (Hansen-style, no extra dependency)."""
    rng = np.random.default_rng(seed)
    lo, hi = _bounds_arr(bounds)
    dim = len(bounds)
    if x0 is None:
        mean = 0.5 * (lo + hi)
    else:
        mean = np.clip(np.asarray(x0, dtype=float), lo, hi)
    span = hi - lo
    sigma = float(sigma)
    lam = int(pop or (4 + 3 * math.log(dim)))
    mu = max(1, lam // 2)
    weights = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    weights = weights / weights.sum()
    mueff = 1.0 / np.sum(weights**2)
    cc = (4 + mueff / dim) / (dim + 4 + 2 * mueff / dim)
    cs = (mueff + 2) / (dim + mueff + 5)
    c1 = 2 / ((dim + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((dim + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0, math.sqrt((mueff - 1) / (dim + 1)) - 1) + cs
    C = np.eye(dim)
    pc = np.zeros(dim)
    ps = np.zeros(dim)
    trials, best = [], None
    chi = math.sqrt(dim) * (1 - 1 / (4 * dim) + 1 / (21 * dim * dim))
    for _ in range(gens):
        # sample
        try:
            A = np.linalg.cholesky(C)
        except np.linalg.LinAlgError:
            C = np.eye(dim)
            A = np.eye(dim)
        zs = rng.normal(size=(lam, dim))
        xs = mean + sigma * (zs @ A.T) * span
        xs = np.clip(xs, lo, hi)
        scored = []
        for x, z in zip(xs, zs):
            s = fun(x)
            if not maximize:
                s = -s
            t = Trial(np.array(x, dtype=float), float(s), info={"z": z.tolist()})
            trials.append(t)
            scored.append((t.score, x, z, t))
            if best is None or t.score > best.score:
                best = t
        scored.sort(key=lambda r: -r[0])
        old = mean.copy()
        mean = np.sum([w * x for w, (_, x, _, _) in zip(weights, scored[:mu])], axis=0)
        zmean = np.sum([w * z for w, (_, _, z, _) in zip(weights, scored[:mu])], axis=0)
        ps = (1 - cs) * ps + math.sqrt(cs * (2 - cs) * mueff) * zmean
        hsig = float(np.linalg.norm(ps) / math.sqrt(1 - (1 - cs) ** (2 * (_ + 1))) / chi < (1.4 + 2 / (dim + 1)))
        pc = (1 - cc) * pc + hsig * math.sqrt(cc * (2 - cc) * mueff) * (A @ zmean)
        y = pc / span  # approx
        C = (1 - c1 - cmu) * C + c1 * (np.outer(zmean, zmean) * 0 + np.outer(pc, pc) / max((sigma * span).mean() ** 2, 1e-12))
        # simpler CMA covariance update in z-space:
        Cz = (1 - c1 - cmu) * (A @ A.T)
        Cz = Cz + c1 * np.outer(ps, ps)  # rough
        for w, (_, _, z, _) in zip(weights, scored[:mu]):
            Cz = Cz + cmu * w * np.outer(z, z)
        C = 0.5 * (Cz + Cz.T)
        sigma = sigma * math.exp((cs / damps) * (np.linalg.norm(ps) / chi - 1))
        sigma = float(np.clip(sigma, 1e-3, 1.0))
    return SearchResult(best, trials, "cma-es")


def bayesian_search(fun, bounds, n=30, seed=0, maximize=True) -> SearchResult:
    """optuna TPE if installed; otherwise falls back to CMA-ES."""
    lo, hi = _bounds_arr(bounds)
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except Exception:
        return cma_es(fun, bounds, gens=max(8, n // 4), seed=seed, maximize=maximize)

    trials, best = [], None

    def objective(trial):
        x = np.array([trial.suggest_float(f"x{i}", a, b) for i, (a, b) in enumerate(zip(lo, hi))])
        s = fun(x)
        if not maximize:
            s = -s
        t = Trial(x, float(s))
        trials.append(t)
        nonlocal best
        if best is None or t.score > best.score:
            best = t
        return -float(s)  # optuna minimizes

    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n)
    return SearchResult(best, trials, "optuna-tpe")


def pareto_front(trials, keys):
    """Non-dominated subset. Each trial.info must contain `keys`, all maximized."""
    pts = []
    for t in trials:
        if all(k in t.info for k in keys):
            pts.append((t, np.array([t.info[k] for k in keys], dtype=float)))
    keep = []
    for i, (ti, vi) in enumerate(pts):
        dominated = False
        for j, (tj, vj) in enumerate(pts):
            if j == i:
                continue
            if np.all(vj >= vi) and np.any(vj > vi):
                dominated = True
                break
        if not dominated:
            keep.append(ti)
    return keep
