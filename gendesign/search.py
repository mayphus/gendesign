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


@dataclass
class MultiResult:
    """NSGA-II output. `front` is the feasible non-dominated set (maximized)."""

    front: list
    population: list
    trials: list
    method: str = "nsga2"
    history: list = field(default_factory=list)

    def pareto(self, keys=None):
        if keys is None:
            return list(self.front)
        return pareto_front(self.trials, keys)


def _as_objectives(raw):
    """Normalize a fun() return into (objectives, violation, info)."""
    info = {}
    violation = 0.0
    if isinstance(raw, dict):
        info = dict(raw.get("info") or {})
        violation = float(raw.get("violation") or 0.0)
        obj = raw.get("objectives", raw.get("f"))
    else:
        obj = raw
    f = np.asarray(obj, dtype=float).ravel()
    if not np.all(np.isfinite(f)):
        violation = max(violation, 1e6)
        f = np.nan_to_num(f, nan=-1e6, posinf=1e6, neginf=-1e6)
    return f, violation, info


def _dominates(a, b, va, vb):
    """Constraint-domination. Objectives are maximized. Violation 0 is feasible."""
    a_ok, b_ok = va <= 0.0, vb <= 0.0
    if a_ok and not b_ok:
        return True
    if b_ok and not a_ok:
        return False
    if not a_ok and not b_ok:
        return va < vb - 1e-12
    return bool(np.all(a >= b - 1e-12) and np.any(a > b + 1e-12))


def _nondominated_ranks(F, V):
    """Return rank per row (0 is the best front) and the front index lists."""
    n = len(F)
    dominated_by = [0] * n
    dominates = [[] for _ in range(n)]
    fronts = [[]]
    for i in range(n):
        for j in range(i + 1, n):
            if _dominates(F[i], F[j], V[i], V[j]):
                dominates[i].append(j)
                dominated_by[j] += 1
            elif _dominates(F[j], F[i], V[j], V[i]):
                dominates[j].append(i)
                dominated_by[i] += 1
        if dominated_by[i] == 0:
            fronts[0].append(i)
    rank = np.zeros(n, dtype=int)
    k = 0
    while fronts[k]:
        nxt = []
        for i in fronts[k]:
            rank[i] = k
            for j in dominates[i]:
                dominated_by[j] -= 1
                if dominated_by[j] == 0:
                    nxt.append(j)
        k += 1
        fronts.append(nxt)
    fronts.pop()
    return rank, fronts


def _crowding(F, idxs):
    m = len(idxs)
    dist = np.zeros(m)
    if m == 0:
        return dist
    if m <= 2:
        dist[:] = np.inf
        return dist
    sub = F[idxs]
    for j in range(sub.shape[1]):
        order = np.argsort(sub[:, j])
        dist[order[0]] = np.inf
        dist[order[-1]] = np.inf
        span = sub[order[-1], j] - sub[order[0], j]
        if span < 1e-12:
            continue
        for t in range(1, m - 1):
            dist[order[t]] += (sub[order[t + 1], j] - sub[order[t - 1], j]) / span
    return dist


def _sbx(p1, p2, lo, hi, rng, eta):
    c1 = np.array(p1, dtype=float)
    c2 = np.array(p2, dtype=float)
    for i in range(len(p1)):
        if rng.random() > 0.5 or abs(p1[i] - p2[i]) < 1e-14:
            continue
        y1, y2 = (p1[i], p2[i]) if p1[i] < p2[i] else (p2[i], p1[i])
        yl, yu = lo[i], hi[i]
        span = y2 - y1
        for which in (0, 1):
            rnd = rng.random()
            if which == 0:
                beta = 1.0 + 2.0 * (y1 - yl) / span
            else:
                beta = 1.0 + 2.0 * (yu - y2) / span
            alpha = 2.0 - beta ** (-(eta + 1.0))
            if rnd <= 1.0 / alpha:
                betaq = (rnd * alpha) ** (1.0 / (eta + 1.0))
            else:
                betaq = (1.0 / (2.0 - rnd * alpha)) ** (1.0 / (eta + 1.0))
            if which == 0:
                child = 0.5 * ((y1 + y2) - betaq * span)
                c1[i] = float(np.clip(child, yl, yu))
            else:
                child = 0.5 * ((y1 + y2) + betaq * span)
                c2[i] = float(np.clip(child, yl, yu))
    if rng.random() < 0.5:
        return c2, c1
    return c1, c2


def _poly_mutation(x, lo, hi, rng, eta, prob):
    y = np.array(x, dtype=float)
    for i in range(len(y)):
        if rng.random() > prob:
            continue
        dx = hi[i] - lo[i]
        if dx <= 0:
            continue
        delta1 = (y[i] - lo[i]) / dx
        delta2 = (hi[i] - y[i]) / dx
        rnd = rng.random()
        mut_pow = 1.0 / (eta + 1.0)
        if rnd < 0.5:
            xy = 1.0 - delta1
            val = 2.0 * rnd + (1.0 - 2.0 * rnd) * (xy ** (eta + 1.0))
            deltaq = val ** mut_pow - 1.0
        else:
            xy = 1.0 - delta2
            val = 2.0 * (1.0 - rnd) + 2.0 * (rnd - 0.5) * (xy ** (eta + 1.0))
            deltaq = 1.0 - val ** mut_pow
        y[i] = float(np.clip(y[i] + deltaq * dx, lo[i], hi[i]))
    return y


