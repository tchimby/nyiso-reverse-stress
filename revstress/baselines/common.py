"""Shared pieces of the random-search and optimizer baselines (plan section 8D).

engine_fn(shock_dict) -> dict with pnl_total (USD, negative = loss), pnl_by_position, pnl_by_channel,
d2, q, marginals (factor -> percentile in [0, 1]), nearest_date, severity, spike_exceedance.
The engine is injected; this package does not import the risk module.

Scenario record schema (same fields as the agent loop output, plus engine results):
scenario_id, arm, seed, iteration, driver_class, season, horizon_days, narrative, shocks, analogue,
confidence, engine (dict or None), loss_usd, rules_failed (list), rules_passed (bool), breach (bool).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import numpy as np

from .. import config
from ..market import Market, get_market

EngineFn = Callable[[dict], dict]
RulesFn = Callable[[dict, "dict | None", dict], "list[str]"]

FACTOR_ORDER: tuple[str, ...] = config.GAUSSIAN_CORE_FACTORS  # ("g", "l", "s", "c", "d")


class BudgetExhausted(Exception):
    """Raised when the engine-evaluation budget is used up."""


@dataclass(frozen=True)
class FactorSpec:
    """Gaussian-core factor model: mean and covariance of daily deviations from seasonal means.

    mu: shape (5,), cov: shape (5, 5), in the units of FACTOR_ORDER
    (g, l, s, d: log points; c: $/MWh).
    """

    mu: np.ndarray
    cov: np.ndarray

    def __post_init__(self) -> None:
        n = len(FACTOR_ORDER)
        if np.shape(self.mu) != (n,) or np.shape(self.cov) != (n, n):
            raise ValueError(f"mu must have shape ({n},) and cov ({n}, {n})")

    @property
    def sd(self) -> np.ndarray:
        """Marginal standard deviations, same units as the factors."""
        return np.sqrt(np.diag(self.cov))

    def d2(self, x: np.ndarray) -> float:
        """Squared Mahalanobis distance of factor vector x from mu (dimensionless)."""
        dx = np.asarray(x, dtype=float) - self.mu
        return float(dx @ np.linalg.solve(self.cov, dx))


@dataclass(frozen=True)
class SpikeOverlay:
    """Spike overlay shared by all arms: Binomial(duration, p) spike days, Pareto excess over a threshold.

    PLACEHOLDER parameters until the spike model (plan section 4) is fitted. Levels in $/MWh.
    """

    prob_per_day: float = 0.03
    threshold_usd: float = 250.0
    pareto_scale_usd: float = 150.0
    pareto_shape: float = 2.5
    max_avg_usd: float = field(default_factory=config.energy_cap_usd)

    def sample(self, rng: np.random.Generator, duration_days: int) -> tuple[int, float]:
        """Return (spike_days, spike_daily_avg_usd in $/MWh); the average is 0 with no spike days."""
        n = int(rng.binomial(duration_days, self.prob_per_day))
        if n == 0:
            return 0, 0.0
        u = rng.uniform()
        avg = self.threshold_usd + self.pareto_scale_usd * ((1.0 - u) ** (-1.0 / self.pareto_shape) - 1.0)
        return n, float(min(avg, self.max_avg_usd))


def factors_to_shock(
    x: np.ndarray,
    duration_days: int,
    spike_days: int = 0,
    spike_daily_avg_usd: float = 0.0,
    dc_load_shock_mw: float = 0.0,
) -> dict[str, float]:
    """Map a Gaussian-core deviation vector (g, l, s, c, d) to a shock dict.

    g, l, s, d are log deviations: pct = 100*(exp(x)-1), load_peak_ratio = exp(l). c is $/MWh.
    """
    g, l, s, c, d = (float(v) for v in x)
    return {
        "gas_hh_pct": 100.0 * float(np.expm1(g)),
        "load_peak_ratio": float(np.exp(l)),
        "dc_load_shock_mw": float(dc_load_shock_mw),
        "wh_onpeak_pct": 100.0 * float(np.expm1(s)),
        "dom_minus_wh_usd": c,
        "dart_pct": 100.0 * float(np.expm1(d)),
        "spike_days": int(spike_days),
        "spike_daily_avg_usd": float(spike_daily_avg_usd),
        "duration_days": int(duration_days),
    }


def classify_driver(shock: Mapping[str, float], season: str, market: "str | Market | None" = None) -> str:
    """Rule-based driver class from the shock signs (the baselines have no story of their own).

    Engine shock keys. market=None means the active market: PJM labels a positive dc_load_shock_mw
    demand_shock_datacenter and the fallback class is policy; NYISO labels a negative one large_load_shortfall and the
    fallback class is reserve_shortage.
    """
    m = get_market(config.MARKET if market is None else market)
    dc = shock.get("dc_load_shock_mw", 0.0)
    if (m.name == "PJM" and dc > 0) or (m.name != "PJM" and dc < 0):
        return m.large_load_driver_class
    gas, load = shock.get("gas_hh_pct", 0.0), shock.get("load_peak_ratio", 1.0)
    if abs(shock.get("dom_minus_wh_usd", 0.0)) >= 25.0 and load < 1.05:
        return "transmission"
    if gas >= 40.0 and load < 1.05:
        return "gas_supply"
    if load >= 1.05:
        return "cold_snap" if season == "winter" else "heat_wave"
    if shock.get("spike_days", 0) > 0:
        return "generator_outage"
    return m.default_driver_class


def default_hard_rules(shock: dict, result: "dict | None", context: dict) -> list[str]:
    """Hard rules (plan section 5) checkable from shock and engine result; returns failed rule names."""
    if result is None:
        return ["invalid_shock"]
    failed: list[str] = []
    if shock["duration_days"] > context.get("horizon_days", 10**9):
        failed.append("duration_over_horizon")
    if shock["spike_days"] > shock["duration_days"]:
        failed.append("spike_days_over_duration")
    if shock["spike_daily_avg_usd"] > config.energy_cap_usd():
        failed.append("energy_component_above_cap")
    driver = context.get("driver_class", "")
    if driver in ("cold_snap", "heat_wave") and shock["load_peak_ratio"] < 1.0:
        failed.append("sign_inconsistent")
    if driver == "cold_snap" and shock["gas_hh_pct"] < 0.0:
        failed.append("sign_inconsistent")
    if result.get("severity") == "implausible":
        failed.append("implausible_severity")
    return sorted(set(failed))


def template_narrative(
    shock: Mapping[str, float],
    season: str,
    driver_class: str,
    loss_usd: float | None = None,
    market: "str | Market | None" = None,
) -> str:
    """Hand-coded narrative: one clause per non-zero shock, no story beyond the numbers (zone labels from the market)."""
    m = get_market(config.MARKET if market is None else market)
    ref, pocket = m.reference_label, m.pocket_label
    parts = [f"Template scenario of type {driver_class} in {season}, lasting {int(shock['duration_days'])} days."]
    if shock["gas_hh_pct"]:
        parts.append(f"Henry Hub gas moves {shock['gas_hh_pct']:+.0f}% which lifts heat-rate driven power prices.")
    if shock["load_peak_ratio"] != 1.0:
        parts.append(f"Peak load is {shock['load_peak_ratio']:.2f}x normal which pushes prices up the supply curve.")
    if shock["dc_load_shock_mw"]:
        if m.name == "PJM":
            parts.append(f"Data center load adds {shock['dc_load_shock_mw']:.0f} MW to the peak.")
        else:
            parts.append(f"Large-load demand changes the peak by {shock['dc_load_shock_mw']:+.0f} MW.")
    if shock.get("ny_gas_basis_usd", 0.0):
        parts.append(f"The New York gas basis moves by {shock['ny_gas_basis_usd']:+.1f} dollars per MMBtu.")
    if shock["wh_onpeak_pct"]:
        parts.append(f"{ref} on-peak price carries a further {shock['wh_onpeak_pct']:+.0f}% residual move.")
    if shock["dom_minus_wh_usd"]:
        parts.append(f"The {pocket} minus {ref} congestion spread widens by {shock['dom_minus_wh_usd']:+.1f} dollars per MWh.")
    if shock["dart_pct"]:
        parts.append(f"Real-time prices differ from day-ahead by {shock['dart_pct']:+.0f}%.")
    if shock["spike_days"]:
        parts.append(
            f"{int(shock['spike_days'])} spike days have a {ref} on-peak daily average of {shock['spike_daily_avg_usd']:.0f} dollars per MWh."
        )
    if loss_usd is not None:
        parts.append(f"The book loses {loss_usd / 1e6:.2f} million dollars.")
    return " ".join(parts)


@dataclass
class Evaluator:
    """Counts engine calls against a budget, caches repeats and stores one record per evaluation."""

    engine_fn: EngineFn
    budget: int
    arm: str
    seed: int
    season: str
    horizon_days: int
    target_usd: float
    rules_fn: RulesFn = default_hard_rules
    q_max: float = config.Q_ADVERSE_MAX
    records: list[dict] = field(default_factory=list)
    _cache: dict = field(default_factory=dict)

    @property
    def used(self) -> int:
        """Engine evaluations spent so far."""
        return len(self.records)

    def evaluate(
        self, shock: dict, iteration: int, extra: Mapping[str, Any] | None = None, limit: int | None = None
    ) -> dict | None:
        """Evaluate one shock; returns the engine result (None if the engine rejected the shock).

        Repeated identical shocks are served from the cache and do not use budget.
        Raises BudgetExhausted when the budget (or the optional lower `limit` on total calls) is spent.
        """
        key = tuple(round(float(shock[k]), 9) for k in config.SHOCK_KEYS)
        if key in self._cache:
            return self._cache[key]
        if self.used >= (self.budget if limit is None else min(self.budget, limit)):
            raise BudgetExhausted
        try:
            result = self.engine_fn(dict(shock))
        except ValueError:
            result = None
        self._cache[key] = result
        driver = classify_driver(shock, self.season)
        loss = None if result is None else float(-result["pnl_total"])
        context = {"horizon_days": self.horizon_days, "driver_class": driver, "season": self.season}
        failed = self.rules_fn(dict(shock), result, context)
        breach = bool(result is not None and loss >= self.target_usd and result["q"] < self.q_max and not failed)
        self.records.append(
            {
                "scenario_id": f"{self.arm[:1].upper()}-{self.seed}-{self.used + 1:03d}",
                "arm": self.arm,
                "seed": self.seed,
                "iteration": iteration,
                "driver_class": driver,
                "season": self.season,
                "horizon_days": self.horizon_days,
                "narrative": template_narrative(shock, self.season, driver, loss) if self.arm == "optimizer" else "",
                "shocks": dict(shock),
                "analogue": {"event": "", "dates": "", "claimed": {}, "source": ""},
                "confidence": "low",
                "engine": result,
                "loss_usd": loss,
                "rules_failed": failed,
                "rules_passed": not failed,
                "breach": breach,
                **(dict(extra) if extra else {}),
            }
        )
        return result
