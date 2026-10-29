"""Conditional-Gaussian most-likely scenario (Sparviero and Viola, arXiv 2606.09274; plan sections 5 and 8D).

Given the target loss, pick the core-factor vector x that maximises the Gaussian-core density subject to
loss(x) = target, i.e. minimises D^2 = (x - mu)' Sigma^-1 (x - mu) on the loss constraint. The book P&L is nonlinear in
the shocks, so the loss is linearised around the base point x0 = mu with forward-difference gradients g (engine calls),
loss(x) ~ L0 + g'(x - mu). On the hyperplane the minimiser is closed-form,
    x* = mu + lam * Sigma g,   lam = (target - L0) / (g' Sigma g),
and is then verified with the true engine and corrected by damped Newton / secant steps along lam (a line search on
the one scalar that moves x* along Sigma g). The remaining budget is spent on local perturbations of the best
feasible point, projected onto the hyperplane (Sigma^-1-orthogonal to Sigma g) with a small random outward scale, so
all arms use an equal engine-evaluation budget. Same engine_fn interface and record schema as random_search and
optimizer (arm 'cond_gaussian'). Duration, spike days and spike size are fixed inputs (default: no spike).
Factor units as FACTOR_ORDER (g, l, s, d: log points; c: $/MWh). Deterministic given seed.
"""

from __future__ import annotations

import numpy as np

from .. import config
from .common import (
    BudgetExhausted,
    EngineFn,
    Evaluator,
    FactorSpec,
    RulesFn,
    default_hard_rules,
    factors_to_shock,
    template_narrative,
)

LOSS_SCALE_USD = 1e6
ARM = "cond_gaussian"


def cond_gaussian_search(
    engine_fn: EngineFn,
    spec: FactorSpec,
    *,
    budget: int,
    seed: int,
    season: str = "winter",
    horizon_days: int = 30,
    duration_days: int = 7,
    spike_days: int = 0,
    spike_daily_avg_usd: float = 0.0,
    target_usd: float = config.LOSS_TARGET_USD,
    rules_fn: RulesFn = default_hard_rules,
    fd_step_sd: float = 0.25,
    max_newton: int = 6,
    damping: float = 0.9,
    overshoot: float = 0.02,
    local_scale: float = 0.15,
    bound_sd: float = 6.0,
) -> list[dict]:
    """Closed-form linearised most-likely scenario, engine-verified, then local perturbations; returns records.

    1. Evaluate the base point mu and forward differences with step fd_step_sd * sd per factor (1 + 5 engine calls).
    2. lam0 = (target*(1+overshoot) - L0) / (g' Sigma g); x(lam) = mu + lam * Sigma g, clipped to +/- bound_sd sd.
    3. Up to max_newton damped (damping) Newton steps on lam, slope from the linearisation then from the last two
       evaluations (secant); stop when loss lies in [target, target*(1+2*overshoot+0.03)].
    4. Spend the rest of `budget` on x* + local_scale * (projected noise in sd units), outward scale in [1, 1.1].
    Records are all engine evaluations (at most budget). spike_days / spike_daily_avg_usd are held fixed in all calls.
    With zero loss sensitivity (g = 0) the search reduces to Gaussian perturbations around mu.
    """
    rng = np.random.default_rng(seed)
    sd, mu, cov = spec.sd, spec.mu, spec.cov
    n = len(mu)
    chol = np.linalg.cholesky(cov)
    ev = Evaluator(engine_fn, budget, ARM, seed, season, horizon_days, target_usd, rules_fn)
    lo, hi = mu - bound_sd * sd, mu + bound_sd * sd

    def shock(x: np.ndarray) -> dict:
        return factors_to_shock(np.clip(x, lo, hi), duration_days, spike_days, spike_daily_avg_usd)

    def loss_of(x: np.ndarray, it: int) -> float | None:
        res = ev.evaluate(shock(x), iteration=it)
        return None if res is None else float(-res["pnl_total"])

    best_x: np.ndarray | None = None
    best_d2 = np.inf

    def track(x: np.ndarray, loss: float | None) -> None:
        nonlocal best_x, best_d2
        if loss is not None and loss >= target_usd:
            d2 = spec.d2(np.clip(x, lo, hi))
            if d2 < best_d2:
                best_x, best_d2 = np.clip(x, lo, hi), d2

    try:
        l0 = loss_of(mu, 0)
        track(mu, l0)
        grad = np.zeros(n)
        if l0 is not None:
            for i in range(n):
                h = fd_step_sd * sd[i]
                x = mu.copy()
                x[i] += h
                li = loss_of(x, 1)
                grad[i] = 0.0 if li is None else (li - l0) / h
        direction = cov @ grad
        curv = float(grad @ direction)
        if l0 is not None and curv > 0.0:
            aim = target_usd * (1.0 + overshoot)
            lam = max((aim - l0) / curv, 0.0)
            prev: tuple[float, float] | None = None
            slope = curv
            for k in range(max_newton):
                x = np.clip(mu + lam * direction, lo, hi)
                lk = loss_of(x, 2 + k)
                if lk is None:
                    break
                track(x, lk)
                if target_usd <= lk <= target_usd * (1.0 + 2.0 * overshoot + 0.03):
                    break
                if prev is not None and abs(lam - prev[0]) > 1e-15:
                    sec = (lk - prev[1]) / (lam - prev[0])
                    if sec > 0.0:
                        slope = sec
                prev = (lam, lk)
                lam = max(lam + damping * (aim - lk) / slope, 0.0)
        base = best_x if best_x is not None else mu
        it = 2 + max_newton
        for _ in range(100 * max(budget, 1)):  # guard: repeated shocks are cached and cost no budget
            if ev.used >= budget:
                break
            noise = chol @ rng.standard_normal(n) * local_scale
            if curv > 0.0:
                noise = noise - (grad @ noise) / curv * direction  # g'noise = 0: stays on the hyperplane
            x = base + noise
            if curv > 0.0 and best_x is not None:
                x = mu + (1.0 + 0.1 * rng.uniform()) * (x - mu)
            track(x, loss_of(x, it))
            it += 1
    except BudgetExhausted:
        pass
    for r in ev.records:
        r["narrative"] = template_narrative(r["shocks"], season, r["driver_class"], r["loss_usd"])
    return ev.records
