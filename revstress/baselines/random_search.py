"""Random-search baseline (plan section 8D b): shocks sampled from N(mu, Sigma) plus the spike overlay."""

from __future__ import annotations

import numpy as np

from .. import config
from .common import BudgetExhausted, EngineFn, Evaluator, FactorSpec, RulesFn, SpikeOverlay, default_hard_rules, factors_to_shock


def random_search(
    engine_fn: EngineFn,
    spec: FactorSpec,
    *,
    budget: int,
    seed: int,
    season: str = "winter",
    horizon_days: int = 30,
    duration_range: tuple[int, int] = (3, 14),
    sigma_mult: float = 1.0,
    spike: SpikeOverlay | None = None,
    target_usd: float = config.LOSS_TARGET_USD,
    rules_fn: RulesFn = default_hard_rules,
) -> list[dict]:
    """Draw `budget` shocks and evaluate each once with engine_fn; return scenario records.

    Factor deviations ~ N(mu, sigma_mult^2 * Sigma); the default sigma_mult = 1 is the plan's N(mu, Sigma).
    A larger sigma_mult is a widened SENSITIVITY variant and must be reported as such. Duration is
    uniform on duration_range (days, capped at horizon_days); spike days and size come from the shared
    SpikeOverlay. Deterministic given seed.
    """
    overlay = SpikeOverlay() if spike is None else spike
    rng = np.random.default_rng(seed)
    chol = np.linalg.cholesky(spec.cov)
    lo, hi = duration_range[0], min(duration_range[1], horizon_days)
    ev = Evaluator(engine_fn, budget, "random", seed, season, horizon_days, target_usd, rules_fn)
    try:
        for i in range(budget):
            x = spec.mu + sigma_mult * chol @ rng.standard_normal(len(spec.mu))
            duration = int(rng.integers(lo, hi + 1))
            n_spike, avg = overlay.sample(rng, duration)
            ev.evaluate(factors_to_shock(x, duration, n_spike, avg), iteration=i)
    except BudgetExhausted:
        pass
    return ev.records
