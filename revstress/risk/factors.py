"""Explicit factors x = [g, l, T, s, c, d] and the price model (plan sec 4).

g = log Henry Hub ($/MMBtu); l = log(daily peak load / normal); T = hdd + cdd (degF-days, one is 0);
s = residual of log WH on-peak price ($/MWh) after gas and load; c = DOM - WH on-peak spread ($/MWh);
d = log(RT_on / DA_on) at WH.
Price model: log P_WH = a_season + b1 g + b2 l + b3 l^2 + e, by numpy least squares.
Normal load is the month-of-year mean of load_peak_mw in the fit sample (a simple seasonal normal,
not a weather-normal regression).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config
from ..panel import season_labels

FACTOR_COLUMNS: tuple[str, ...] = config.FACTOR_NAMES
PRICE_FLOOR_USD: float = 1.0  # $/MWh floor before taking logs
GAS_FLOOR_USD: float = 0.01  # $/MMBtu floor before taking logs


@dataclass(frozen=True)
class PriceModel:
    """Fitted log-price regression and load normals."""

    intercepts: dict[str, float]
    b_gas: float
    b_load: float
    b_load2: float
    resid_sd: float
    r2: float
    n_obs: int
    load_normal_mw_by_month: dict[int, float]
    harm: tuple[float, ...] = ()  # daily-model terms: sin1, cos1, sin2, cos2, l*sin1, l*cos1 (empty: season intercepts only)


def harmonic_design(dates: pd.Series | pd.DatetimeIndex, l: np.ndarray) -> np.ndarray:
    """Smooth seasonal terms of the daily model: 2 annual harmonics and load x first harmonic (6 columns)."""
    doy = 2 * np.pi * pd.DatetimeIndex(dates).dayofyear.to_numpy(dtype=float) / 365.25
    s1, c1 = np.sin(doy), np.cos(doy)
    return np.column_stack([s1, c1, np.sin(2 * doy), np.cos(2 * doy), l * s1, l * c1])


def _log_price(p: np.ndarray) -> np.ndarray:
    return np.log(np.maximum(np.asarray(p, dtype=float), PRICE_FLOOR_USD))


def _design(g: np.ndarray, l: np.ndarray, seasons: np.ndarray) -> np.ndarray:
    cols = [(seasons == s).astype(float) for s in config.SEASONS]
    return np.column_stack(cols + [g, l, l**2])


def load_normal_mw(dates: pd.Series | pd.DatetimeIndex, model: PriceModel) -> np.ndarray:
    """Normal peak load (MW) for each date: month-of-year mean from the fit sample."""
    months = pd.DatetimeIndex(dates).month
    return np.array([model.load_normal_mw_by_month[int(m)] for m in months], dtype=float)


def fit_price_model(df: pd.DataFrame, daily: bool = True) -> PriceModel:
    """Fit log P_WH,on = a_season + b1 g + b2 l + b3 l^2 [+ daily-model seasonal harmonics and load x harmonic] on df.

    daily=True (default) adds the harmonic terms retained by the walk-forward daily-model test (scripts/daily_factor_model.py);
    daily=False reproduces the earlier season-intercept model. Returns PriceModel."""
    normals = df.groupby(pd.DatetimeIndex(df["date"]).month)["load_peak_mw"].mean()
    overall = float(df["load_peak_mw"].mean())
    by_month = {m: float(normals.get(m, overall)) for m in range(1, 13)}
    shell = PriceModel({}, 0.0, 0.0, 0.0, 0.0, 0.0, 0, by_month)
    g = np.log(np.maximum(df["hh_usd"].to_numpy(dtype=float), GAS_FLOOR_USD))
    l = np.log(df["load_peak_mw"].to_numpy(dtype=float) / load_normal_mw(df["date"], shell))
    y = _log_price(df["wh_on"].to_numpy())
    X = _design(g, l, season_labels(df["date"]))
    if daily:
        X = np.column_stack([X, harmonic_design(df["date"], l)])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return PriceModel(
        intercepts={s: float(b) for s, b in zip(config.SEASONS, beta[:3])},
        b_gas=float(beta[3]),
        b_load=float(beta[4]),
        b_load2=float(beta[5]),
        resid_sd=float(resid.std(ddof=1)),
        r2=float(1.0 - (resid**2).sum() / ss_tot) if ss_tot > 0 else float("nan"),
        n_obs=len(df),
        load_normal_mw_by_month=by_month,
        harm=tuple(float(b) for b in beta[6:]) if daily else (),
    )


def compute_factors(df: pd.DataFrame, model: PriceModel) -> pd.DataFrame:
    """Daily factors for a panel or scenario path. Returns DataFrame: date, season, g, l, T, s, c, d."""
    seasons = season_labels(df["date"])
    g = np.log(np.maximum(df["hh_usd"].to_numpy(dtype=float), GAS_FLOOR_USD))
    l = np.log(df["load_peak_mw"].to_numpy(dtype=float) / load_normal_mw(df["date"], model))
    intercept = np.array([model.intercepts[s] for s in seasons])
    fitted = intercept + model.b_gas * g + model.b_load * l + model.b_load2 * l**2
    if model.harm:
        fitted = fitted + harmonic_design(df["date"], l) @ np.asarray(model.harm)
    s = _log_price(df["wh_on"].to_numpy()) - fitted
    return pd.DataFrame(
        {
            "date": df["date"].to_numpy(),
            "season": seasons,
            "g": g,
            "l": l,
            "T": df["hdd"].to_numpy(dtype=float) + df["cdd"].to_numpy(dtype=float),
            "s": s,
            "c": df["dom_on"].to_numpy(dtype=float) - df["wh_on"].to_numpy(dtype=float),
            "d": _log_price(df["rt_wh_on"].to_numpy()) - _log_price(df["da_wh_on"].to_numpy()),
        }
    )
