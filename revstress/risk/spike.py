"""Spike component, separate from the Gaussian core (plan sec 4).

Spike day: WH on-peak above the SPIKE_SEASON_PERCENTILE of its season in the fit sample.
Probability: logistic on [standardized l, T_extreme] (sklearn); T_extreme = max(z-score of T within
its season, 0). No outage proxy exists in the daily panel.
Size: generalized Pareto (peaks over threshold, scipy) on relative excess P/threshold - 1, pooled over
seasons. The shape is poorly determined: a bootstrap 5-95% range is reported with the point estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression

from .. import config

MIN_EXCEEDANCES_FOR_GPD: int = 8


@dataclass(frozen=True)
class SpikeModel:
    """Fitted spike model. Thresholds in $/MWh; GPD shape/scale are for relative excess (dimensionless)."""

    thresholds_usd: dict[str, float]
    hist_exceed_share: dict[str, float]
    t_mean: dict[str, float]
    t_sd: dict[str, float]
    l_mean: float
    l_sd: float
    coef: tuple[float, float]
    intercept: float
    gpd_shape: float | None
    gpd_scale: float | None
    gpd_shape_range: tuple[float, float] | None
    n_exceed: int
    relative_excesses: np.ndarray
    n_days: int


def t_extreme(T: np.ndarray, seasons: np.ndarray, t_mean: dict[str, float], t_sd: dict[str, float]) -> np.ndarray:
    """One-sided standardized degree-day extremeness, max(z, 0), per row."""
    mean = np.array([t_mean.get(s, 0.0) for s in seasons])
    sd = np.array([max(t_sd.get(s, 1.0), 1e-9) for s in seasons])
    return np.maximum((np.asarray(T, dtype=float) - mean) / sd, 0.0)


def _features(l_mean: float, l_sd: float, l: np.ndarray, te: np.ndarray) -> np.ndarray:
    return np.column_stack([(np.asarray(l, dtype=float) - l_mean) / l_sd, te])


def fit_spike_model(
    factors: pd.DataFrame,
    wh_on: np.ndarray,
    percentile: float = config.SPIKE_SEASON_PERCENTILE,
    seed: int = 0,
    n_boot: int = 200,
) -> SpikeModel:
    """Fit spike thresholds, logistic probability and GPD tail.

    factors needs columns season, l, T; wh_on is the WH on-peak price in $/MWh (same row order).
    """
    wh_on = np.asarray(wh_on, dtype=float)
    seasons = factors["season"].to_numpy()
    thr: dict[str, float] = {}
    share: dict[str, float] = {}
    t_mean: dict[str, float] = {}
    t_sd: dict[str, float] = {}
    spike = np.zeros(len(factors), dtype=bool)
    for s in config.SEASONS:
        m = seasons == s
        if not m.any():
            continue
        thr[s] = float(np.percentile(wh_on[m], percentile))
        spike[m] = wh_on[m] > thr[s]
        share[s] = float(spike[m].mean())
        t_mean[s] = float(factors.loc[m, "T"].mean())
        t_sd[s] = float(factors.loc[m, "T"].std(ddof=1))
    l = factors["l"].to_numpy(dtype=float)
    l_mean, l_sd = float(l.mean()), float(max(l.std(ddof=1), 1e-9))
    te = t_extreme(factors["T"].to_numpy(), seasons, t_mean, t_sd)
    X = _features(l_mean, l_sd, l, te)
    if spike.sum() >= 3 and (~spike).sum() >= 3:
        clf = LogisticRegression(C=1.0, max_iter=1000).fit(X, spike)
        coef = (float(clf.coef_[0, 0]), float(clf.coef_[0, 1]))
        intercept = float(clf.intercept_[0])
    else:
        rate = float(np.clip(spike.mean(), 1e-6, 1 - 1e-6))
        coef, intercept = (0.0, 0.0), float(np.log(rate / (1.0 - rate)))
    thr_row = np.array([thr[s] for s in seasons])
    excess = (wh_on / thr_row - 1.0)[spike]
    shape = scale = None
    shape_range: tuple[float, float] | None = None
    if len(excess) >= MIN_EXCEEDANCES_FOR_GPD:
        shape, _, scale = stats.genpareto.fit(excess, floc=0.0)
        rng = np.random.default_rng(seed)
        boots = []
        for _ in range(n_boot):
            sample = rng.choice(excess, size=len(excess), replace=True)
            try:
                boots.append(float(stats.genpareto.fit(sample, floc=0.0)[0]))
            except Exception:
                continue
        if boots:
            lo, hi = np.percentile(boots, [5.0, 95.0])
            shape_range = (float(min(lo, shape)), float(max(hi, shape)))
        shape, scale = float(shape), float(scale)
    return SpikeModel(
        thresholds_usd=thr,
        hist_exceed_share=share,
        t_mean=t_mean,
        t_sd=t_sd,
        l_mean=l_mean,
        l_sd=l_sd,
        coef=coef,
        intercept=intercept,
        gpd_shape=shape,
        gpd_scale=scale,
        gpd_shape_range=shape_range,
        n_exceed=int(len(excess)),
        relative_excesses=np.sort(excess),
        n_days=len(factors),
    )


def spike_probability(model: SpikeModel, l: np.ndarray, T: np.ndarray, seasons: np.ndarray) -> np.ndarray:
    """Logistic daily spike probability in [0, 1] for each row."""
    te = t_extreme(T, np.asarray(seasons), model.t_mean, model.t_sd)
    z = model.intercept + _features(model.l_mean, model.l_sd, l, te) @ np.asarray(model.coef)
    return 1.0 / (1.0 + np.exp(-z))


def spike_exceedance(
    model: SpikeModel,
    seasons: np.ndarray,
    l: np.ndarray,
    T: np.ndarray,
    wh_on: np.ndarray,
    spike_flags: np.ndarray | None = None,
) -> dict:
    """Score a path's spike overlay by empirical exceedance, separately from the Gaussian core.

    Returns spike count, expected count under the logistic model, Poisson upper-tail probability of
    the count, size ratio to the season threshold, and empirical / GPD survival of the largest spike.
    """
    seasons = np.asarray(seasons)
    wh_on = np.asarray(wh_on, dtype=float)
    thr = np.array([model.thresholds_usd[s] for s in seasons])
    flags = wh_on > thr if spike_flags is None else np.asarray(spike_flags, dtype=bool)
    p = spike_probability(model, l, T, seasons)
    k, lam = int(flags.sum()), float(p.sum())
    out: dict = {
        "n_spike_days": k,
        "n_days": int(len(seasons)),
        "share_days_above_threshold": float((wh_on > thr).mean()),
        "hist_exceed_share_by_season": dict(model.hist_exceed_share),
        "expected_spike_days": lam,
        "poisson_tail_p": float(stats.poisson.sf(k - 1, lam)) if k > 0 else 1.0,
        "max_size_ratio": None,
        "empirical_size_exceedance": None,
        "gpd_size_survival": None,
        "gpd_shape": model.gpd_shape,
        "gpd_shape_range": model.gpd_shape_range,
    }
    if k > 0:
        top = float((wh_on[flags] / thr[flags]).max())
        out["max_size_ratio"] = top
        excess = top - 1.0
        if len(model.relative_excesses):
            out["empirical_size_exceedance"] = float((model.relative_excesses >= excess).mean())
        if model.gpd_shape is not None:
            out["gpd_size_survival"] = float(
                stats.genpareto.sf(max(excess, 0.0), model.gpd_shape, loc=0.0, scale=model.gpd_scale)
            )
    return out
