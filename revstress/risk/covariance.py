"""Robust seasonal covariance of the Gaussian-core factors [g, l, s, c, d] (plan sec 4).

Default: Ledoit-Wolf shrinkage on deviations from a seasonal median, rolling window (3 years;
5 years in winter, where only about 90 days per year exist). Alternative: method="mcd"
(sklearn MinCovDet, robust location and scatter, no shrinkage; can be near-singular in small samples).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf, MinCovDet

from .. import config

CORE: tuple[str, ...] = config.GAUSSIAN_CORE_FACTORS
DEFAULT_WINDOW_YEARS: dict[str, int] = {"winter": 5, "summer": 3, "shoulder": 3}
MIN_OBS: int = 60


@dataclass(frozen=True)
class SeasonCov:
    """Robust location and scatter of the core factors for one season."""

    season: str
    mu: np.ndarray
    cov: np.ndarray
    precision: np.ndarray
    n_obs: int
    start: pd.Timestamp
    end: pd.Timestamp
    method: str
    shrinkage: float | None


def fit_season_cov(x: pd.DataFrame, season: str, method: str = "ledoit_wolf", seed: int = 0) -> SeasonCov:
    """Fit mu (median) and Sigma for one season from rows x with CORE columns and 'date'."""
    X = x[list(CORE)].to_numpy(dtype=float)
    if len(X) < len(CORE) + 5:
        raise ValueError(f"too few observations for season {season}: {len(X)}")
    shrinkage = None
    if method == "ledoit_wolf":
        mu = np.median(X, axis=0)
        dev = X - mu
        scale = dev.std(axis=0)
        scale = np.where(scale > 0, scale, 1.0)  # shrink in standardized units: factors mix log points and USD/MWh
        lw = LedoitWolf(assume_centered=True).fit(dev / scale)
        cov, shrinkage = lw.covariance_ * np.outer(scale, scale), float(lw.shrinkage_)
    elif method == "mcd":
        mcd = MinCovDet(random_state=seed).fit(X)
        mu, cov = mcd.location_, mcd.covariance_
    else:
        raise ValueError(f"unknown covariance method: {method}")
    cov = 0.5 * (cov + cov.T)
    return SeasonCov(
        season=season,
        mu=np.asarray(mu, dtype=float),
        cov=cov,
        precision=np.linalg.inv(cov),
        n_obs=len(X),
        start=pd.Timestamp(x["date"].min()),
        end=pd.Timestamp(x["date"].max()),
        method=method,
        shrinkage=shrinkage,
    )


def fit_all_seasons(
    factors: pd.DataFrame,
    window_years: dict[str, int] | None = None,
    method: str = "ledoit_wolf",
    min_obs: int = MIN_OBS,
    seed: int = 0,
) -> dict[str, SeasonCov]:
    """Per-season rolling-window fits ending at the last date in factors (caller enforces as_of).

    If a season has fewer than min_obs rows in its window, all rows of that season are used.
    """
    window_years = DEFAULT_WINDOW_YEARS if window_years is None else window_years
    end = pd.Timestamp(factors["date"].max())
    out: dict[str, SeasonCov] = {}
    for season in config.SEASONS:
        sub = factors[factors["season"] == season]
        if sub.empty:
            continue
        recent = sub[sub["date"] > end - pd.DateOffset(years=window_years[season])]
        out[season] = fit_season_cov(recent if len(recent) >= min_obs else sub, season, method, seed)
    return out


def mahalanobis_sq(x: np.ndarray, mu: np.ndarray, precision: np.ndarray) -> np.ndarray:
    """Squared Mahalanobis distance of rows of x (n, k) to mu under a precision matrix; returns (n,)."""
    z = np.atleast_2d(x) - mu
    return np.einsum("ij,jk,ik->i", z, precision, z)
