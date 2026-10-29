"""Historical replay (plan section 8A): realized event factors -> shock -> P&L versus P&L on actual prices.

The shock summarises the event window with window averages, so the engine path is a smoothed version
of the realized path. The gap by position is therefore the daily-averaging gap (plus the placeholder
pass-through error). Expected: P6 and P3 understated (convex or short-lived payoffs lose most).
Works on any panel; label results with the market and data range (synthetic panels stay SYNTHETIC).
The base window takes the event's on-peak calendar, so weekend/holiday hours match the actual side.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config
from ..book import BookParams, pnl, pnl_totals
from ..panel import onpeak_day_flags, resolve_load_normal
from ..shock import PassThrough, apply_shock

COLD_SNAP_SIGNS: dict[str, int] = {"P1": 1, "P4": 1, "P3": -1, "P5": -1, "P6": -1}  # expected sign of actual P&L
WITHIN_REL = 0.30


@dataclass(frozen=True)
class ReplayResult:
    """Replay of one event. table is indexed by position/channel/total (USD over the window)."""

    shock: dict[str, float]
    table: pd.DataFrame
    engine_path: pd.DataFrame
    actual_pnl: pd.DataFrame


def _wh24(df: pd.DataFrame) -> pd.Series:
    """24h average of wh_on/wh_off, $/MWh; weekend and holiday days use off-peak only (as book.pnl does)."""
    on = config.ON_PEAK_HOURS * onpeak_day_flags(df)
    return pd.Series((on * df["wh_on"].to_numpy(dtype=float) + (config.DAY_HOURS - on) * df["wh_off"].to_numpy(dtype=float)) / config.DAY_HOURS)


def event_to_shock(
    event: pd.DataFrame,
    base: pd.DataFrame,
    passthrough: PassThrough | None = None,
    spike_threshold_usd: float = 250.0,
) -> dict[str, float]:
    """Realized daily factor vector of an event window as a shock dict.

    event and base are panel slices of equal length (base = normal-conditions window used as the
    unshocked path). Units follow the shock schema. Spike days are event days with wh_on above
    spike_threshold_usd ($/MWh); the level residual wh_onpeak_pct is what remains of the non-spike
    on-peak WH change after the gas and load pass-through and after the RT/DA factor (apply_shock multiplies RT
    on-peak by 1 + dart_pct too, so the residual divides it out; without this the level is double counted).
    """
    if len(event) != len(base):
        raise ValueError("event and base windows must have equal length")
    pt = PassThrough() if passthrough is None else passthrough
    n = len(event)
    spike = event["wh_on"].to_numpy(dtype=float) > spike_threshold_usd
    gas_ratio = event["hh_usd"].mean() / base["hh_usd"].mean()
    normal = float(np.median(resolve_load_normal(base, pt.l_normal_mw)))
    load_ratio = event["load_peak_mw"].mean() / base["load_peak_mw"].mean()
    l0, l1 = np.log(base["load_peak_mw"].mean() / normal), np.log(event["load_peak_mw"].mean() / normal)
    passed = pt.gas_beta * np.log(gas_ratio) + pt.load_beta1 * (l1 - l0) + pt.load_beta2 * (l1**2 - l0**2)
    ev_level = event.loc[~spike, "wh_on"].mean() if (~spike).any() else event["wh_on"].mean()
    total_log = np.log(ev_level / base["wh_on"].mean())
    spread = (_wh24(event.assign(wh_on=event["dom_on"], wh_off=event["dom_off"])) - _wh24(event)).mean()
    spread0 = (_wh24(base.assign(wh_on=base["dom_on"], wh_off=base["dom_off"])) - _wh24(base)).mean()
    dart_ev = event["rt_wh_off"].mean() / event["da_wh_off"].mean()
    dart_b = base["rt_wh_off"].mean() / base["da_wh_off"].mean()
    return {
        "gas_hh_pct": 100.0 * (gas_ratio - 1.0),
        "load_peak_ratio": float(load_ratio),
        "dc_load_shock_mw": 0.0,
        "wh_onpeak_pct": 100.0 * float(np.expm1(total_log - passed - np.log(dart_ev / dart_b))),
        "dom_minus_wh_usd": float(spread - spread0),
        "dart_pct": 100.0 * float(dart_ev / dart_b - 1.0),
        "spike_days": int(spike.sum()),
        "spike_daily_avg_usd": float(event.loc[spike, "wh_on"].mean()) if spike.any() else 0.0,
        "duration_days": n,
    }


def replay_event(
    event: pd.DataFrame,
    base: pd.DataFrame,
    params: BookParams,
    *,
    rng_seed: int = 0,
    passthrough: PassThrough | None = None,
    spike_threshold_usd: float = 250.0,
    fallback: bool | None = None,
    n_seeds: int = 1,
) -> ReplayResult:
    """Replay one event window.

    Engine side: event_to_shock -> apply_shock on `base` -> book P&L. Actual side: book P&L on the event
    prices. table columns: engine_usd, actual_usd, gap_usd (engine - actual, USD), rel_gap (gap/|actual|,
    NaN if actual is 0), within30 (|rel_gap| <= 30%), sign_match. The gap is the daily-averaging gap.
    Spike days are placed at random by the engine; n_seeds > 1 averages the engine P&L over seeds rng_seed.. (expected value).
    """
    passthrough = PassThrough(l_normal_mw=params.l_normal_mw) if passthrough is None else passthrough
    shock = event_to_shock(event, base, passthrough, spike_threshold_usd)
    base = base.reset_index(drop=True).assign(is_onpeak_day=onpeak_day_flags(event))  # the event's calendar fixes on-peak hours
    path = apply_shock(base, shock, rng_seed, passthrough)
    eng = pnl_totals(pnl(path, params, fallback))
    if n_seeds > 1:
        runs = [eng] + [pnl_totals(pnl(apply_shock(base, shock, rng_seed + k, passthrough), params, fallback)) for k in range(1, n_seeds)]
        eng = sum(runs) / n_seeds
    act_pnl = pnl(event.reset_index(drop=True), params, fallback)
    act = pnl_totals(act_pnl)
    gap = eng - act
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = gap / act.abs().replace(0.0, np.nan)
    table = pd.DataFrame(
        {
            "engine_usd": eng,
            "actual_usd": act,
            "gap_usd": gap,
            "rel_gap": rel,
            "within30": rel.abs() <= WITHIN_REL,
            "sign_match": np.sign(eng) == np.sign(act),
        }
    )
    return ReplayResult(shock=shock, table=table, engine_path=path, actual_pnl=act_pnl)


def cold_snap_sign_check(table: pd.DataFrame, column: str = "actual_usd") -> dict[str, bool]:
    """Plan 8A sign check for a cold snap on the chosen column (USD): P1/P4 >= 0, P3/P5/P6 <= 0 (zero passes)."""
    return {
        p: bool(table.loc[p, column] * s >= 0.0) for p, s in COLD_SNAP_SIGNS.items() if p in table.index
    }


def replay_event_daily(
    event: pd.DataFrame,
    base: pd.DataFrame,
    params: BookParams,
    *,
    passthrough: PassThrough | None = None,
    spike_threshold_usd: float = 250.0,
    fallback: bool | None = None,
) -> pd.Series:
    """Engine P&L (USD, summed over days) when each event day is shocked on its own against the matching base day.

    Removes the cross-day averaging of the window shock, so what remains versus actual is the within-day model error
    (pass-through, off-peak scaling, spread shift). Compare with replay_event: the difference is the window-averaging gap.
    """
    if len(event) != len(base):
        raise ValueError("event and base windows must have equal length")
    total = None
    for i in range(len(event)):
        r = replay_event(event.iloc[[i]].reset_index(drop=True), base.iloc[[i]].reset_index(drop=True), params,
                         passthrough=passthrough, spike_threshold_usd=spike_threshold_usd, fallback=fallback)
        total = r.table["engine_usd"] if total is None else total + r.table["engine_usd"]
    return total
