"""The six-position PJM book (plan section 3) and its daily P&L.

Daily P&L (USD per day) on a day with on-peak hours (weekday, not a NERC holiday): on = 16 h, off = 8 h:
  P1 = 16*50*(wh_on - K)                                  channel system
  P2 = 24*50*((dom24 - wh24) - c0)                        congestion
  P3 = 8*25*(da_wh_off - rt_wh_off)                       dart
  P4 = 16*100*max(wh_on - HR*G - VOM, 0) - premium        gas   (G = hh_usd + seasonal basis)
  P5 = 24*200*(L/Lnorm)*((R - dom24) + (wh24 - H))        zone_volume (DOM hub as zone proxy)
  P6 = -16*25*max(wh_on - K6, 0) + premium                tail
with wh24 = (16*wh_on + 8*wh_off)/24 and dom24 likewise. Option premiums default to 0 (payoff only).
On a weekend or NERC holiday there are 0 on-peak hours: P1, P4, P6 pay 0, wh24 = wh_off, dom24 = dom_off and the
P3 off-peak leg covers 24 h (panel.onpeak_day_flags; a panel column 'is_onpeak_day' overrides the calendar).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import config
from .panel import gas_price_usd, onpeak_day_flags, resolve_load_normal

POSITION_COLUMNS: tuple[str, ...] = config.POSITIONS
CHANNEL_COLUMNS: tuple[str, ...] = config.CHANNELS
PNL_COLUMNS: tuple[str, ...] = ("date",) + POSITION_COLUMNS + CHANNEL_COLUMNS + ("total",)


@dataclass(frozen=True)
class BookParams:
    """Strikes and levels of the book. Prices $/MWh, load MW."""

    k1_usd: float  # P1 swap strike K
    c0_usd: float  # P2 congestion strike, DOM-WH 24h average
    k6_usd: float  # P6 call strike
    r_usd: float  # P5 fixed retail price R
    h_usd: float  # P5 WH hedge price H
    l_normal_mw: float  # P5 normal peak load (used if the path has no 'load_normal_mw' column)
    heat_rate: float = config.HEAT_RATE_MMBTU_PER_MWH
    vom_usd: float = config.VOM_USD_PER_MWH
    p4_premium_usd: float = 0.0  # $/MWh paid on P4 volume (carry excluded by default)
    p6_premium_usd: float = 0.0  # $/MWh received on P6 volume
    sizes_mw: dict[str, float] = field(default_factory=lambda: dict(config.POSITION_SIZES_MW))
    basis_usd: dict[str, float] = field(default_factory=config.gas_basis_by_season)


def fit_book_params(panel: pd.DataFrame) -> BookParams:
    """Set strikes at forward-like levels from a fit sample so that expected P&L is about zero.

    K = mean wh_on and K6 = 99th percentile of wh_on, both over on-peak days; c0 = mean 24h DOM-WH spread; H = mean WH 24h;
    R = mean DOM 24h; l_normal = median load_peak_mw. Needs the full panel columns.
    """
    on_h = config.ON_PEAK_HOURS * onpeak_day_flags(panel)
    off_h = config.DAY_HOURS - on_h
    wh24 = pd.Series((on_h * panel["wh_on"] + off_h * panel["wh_off"]) / config.DAY_HOURS)
    dom24 = pd.Series((on_h * panel["dom_on"] + off_h * panel["dom_off"]) / config.DAY_HOURS)
    flags = onpeak_day_flags(panel)
    wh_on_days = panel.loc[flags, "wh_on"]
    k6 = float(wh_on_days.quantile(config.SPIKE_STRIKE_QUANTILE))
    # Option premiums at fair value on the fit sample (multi-channel rule v2): mean payoff per on-peak MWh, so that P4 and P6
    # have zero expected absolute P&L on the sample. (The scenario engine reports shock-attributable P&L, where a constant cancels.)
    g_on = gas_price_usd(panel.loc[flags], BookParams.__dataclass_fields__["basis_usd"].default_factory())
    p4_prem = float(np.maximum(wh_on_days.to_numpy(dtype=float) - config.HEAT_RATE_MMBTU_PER_MWH * np.asarray(g_on, dtype=float)
                               - config.VOM_USD_PER_MWH, 0.0).mean())
    p6_prem = float(np.maximum(wh_on_days.to_numpy(dtype=float) - k6, 0.0).mean())
    return BookParams(
        k1_usd=float(wh_on_days.mean()),
        c0_usd=float((dom24 - wh24).mean()),
        k6_usd=k6,
        p4_premium_usd=p4_prem,
        p6_premium_usd=p6_prem,
        r_usd=float(dom24.mean()),
        h_usd=float(wh24.mean()),
        l_normal_mw=float(panel["load_peak_mw"].median()),
    )


def active_positions(fallback: bool | None = None) -> tuple[str, ...]:
    """Positions in the book; fallback=None reads config.FALLBACK_BOOK."""
    if fallback is None:
        fallback = config.FALLBACK_BOOK
    return config.FALLBACK_POSITIONS if fallback else config.POSITIONS


def pnl(path_df: pd.DataFrame, params: BookParams, fallback: bool | None = None) -> pd.DataFrame:
    """Per-day P&L in USD by position, channel and total.

    Returns columns: date, P1..P6, system, congestion, dart, gas, zone_volume, tail, total.
    Positions outside the active book are 0.0. Deterministic and vectorised; path_df needs the
    panel columns used by the active positions (fallback: wh_on, hh_usd, date).
    """
    active = active_positions(fallback)
    n = len(path_df)
    day = config.DAY_HOURS
    on = config.ON_PEAK_HOURS * onpeak_day_flags(path_df)  # on-peak hours per day: 16, or 0 on weekends and NERC holidays
    off = day - on
    sz = params.sizes_mw
    wh_on = path_df["wh_on"].to_numpy(dtype=float)
    out = {p: np.zeros(n) for p in POSITION_COLUMNS}

    if "P1" in active:
        out["P1"] = on * sz["P1"] * (wh_on - params.k1_usd)
    if "P4" in active:
        g = gas_price_usd(path_df, params.basis_usd)
        out["P4"] = on * sz["P4"] * (np.maximum(wh_on - params.heat_rate * g - params.vom_usd, 0.0) - params.p4_premium_usd)
    if "P6" in active:
        out["P6"] = -on * sz["P6"] * (np.maximum(wh_on - params.k6_usd, 0.0) - params.p6_premium_usd)

    if {"P2", "P3", "P5"} & set(active):
        wh24 = (on * wh_on + off * path_df["wh_off"].to_numpy(dtype=float)) / day
        dom24 = (on * path_df["dom_on"].to_numpy(dtype=float) + off * path_df["dom_off"].to_numpy(dtype=float)) / day
        if "P2" in active:
            out["P2"] = day * sz["P2"] * ((dom24 - wh24) - params.c0_usd)
        if "P3" in active:
            out["P3"] = off * sz["P3"] * (path_df["da_wh_off"].to_numpy(dtype=float) - path_df["rt_wh_off"].to_numpy(dtype=float))
        if "P5" in active:
            ratio = path_df["load_peak_mw"].to_numpy(dtype=float) / resolve_load_normal(path_df, params.l_normal_mw)
            out["P5"] = day * sz["P5"] * ratio * ((params.r_usd - dom24) + (wh24 - params.h_usd))

    res = pd.DataFrame({"date": path_df["date"].to_numpy()})
    for p in POSITION_COLUMNS:
        res[p] = out[p]
    for ch in CHANNEL_COLUMNS:
        res[ch] = sum(res[p] for p in POSITION_COLUMNS if config.POSITION_CHANNEL[p] == ch)
    res["total"] = res[list(POSITION_COLUMNS)].sum(axis=1)
    return res[list(PNL_COLUMNS)]


def pnl_totals(pnl_df: pd.DataFrame) -> pd.Series:
    """Sum over days (USD) of every position, channel and total column."""
    return pnl_df.drop(columns="date").sum()


def scenario_loss_usd(pnl_df: pd.DataFrame) -> float:
    """Loss in USD (positive = loss) = minus the total P&L over the path."""
    return float(-pnl_df["total"].sum())


def is_breach(pnl_df: pd.DataFrame, target_usd: float = config.LOSS_TARGET_USD) -> bool:
    """True if the path loses at least target_usd."""
    return scenario_loss_usd(pnl_df) >= target_usd


def with_strikes(params: BookParams, **changes: float) -> BookParams:
    """Copy of params with some fields replaced."""
    return replace(params, **changes)