def _lhs(rng, n, lo, hi):
    dim = len(lo)
    u = np.zeros((n, dim))
    for j in range(dim):
        slots = (np.arange(n) + rng.random(n)) / n
        rng.shuffle(slots)
        u[:, j] = slots
    return lo + u * (hi - lo)


def nsga2(
    fun: Callable,
    bounds,
    pop: int = 32,
    gens: int = 12,
    seed: int = 0,
    eta_cross: float = 12.0,
    eta_mut: float = 18.0,
    x0=None,
    callback: Callable | None = None,
) -> MultiResult:
    """NSGA-II. `fun` is maximized.

    `fun(x)` returns a sequence of objectives, or a dict with
    `objectives` (maximized), optional `violation` (0 = feasible), and
    optional `info`. Infeasible points lose to feasible ones; among
    infeasible points, the smaller violation wins.

    `callback(gen, front, population)` runs after each generation,
    including 0. `front` and `population` are lists of Trial.
    """
    rng = np.random.default_rng(seed)
    lo, hi = _bounds_arr(bounds)
    dim = len(bounds)
    pop = max(4, int(pop))
    if pop % 2:
        pop += 1
    X = _lhs(rng, pop, lo, hi)
    if x0 is not None:
        seeds = np.atleast_2d(np.asarray(x0, dtype=float))
        for i, row in enumerate(seeds[:pop]):
            X[i] = np.clip(row, lo, hi)

    trials: list[Trial] = []
    history = []

    def evaluate(batch):
        out_f, out_v, out_t = [], [], []
        for x in batch:
            f, v, info = _as_objectives(fun(np.asarray(x, dtype=float)))
            info = dict(info)
            info.setdefault("objectives", f.tolist())
            info["violation"] = v
            info["feasible"] = v <= 0.0
            # Scalar stand-in so a single-objective consumer still has a score.
            t = Trial(np.asarray(x, dtype=float), float(np.sum(f)) if v <= 0 else -1e6 - v, info)
            trials.append(t)
            out_f.append(f)
            out_v.append(v)
            out_t.append(t)
        return np.vstack(out_f), np.asarray(out_v, dtype=float), out_t

    def pack(gen, F, V, Ts, Xs):
        rank, fronts = _nondominated_ranks(F, V)
        crowd = np.zeros(len(F))
        for fr in fronts:
            if not fr:
                continue
            cd = _crowding(F, fr)
            for k, i in enumerate(fr):
                crowd[i] = cd[k]
        feas = [Ts[i] for i in fronts[0] if V[i] <= 0.0] if fronts else []
        # If the first front is entirely infeasible, expose it but flag it.
        front = feas if feas else ([Ts[i] for i in fronts[0]] if fronts else [])
        history.append({
            "gen": gen,
            "n_feasible": int(np.sum(V <= 0.0)),
            "front": len(front),
            "best_objectives": None if not feas else np.max(np.vstack([
                t.info["objectives"] for t in feas
            ]), axis=0).tolist(),
        })
        if callback is not None:
            callback(gen, front, Ts)
        return rank, crowd, fronts, front

    F, V, Ts = evaluate(X)
    rank, crowd, fronts, front = pack(0, F, V, Ts, X)

    mut_prob = 1.0 / dim
    for gen in range(1, int(gens) + 1):
        children = []
        while len(children) < pop:
            i, j = rng.integers(0, pop, size=2)
            a = i if (rank[i], -crowd[i]) <= (rank[j], -crowd[j]) else j
            i, j = rng.integers(0, pop, size=2)
            b = i if (rank[i], -crowd[i]) <= (rank[j], -crowd[j]) else j
            c1, c2 = _sbx(X[a], X[b], lo, hi, rng, eta_cross)
            children.append(_poly_mutation(c1, lo, hi, rng, eta_mut, mut_prob))
            if len(children) < pop:
                children.append(_poly_mutation(c2, lo, hi, rng, eta_mut, mut_prob))
        C = np.vstack(children)
        Fc, Vc, Tc = evaluate(C)
        X = np.vstack([X, C])
        F = np.vstack([F, Fc])
        V = np.concatenate([V, Vc])
        Ts = Ts + Tc
        rank_all, fronts = _nondominated_ranks(F, V)
        chosen = []
        for fr in fronts:
            if len(chosen) + len(fr) <= pop:
                chosen.extend(fr)
                continue
            cd = _crowding(F, fr)
            order = np.argsort(-cd)
            need = pop - len(chosen)
            chosen.extend([fr[i] for i in order[:need]])
            break
        chosen = np.array(chosen[:pop], dtype=int)
        X, F, V = X[chosen], F[chosen], V[chosen]
        Ts = [Ts[i] for i in chosen]
        rank, crowd, fronts, front = pack(gen, F, V, Ts, X)

    return MultiResult(front=list(front), population=list(Ts), trials=trials, method="nsga2", history=history)


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
