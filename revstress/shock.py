"""Map a plan-section-5 shock vector onto a daily scenario path.

Units: *_pct are percent (60 = +60%); load_peak_ratio is a multiplier; dc_load_shock_mw is MW added
to daily peak load; dom_minus_wh_usd is $/MWh added to the DOM-WH spread; spike_daily_avg_usd is the
WH on-peak daily average on spike days, $/MWh; duration_days counts days from the start of the slice.

Mapping on shocked days (the first duration_days rows):
  gas:   hh_usd *= 1 + gas_hh_pct/100
  load:  load_peak_mw = load*load_peak_ratio + dc_load_shock_mw
  level: WH DA and RT prices *= exp(gas_beta*dlog(gas) + b1*dl + b2*d(l^2)) * (1 + wh_onpeak_pct/100),
         with l = log(load/load_normal). Off-peak gets the load and pct terms scaled by offpeak_scale.
         The pass-through coefficients in PassThrough are PLACEHOLDERS until the price regression exists.
  dart:  RT (on and off) *= 1 + dart_pct/100 relative to DA
  spike: spike_days days drawn at random (seeded) among shocked days; RT on-peak = max(RT on-peak, spike avg)
  ny_gas_basis_usd (optional, $/MMBtu): added to hh_usd on shocked days (gas leg of P4 only; not passed into the
         reference-zone price, which is the least gas-exposed zone, plan section 3)
  basis: DOM = shocked WH + base DOM-WH spread + dom_minus_wh_usd (on and off)
  weather: if a DegreeDaySlopes is given, hdd/cdd on shocked days move so that the weather-driven load change
         log(load_peak_ratio) is explained by the fitted load-vs-degree-day slopes: d(hdd or cdd) = log(ratio) /
         slope, using hdd on days with hdd >= cdd and cdd otherwise, floored at 0. The T factor of the path then
         responds to the scenario (dc_load_shock_mw is not weather and does not move T). Without it hdd/cdd are
         unchanged (base-window weather).
Clipping: the WH series (treated as the energy component; WH congestion and losses are not separated
in daily data) are capped at config.energy_cap_usd() (PJM 3,700; NYISO 5,000 scenario cap, a stated assumption). DOM may exceed the cap through the spread.
LIMITATION: the model works on daily averages, so it understates hourly spikes (a few hours at the cap
move a daily average far less than they move P6/P3 payoffs would on an hourly basis).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from . import config
from .panel import resolve_load_normal

SCENARIO_EXTRA_COLUMNS: tuple[str, ...] = ("load_normal_mw", "shock_day", "spike_day", "energy_clipped")


@dataclass(frozen=True)
class PassThrough:
    """Placeholder log-price pass-through; replace with fitted b1, b2, b3 (plan section 4)."""

    gas_beta: float = 0.6  # dlog(WH) per dlog(gas)
    load_beta1: float = 2.0  # per unit of l
    load_beta2: float = 6.0  # per unit of l^2
    offpeak_scale: float = 0.5  # off-peak sensitivity relative to on-peak for load and wh_onpeak_pct
    l_normal_mw: float | None = None  # None: use 'load_normal_mw' column, else median of the slice
    phi_level: float = 0.0  # daily persistence of the price-level shock after it ends (AR(1) of s); 0 = snap back
    phi_spread: float = 0.0  # same for the N.Y.C.-WEST spread shock (AR(1) of c)


@dataclass(frozen=True)
class DegreeDaySlopes:
    """Fitted change in log daily peak load per degree day: slopes of l on hdd and cdd (1/degF-day, >= 0)."""

    hdd: float
    cdd: float


def fit_degree_day_slopes(panel: pd.DataFrame) -> DegreeDaySlopes:
    """OLS of log(load / month-of-year mean load) on [1, hdd, cdd]; slopes floored at 0. Needs load_peak_mw, hdd, cdd."""
    load = panel["load_peak_mw"].to_numpy(dtype=float)
    month_mean = panel.groupby(pd.DatetimeIndex(panel["date"]).month)["load_peak_mw"].transform("mean").to_numpy(dtype=float)
    y = np.log(load / month_mean)
    X = np.column_stack([np.ones(len(panel)), panel["hdd"].to_numpy(dtype=float), panel["cdd"].to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return DegreeDaySlopes(hdd=max(float(beta[1]), 0.0), cdd=max(float(beta[2]), 0.0))


def validate_shock(shock: Mapping[str, float], horizon_days: int) -> dict[str, float]:
    """Fill missing keys with neutral values and check ranges; return the full shock dict.

    Raises ValueError on unknown keys, duration_days > horizon_days, spike_days > duration_days,
    load_peak_ratio <= 0, gas_hh_pct/wh_onpeak_pct/dart_pct <= -100, or negative counts/levels.
    """
    unknown = set(shock) - set(config.SHOCK_KEYS) - set(config.OPTIONAL_SHOCK_KEYS)
    if unknown:
        raise ValueError(f"unknown shock keys: {sorted(unknown)}")
    s = {**config.NEUTRAL_SHOCK, **shock}
    if not (0 <= s["duration_days"] <= horizon_days):
        raise ValueError("duration_days must be in [0, horizon_days]")
    if not (0 <= s["spike_days"] <= s["duration_days"]):
        raise ValueError("spike_days must be in [0, duration_days]")
    if s["spike_daily_avg_usd"] < 0:
        raise ValueError("spike_daily_avg_usd must be >= 0")
    if s["load_peak_ratio"] <= 0:
        raise ValueError("load_peak_ratio must be > 0")
    for k in ("gas_hh_pct", "wh_onpeak_pct", "dart_pct"):
        if s[k] <= -100:
            raise ValueError(f"{k} must be > -100")
    return s


def apply_shock(
    base_panel_slice: pd.DataFrame,
    shock: Mapping[str, float],
    rng_seed: int,
    passthrough: PassThrough | None = None,
    weather: DegreeDaySlopes | None = None,
) -> pd.DataFrame:
    """Return the scenario path for a horizon (one row per day of base_panel_slice).

    base_panel_slice must have all panel.PANEL_COLUMNS (row order = horizon days). Output has the same
    columns (prices $/MWh, load MW, gas $/MMBtu) plus load_normal_mw (MW), shock_day, spike_day and
    energy_clipped (bool). Input is not modified. Spike-day placement depends only on rng_seed.
    """
    pt = PassThrough() if passthrough is None else passthrough
    n = len(base_panel_slice)
    s = validate_shock(shock, n)
    dur, n_spike = int(s["duration_days"]), int(s["spike_days"])
    out = base_panel_slice.copy().reset_index(drop=True)

    mask = np.zeros(n, dtype=bool)
    mask[:dur] = True
    spike = np.zeros(n, dtype=bool)
    if n_spike > 0:
        rng = np.random.default_rng(rng_seed)
        spike[rng.choice(np.flatnonzero(mask), size=n_spike, replace=False)] = True

    normal = resolve_load_normal(out, pt.l_normal_mw)
    load0 = out["load_peak_mw"].to_numpy(dtype=float)
    load1 = np.where(mask, load0 * s["load_peak_ratio"] + s["dc_load_shock_mw"], load0)
    if (load1 <= 0).any():
        raise ValueError("shocked load must stay positive")
    l0, l1 = np.log(load0 / normal), np.log(load1 / normal)
    if weather is not None:
        use_hdd = out["hdd"].to_numpy(dtype=float) >= out["cdd"].to_numpy(dtype=float)
        slope = np.where(use_hdd, weather.hdd, weather.cdd)
        d_dd = np.where(mask & (slope > 1e-12), np.log(s["load_peak_ratio"]) / np.maximum(slope, 1e-12), 0.0)
        out["hdd"] = np.maximum(out["hdd"].to_numpy(dtype=float) + np.where(use_hdd, d_dd, 0.0), 0.0)
        out["cdd"] = np.maximum(out["cdd"].to_numpy(dtype=float) + np.where(use_hdd, 0.0, d_dd), 0.0)

    d_gas = np.log1p(s["gas_hh_pct"] / 100.0)
    load_term = pt.load_beta1 * (l1 - l0) + pt.load_beta2 * (l1**2 - l0**2)
    pct = 1.0 + s["wh_onpeak_pct"] / 100.0
    f_on = np.where(mask, np.exp(pt.gas_beta * d_gas + load_term) * pct, 1.0)
    f_off = np.where(
        mask,
        np.exp(pt.gas_beta * d_gas + pt.offpeak_scale * load_term) * (1.0 + pt.offpeak_scale * s["wh_onpeak_pct"] / 100.0),
        1.0,
    )
    dart = np.where(mask, 1.0 + s["dart_pct"] / 100.0, 1.0)
    # Persistence tail: after the shocked days the price-level and spread effects decay geometrically (phi^k) instead of vanishing.
    k_after = np.arange(n) - (dur - 1)
    tail = (k_after >= 1) & (dur >= 1)
    if tail.any() and (pt.phi_level > 0 or pt.phi_spread > 0):
        lvl = pt.phi_level ** np.where(tail, k_after, 0)
        f_on = np.where(tail, np.exp(np.log(f_on[dur - 1]) * lvl), f_on)
        f_off = np.where(tail, np.exp(np.log(f_off[dur - 1]) * lvl), f_off)
        spread_decay = np.where(tail, pt.phi_spread ** np.where(tail, k_after, 0), 0.0)
    else:
        spread_decay = np.zeros(n)

    col = lambda name: out[name].to_numpy(dtype=float)
    spread_on, spread_off = col("dom_on") - col("wh_on"), col("dom_off") - col("wh_off")
    da_on, da_off = col("da_wh_on") * f_on, col("da_wh_off") * f_off
    rt_on, rt_off = col("rt_wh_on") * f_on * dart, col("rt_wh_off") * f_off * dart
    rt_on = np.where(spike, np.maximum(rt_on, s["spike_daily_avg_usd"]), rt_on)

    cap = config.energy_cap_usd()
    clipped = (da_on > cap) | (da_off > cap) | (rt_on > cap) | (rt_off > cap)
    da_on, da_off, rt_on, rt_off = (np.minimum(x, cap) for x in (da_on, da_off, rt_on, rt_off))

    dom_shift = np.where(mask, s["dom_minus_wh_usd"], spread_decay * s["dom_minus_wh_usd"])
    out["da_wh_on"], out["da_wh_off"], out["rt_wh_on"], out["rt_wh_off"] = da_on, da_off, rt_on, rt_off
    out["wh_on"], out["wh_off"] = rt_on, rt_off
    out["dom_on"], out["dom_off"] = rt_on + spread_on + dom_shift, rt_off + spread_off + dom_shift
    basis = float(s.get("ny_gas_basis_usd", 0.0))
    out["hh_usd"] = np.where(mask, col("hh_usd") * (1.0 + s["gas_hh_pct"] / 100.0) + basis, col("hh_usd"))
    out["load_peak_mw"] = load1
    out["load_normal_mw"] = normal
    out["shock_day"], out["spike_day"], out["energy_clipped"] = mask, spike, clipped
    return out
