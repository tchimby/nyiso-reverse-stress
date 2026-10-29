"""Daily panel contract (one row per calendar day) and validators.

Columns and units:
  date          datetime64[ns], strictly increasing, unique
  wh_on, wh_off Western Hub RT on-peak / off-peak daily average, $/MWh; settlement price,
                must equal rt_wh_on / rt_wh_off
  dom_on, dom_off  Dominion (DOM) on-peak / off-peak daily average, $/MWh (hub used as zone proxy)
  da_wh_off, rt_wh_off, da_wh_on, rt_wh_on  Western Hub DA and RT averages, $/MWh
  load_peak_mw  daily peak metered load, MW
  hh_usd        Henry Hub spot, $/MMBtu
  hdd, cdd      heating / cooling degree days (degF-days, >= 0)
On-peak = HE8-23 on weekdays that are not NERC holidays (16 h); every other hour is off-peak, so on a weekend
or NERC holiday the day has 0 on-peak and 24 off-peak hours. Optional column 'is_onpeak_day' (bool) overrides
the calendar rule (see onpeak_day_flags).
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from . import config

PANEL_COLUMNS: tuple[str, ...] = (
    "date",
    "wh_on",
    "wh_off",
    "dom_on",
    "dom_off",
    "da_wh_off",
    "rt_wh_off",
    "da_wh_on",
    "rt_wh_on",
    "load_peak_mw",
    "hh_usd",
    "hdd",
    "cdd",
)
# Columns needed by the fallback book (P1, P4, P6)
FALLBACK_REQUIRED_COLUMNS: tuple[str, ...] = ("date", "wh_on", "hh_usd")


class PanelError(ValueError):
    """Raised when a panel violates the contract."""


def validate_panel(
    df: pd.DataFrame,
    fallback: bool | None = None,
    check_settlement: bool = True,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """Validate a daily panel and return it unchanged.

    Raises PanelError on missing columns, NaN/inf in required columns, non-datetime or
    non-strictly-increasing dates, negative load/degree days, or (full book only, when
    check_settlement) wh_on != rt_wh_on / wh_off != rt_wh_off beyond tol ($/MWh).
    fallback=None reads config.FALLBACK_BOOK; fallback requires only date, wh_on, hh_usd.
    """
    if fallback is None:
        fallback = config.FALLBACK_BOOK
    required = FALLBACK_REQUIRED_COLUMNS if fallback else PANEL_COLUMNS
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise PanelError(f"missing columns: {missing}")
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        raise PanelError("column 'date' must be datetime64")
    values = df[[c for c in required if c != "date"]]
    if values.isna().any().any() or df["date"].isna().any():
        bad = [c for c in required if df[c].isna().any()]
        raise PanelError(f"NaN in columns: {bad}")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise PanelError("non-finite values in panel")
    if len(df) > 1 and not (df["date"].diff().dropna() > pd.Timedelta(0)).all():
        raise PanelError("dates must be strictly increasing (no duplicates)")
    for col in ("load_peak_mw", "hdd", "cdd", "hh_usd"):
        if col in required and (df[col] < 0).any():
            raise PanelError(f"negative values in '{col}'")
    if not fallback and check_settlement:
        for a, b in (("wh_on", "rt_wh_on"), ("wh_off", "rt_wh_off")):
            if (df[a] - df[b]).abs().max() > tol:
                raise PanelError(f"'{a}' must equal '{b}' (settlement = real time)")
    return df


def season_labels(dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Season name ('winter', 'summer', 'shoulder') for each date; returns array of str."""
    months = pd.DatetimeIndex(dates).month
    return np.array([config.MONTH_TO_SEASON[int(m)] for m in months])


def _observed(d: pd.Timestamp) -> pd.Timestamp:
    """NERC observance: a holiday on Sunday is observed Monday; one on Saturday is not observed."""
    return d + pd.Timedelta(days=1) if d.dayofweek == 6 else d


def nerc_holidays(year: int) -> set[pd.Timestamp]:
    """NERC off-peak holidays of a year (as observed): New Year's Day, Memorial Day, Independence Day, Labor Day,
    Thanksgiving, Christmas Day."""
    may = pd.date_range(f"{year}-05-01", f"{year}-05-31")
    sep = pd.date_range(f"{year}-09-01", f"{year}-09-07")
    nov = pd.date_range(f"{year}-11-01", f"{year}-11-30")
    memorial = may[may.dayofweek == 0][-1]
    labor = sep[sep.dayofweek == 0][0]
    thanksgiving = nov[nov.dayofweek == 3][3]
    fixed = [pd.Timestamp(year, 1, 1), pd.Timestamp(year, 7, 4), pd.Timestamp(year, 12, 25)]
    return {_observed(d) for d in fixed} | {memorial, labor, thanksgiving}


def onpeak_day_flags(df: pd.DataFrame) -> np.ndarray:
    """True on days that have on-peak hours: weekdays that are not NERC holidays (column 'is_onpeak_day' if present)."""
    if "is_onpeak_day" in df.columns:
        return df["is_onpeak_day"].to_numpy(dtype=bool)
    dates = pd.DatetimeIndex(df["date"])
    holidays = set()
    for y in range(int(dates.year.min()) - 1, int(dates.year.max()) + 2):  # observed New Year can land in the prior year
        holidays |= nerc_holidays(y)
    return np.array([(d.dayofweek < 5) and (d.normalize() not in holidays) for d in dates], dtype=bool)


def gas_price_usd(df: pd.DataFrame, basis: Mapping[str, float] | None = None) -> np.ndarray:
    """Gas price G = Henry Hub + stated seasonal basis, $/MMBtu, one value per row."""
    basis = config.gas_basis_by_season() if basis is None else basis
    seasons = season_labels(df["date"])
    b = np.array([basis[s] for s in seasons], dtype=float)
    return df["hh_usd"].to_numpy(dtype=float) + b


def resolve_load_normal(df: pd.DataFrame, default_mw: float | None) -> np.ndarray:
    """Seasonal-normal peak load, MW, per row.

    Uses column 'load_normal_mw' if present, else default_mw, else the median of load_peak_mw.
    """
    if "load_normal_mw" in df.columns:
        return df["load_normal_mw"].to_numpy(dtype=float)
    if default_mw is None:
        default_mw = float(df["load_peak_mw"].median())
    return np.full(len(df), float(default_mw))


def panel_window(panel: pd.DataFrame, start: str | pd.Timestamp, horizon_days: int) -> pd.DataFrame:
    """Return horizon_days consecutive rows starting at the first row with date >= start (a copy)."""
    idx = int(np.searchsorted(panel["date"].to_numpy(), np.datetime64(pd.Timestamp(start)), side="left"))
    out = panel.iloc[idx : idx + horizon_days]
    if len(out) < horizon_days:
        raise PanelError(f"panel has only {len(out)} rows from {start}, need {horizon_days}")
    return out.reset_index(drop=True).copy()
