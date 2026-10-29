"""Plausibility scorer and fitted risk model (plan sec 4).

D^2 is the squared Mahalanobis distance on the Gaussian-core factors [g, l, s, c, d] using the robust
mu and Sigma of the day's season. A path is scored by its worst (max D^2) shocked day; a historical
10-day window is scored by its max daily D^2, so the two are comparable.

q(s) = share of NON-OVERLAPPING 10-day historical windows with window D^2 >= D^2(s). With about 7 years
this is about 250 windows and fewer than 10 independent extreme events: q is a RANK against history,
NOT a probability. "q below 1%" means "not seen in the sample".

Severity: adverse if 0.01 <= q <= 0.05; severe if q < 0.01 and no marginal beyond its limit; implausible
if any marginal exceeds its limit or a hard rule fails; otherwise ordinary (q > 0.05).
Marginal limit = historical (season) max x 1.25 for level-like factors (g, l, s, d are logs, so
max + log 1.25; c and T are linear, so max + 0.25|max|); symmetric on the lower side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from .. import config
from ..panel import validate_panel
from .covariance import CORE, SeasonCov, fit_all_seasons, mahalanobis_sq
from .factors import FACTOR_COLUMNS, PriceModel, compute_factors, fit_price_model
from .spike import SpikeModel, fit_spike_model, spike_exceedance

LOG_FACTORS: tuple[str, ...] = ("g", "l", "s", "d")
HARD_RULE_TOL_USD: float = 1e-6
WEATHER_PERCENTILE: float = 90.0
SYNTHETIC_NOTE: str = "SYNTHETIC DATA: not a real result."


@dataclass(frozen=True)
class RiskModel:
    """Fitted risk model; uses only data with date <= as_of."""

    as_of: pd.Timestamp
    max_date_used: pd.Timestamp
    min_date_used: pd.Timestamp
    include_pre_break: bool
    price_model: PriceModel
    season_cov: dict[str, SeasonCov]
    spike: SpikeModel
    history: pd.DataFrame  # fit-sample factors plus 'd2'
    window_d2: np.ndarray
    window_start: pd.DatetimeIndex
    window_end: pd.DatetimeIndex
    limits: dict[str, dict[str, tuple[float, float]]]  # season -> factor -> (lower, upper)
    t_extreme_threshold: dict[str, float]  # season -> T at WEATHER_PERCENTILE
    robust_sd: np.ndarray
    synthetic: bool


def _limit(lo: float, hi: float, factor: str) -> tuple[float, float]:
    if factor in LOG_FACTORS:
        m = float(np.log(config.IMPLAUSIBLE_MARGINAL_MULT))
        return lo - m, hi + m
    k = config.IMPLAUSIBLE_MARGINAL_MULT - 1.0
    return lo - k * abs(lo), hi + k * abs(hi)


def _daily_d2(factors: pd.DataFrame, cov: Mapping[str, SeasonCov]) -> np.ndarray:
    out = np.full(len(factors), np.nan)
    seasons = factors["season"].to_numpy()
    X = factors[list(CORE)].to_numpy(dtype=float)
    for s, sc in cov.items():
        m = seasons == s
        if m.any():
            out[m] = mahalanobis_sq(X[m], sc.mu, sc.precision)
    return out


def _windows(history: pd.DataFrame, size: int) -> tuple[np.ndarray, pd.DatetimeIndex, pd.DatetimeIndex]:
    """Non-overlapping blocks of `size` consecutive calendar days; max daily D^2 per block."""
    d2 = history["d2"].to_numpy()
    dates = pd.DatetimeIndex(history["date"])
    vals, starts, ends = [], [], []
    for i in range(0, len(history) - size + 1, size):
        if (dates[i + size - 1] - dates[i]).days != size - 1:
            continue
        vals.append(float(np.max(d2[i : i + size])))
        starts.append(dates[i])
        ends.append(dates[i + size - 1])
    return np.array(vals), pd.DatetimeIndex(starts), pd.DatetimeIndex(ends)


def fit_risk_model(
    panel: pd.DataFrame,
    as_of: str | pd.Timestamp | None = None,
    include_pre_break: bool = True,
    covariance_method: str = "ledoit_wolf",
    window_years: dict[str, int] | None = None,
    seed: int = 0,
    n_boot: int = 200,
) -> RiskModel:
    """Fit factors, price model, seasonal covariance, spike model and history using date <= as_of only.

    include_pre_break=False drops dates before the active market's primary structural break (config.break_cutoff(): PJM 2022-10-01 reserve redesign, NYISO 2016-06-22 scarcity pricing) from every step.
    Needs the full-book panel columns. Deterministic given seed.
    """
    validate_panel(panel, fallback=False)
    as_of_ts = pd.Timestamp(panel["date"].max() if as_of is None else as_of)
    df = panel[panel["date"] <= as_of_ts]
    if not include_pre_break:
        df = df[df["date"] >= pd.Timestamp(config.break_cutoff())]
    df = df.reset_index(drop=True)
    if len(df) < 200:
        raise ValueError(f"too few rows to fit risk model: {len(df)}")
    pm = fit_price_model(df)
    fac = compute_factors(df, pm)
    cov = fit_all_seasons(fac, window_years=window_years, method=covariance_method, seed=seed)
    fac["d2"] = _daily_d2(fac, cov)
    wd2, ws, we = _windows(fac, config.WINDOW_DAYS)
    limits: dict[str, dict[str, tuple[float, float]]] = {}
    t_thr: dict[str, float] = {}
    for s in cov:
        sub = fac[fac["season"] == s]
        limits[s] = {f: _limit(float(sub[f].min()), float(sub[f].max()), f) for f in FACTOR_COLUMNS}
        t_thr[s] = float(np.percentile(sub["T"], WEATHER_PERCENTILE))
    dev = np.concatenate(
        [fac.loc[fac["season"] == s, list(FACTOR_COLUMNS)].to_numpy() - fac.loc[fac["season"] == s, list(FACTOR_COLUMNS)].median().to_numpy() for s in cov]
    )
    sd = 1.4826 * np.median(np.abs(dev - np.median(dev, axis=0)), axis=0)
    sd = np.where(sd > 1e-9, sd, np.maximum(dev.std(axis=0), 1e-9))
    spike = fit_spike_model(fac, df["wh_on"].to_numpy(), seed=seed, n_boot=n_boot)
    return RiskModel(
        as_of=as_of_ts,
        max_date_used=pd.Timestamp(df["date"].max()),
        min_date_used=pd.Timestamp(df["date"].min()),
        include_pre_break=include_pre_break,
        price_model=pm,
        season_cov=cov,
        spike=spike,
        history=fac,
        window_d2=wd2,
        window_start=ws,
        window_end=we,
        limits=limits,
        t_extreme_threshold=t_thr,
        robust_sd=sd,
        synthetic="synthetic_source" in panel.columns,
    )


def standardize_core(model: RiskModel, season: str, factors: Mapping[str, float]) -> dict[str, float]:
    """Robust z of the core factors: (x_f - season median_f) / robust_sd_f. Unitless; keys config.GAUSSIAN_CORE_FACTORS."""
    hist = model.history[model.history["season"] == season]
    out = {}
    for f in CORE:
        j = FACTOR_COLUMNS.index(f)
        out[f] = float((float(factors[f]) - float(hist[f].median())) / model.robust_sd[j])
    return out


def severity_class(q: float, marginal_exceeded: bool, hard_rule_failed: bool) -> str:
    """Return 'implausible' | 'severe' | 'adverse' | 'ordinary' from rank q and rule outcomes."""
    if hard_rule_failed or marginal_exceeded:
        return "implausible"
    if q < config.Q_SEVERE_MAX:
        return "severe"
    if q <= config.Q_ADVERSE_MAX:
        return "adverse"
    return "ordinary"


def _percentile_rank(values: np.ndarray, x: float) -> float:
    """Percentile (0-100) of x within values (share <= x)."""
    return float(100.0 * np.mean(values <= x))


def score_scenario(
    scenario: pd.DataFrame | Mapping[str, float],
    model: RiskModel,
    season: str | None = None,
) -> dict:
    """Score a scenario path (DataFrame as returned by shock.apply_shock) or a single factor vector.

    A mapping must have g, l, s, c, d (T optional, defaults to the season's median) and uses `season`
    (argument or key 'season'). Returns a dict with: d2, q (rank, not probability), n_windows,
    severity, hard_rule_failures, marginal_percentiles (0-100, within the season's history),
    marginals_exceeded, nearest_date, nearest_distance (standardized units), worst_day, factors_worst,
    spike (path inputs only), season, notes.
    """
    if isinstance(scenario, pd.DataFrame):
        fac = compute_factors(scenario, model.price_model)
        shocked = scenario["shock_day"].to_numpy(dtype=bool) if "shock_day" in scenario.columns else None
        mask = shocked if shocked is not None and shocked.any() else np.ones(len(fac), dtype=bool)
        is_path = True
    else:
        s_name = season or scenario.get("season")
        if s_name not in config.SEASONS:
            raise ValueError("a factor-vector scenario needs season in {winter, summer, shoulder}")
        missing = [k for k in CORE if k not in scenario]
        if missing:
            raise ValueError(f"missing factors: {missing}")
        t_default = float(model.history.loc[model.history["season"] == s_name, "T"].median())
        row = {k: float(scenario[k]) for k in CORE}
        row["T"] = float(scenario.get("T", t_default))
        fac = pd.DataFrame([{"date": pd.NaT, "season": s_name, **row}])[["date", "season", *FACTOR_COLUMNS]]
        mask = np.ones(1, dtype=bool)
        is_path = False
    missing_season = set(fac["season"]) - set(model.season_cov)
    if missing_season:
        raise ValueError(f"no fitted covariance for seasons {sorted(missing_season)}")
    d2_all = _daily_d2(fac, model.season_cov)
    idx = np.flatnonzero(mask)
    worst = int(idx[np.argmax(d2_all[idx])])
    d2 = float(d2_all[worst])
    q = float(np.mean(model.window_d2 >= d2)) if len(model.window_d2) else float("nan")
    wseason = str(fac.loc[worst, "season"])
    x_worst = {f: float(fac.loc[worst, f]) for f in FACTOR_COLUMNS}

    hist_s = model.history[model.history["season"] == wseason]
    percentiles = {f: _percentile_rank(hist_s[f].to_numpy(), x_worst[f]) for f in FACTOR_COLUMNS}

    exceeded: list[dict] = []
    for i in idx:
        lim = model.limits[str(fac.loc[i, "season"])]
        for f in FACTOR_COLUMNS:
            v = float(fac.loc[i, f])
            lo, hi = lim[f]
            if v > hi or v < lo:
                exceeded.append({"factor": f, "value": v, "lower": lo, "upper": hi, "row": int(i)})
    exceeded = sorted({(e["factor"]): e for e in exceeded}.values(), key=lambda e: e["factor"])

    failures: list[str] = []
    if is_path:
        price_cols = [c for c in ("wh_on", "wh_off", "da_wh_on", "da_wh_off", "rt_wh_on", "rt_wh_off") if c in scenario.columns]
        mkt = config.active_market()
        if any((scenario[c] > mkt.energy_cap_usd + HARD_RULE_TOL_USD).any() for c in price_cols):
            failures.append(mkt.cap_failure_label)
    sub = fac.loc[mask]
    for s_name in ("winter", "summer"):
        ss = sub[sub["season"] == s_name]
        if len(ss) and s_name in model.t_extreme_threshold:
            if ss["T"].mean() > model.t_extreme_threshold[s_name] and ss["l"].mean() < 0.0:
                failures.append(f"extreme_weather_with_falling_load_{s_name}")

    hz = (fac.loc[[worst], list(FACTOR_COLUMNS)].to_numpy(dtype=float))
    h = model.history
    med = h.groupby("season")[list(FACTOR_COLUMNS)].transform("median").to_numpy()
    hz_hist = (h[list(FACTOR_COLUMNS)].to_numpy() - med) / model.robust_sd
    med_s = hist_s[list(FACTOR_COLUMNS)].median().to_numpy()
    dist = np.linalg.norm(hz_hist - (hz - med_s) / model.robust_sd, axis=1)
    j = int(np.argmin(dist))

    out: dict = {
        "d2": d2,
        "q": q,
        "q_is_probability": False,
        "n_windows": int(len(model.window_d2)),
        "n_days_scored": int(len(idx)),
        "season": wseason,
        "severity": severity_class(q, bool(exceeded), bool(failures)),
        "hard_rule_failures": failures,
        "marginals_exceeded": exceeded,
        "marginal_percentiles": percentiles,
        "nearest_date": str(pd.Timestamp(h["date"].iloc[j]).date()),
        "nearest_distance": float(dist[j]),
        "worst_day": None if pd.isna(fac.loc[worst, "date"]) else str(pd.Timestamp(fac.loc[worst, "date"]).date()),
        "factors_worst": x_worst,
        "spike": None,
        "notes": "q is a rank against non-overlapping 10-day historical windows, not a probability; q=0 means not seen in sample.",
    }
    if is_path:
        flags = scenario["spike_day"].to_numpy(dtype=bool) if "spike_day" in scenario.columns else None
        out["spike"] = spike_exceedance(
            model.spike,
            fac["season"].to_numpy(),
            fac["l"].to_numpy(),
            fac["T"].to_numpy(),
            scenario["wh_on"].to_numpy(),
            flags,
        )
    if model.synthetic:
        out["synthetic_warning"] = SYNTHETIC_NOTE
    return out
