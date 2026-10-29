"""What Claude must know about the book to design scenarios: position table, plausibility ceilings, shock sensitivities.

Plan section 5 says Claude sees the book table, the channel sensitivities and per-factor history. Without them a model
proposes price and gas rises that make the book GAIN (P1 and P4 are long), so these blocks are generated from the fitted
book parameters and the fitted risk model, never typed by hand. Pure functions; no network.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from revstress import config
from revstress.book import BookParams, active_positions
from revstress.market import Market, get_market
from revstress.risk import RiskModel
from revstress.risk.factors import compute_factors

# Standard shock steps for the sensitivity table (one key moved at a time, duration SENSITIVITY_DAYS days).
SENSITIVITY_DAYS: int = 5
SENSITIVITY_STEPS: dict[str, dict[str, float]] = {
    "gas_hh_pct": {"gas_hh_pct": 25.0},
    "load_peak_ratio": {"load_peak_ratio": 1.05},
    "ref_onpeak_pct": {"wh_onpeak_pct": 25.0},
    "pocket_minus_ref_usd": {"dom_minus_wh_usd": 50.0},
    "dart_pct": {"dart_pct": 25.0},
    "spike_day_1500": {"spike_days": 1.0, "spike_daily_avg_usd": 1500.0},
}
NEUTRAL_SHOCK: dict[str, float] = {
    "gas_hh_pct": 0.0, "load_peak_ratio": 1.0, "dc_load_shock_mw": 0.0, "wh_onpeak_pct": 0.0, "dom_minus_wh_usd": 0.0,
    "dart_pct": 0.0, "spike_days": 0.0, "spike_daily_avg_usd": 0.0, "duration_days": float(SENSITIVITY_DAYS),
}
# Agent-facing names of the keys that differ between agent and engine vocabularies (rules.SHOCK_MAPPING_LINE).
AGENT_KEY = {"wh_onpeak_pct": "ref_onpeak_pct", "dom_minus_wh_usd": "pocket_minus_ref_usd", "dc_load_shock_mw": "large_load_shock_mw"}


def book_table(params: BookParams, market: Market | None = None, fallback: bool | None = None) -> list[dict[str, Any]]:
    """One row per active position: size, terms, channel and plain statements of when it gains and loses.

    Formulas follow book.pnl; sizes and strikes come from params so they stay consistent with the engine.
    """
    m = market or get_market()
    ref, pocket = m.reference_zone, m.pocket_zone
    on, day = config.ON_PEAK_HOURS, config.DAY_HOURS
    sz = params.sizes_mw
    rows = {
        "P1": dict(
            what=(f"{'Long' if sz['P1'] >= 0 else 'SHORT'} {abs(sz['P1']):g} MW swap on the {ref} on-peak price, strike K1 = {params.k1_usd:.2f} $/MWh, "
                  f"{on} h per on-peak weekday"),
            gains_when=f"the {ref} on-peak price is {'above' if sz['P1'] >= 0 else 'below'} K1",
            loses_when=f"the {ref} on-peak price is {'below' if sz['P1'] >= 0 else 'above'} K1"),
        "P2": dict(
            what=f"Long {sz['P2']:g} MW of the {pocket} minus {ref} price spread around the clock ({day} h), strike c0 = {params.c0_usd:.2f} $/MWh",
            gains_when=f"the {pocket} minus {ref} spread widens above c0", loses_when=f"the {pocket} minus {ref} spread narrows below c0"),
        "P3": dict(
            what=f"Receives (day-ahead minus real-time) at {ref} off-peak on {sz['P3']:g} MW (8 h, {day} h on weekends and holidays)",
            gains_when="real-time clears below day-ahead", loses_when="real-time clears above day-ahead (real-time spikes)"),
        "P4": dict(
            what=(f"Long heat-rate call on {sz['P4']:g} MW, on-peak: pays max({ref} on-peak - {params.heat_rate:g} x gas - {params.vom_usd:g}, 0) "
                  f"minus a premium of {params.p4_premium_usd:.2f} $/MWh (fair value on the fit sample)"),
            gains_when=f"the {ref} on-peak price rises relative to gas",
            loses_when=("scenario losses are measured against the unshocked path (the premium cancels), so P4 loses only when its payoff "
                        "falls BELOW the unshocked payoff, i.e. when gas rises more than power; it can never lose more than that base payoff")),
        "P5": dict(
            what=(f"Retail load obligation: short {sz['P5']:g} MW x (load / normal load) in {pocket} at fixed price R = {params.r_usd:.2f}, "
                  f"hedged by a long {ref} position at H = {params.h_usd:.2f}, {day} h; P&L = (R - {pocket} price) + ({ref} price - H), times load"),
            gains_when=f"the {pocket} minus {ref} spread narrows", loses_when=f"the {pocket} minus {ref} spread widens; the loss also grows with load above normal"),
        "P6": dict(
            what=(f"Short call on {sz['P6']:g} MW of the {ref} on-peak daily average, strike K6 = {params.k6_usd:.2f} $/MWh, "
                  f"premium received {params.p6_premium_usd:.2f} $/MWh (fair value on the fit sample)"),
            gains_when=f"the {ref} on-peak daily average stays below K6", loses_when=f"the {ref} on-peak daily average exceeds K6 (price spikes)"),
    }
    channels = config.POSITION_CHANNEL
    return [{"position": p, "channel": channels[p], **rows[p]} for p in active_positions(fallback)]


def shock_glossary(market: Market | None = None) -> dict[str, str]:
    """Unit and meaning of every shock key and of stated_loss_usd, in the agent's vocabulary (see shock.apply_shock)."""
    m = market or get_market()
    ref, pocket = m.reference_zone, m.pocket_zone
    return {
        "gas_hh_pct": "Percent change of the Henry Hub gas price on the shocked days (60 means +60%). Must be greater than -100.",
        "ny_gas_basis_usd": "$/MMBtu added to the gas price used by the heat-rate call P4 only (a higher gas cost lowers P4's payoff); it does not move power prices.",
        "load_peak_ratio": ("Multiplier of the daily peak load relative to a typical day of the season (1.10 means 10% higher). Must be greater than 0. "
                            "SIGN RULES checked by the hard rule sign_consistent: cold_snap and heat_wave need a value of at least 1.0; "
                            "for large_load_shortfall keep it at 1.0 or below (a load shortfall is less load, not more)."),
        "large_load_shock_mw": ("MW added to the daily peak load because large new loads arrive faster (+) or slower (-) than forecast; not weather. "
                                "SIGN RULE checked by the hard rule sign_consistent: for driver_class large_load_shortfall the value MUST be zero or "
                                "NEGATIVE (a shortfall means the new loads arrive slower, for example -500); a positive value is rejected. "
                                "Use a positive value only for demand_shock_datacenter-type scenarios."),
        "ref_onpeak_pct": f"Percent move of the {ref} on-peak price ON TOP of what the gas and load shocks already imply (60 means a further +60%). Must be greater than -100.",
        "pocket_minus_ref_usd": f"$/MWh ADDED to the {pocket} minus {ref} price spread on the shocked days (positive widens it).",
        "dart_pct": ("Percent by which real-time prices differ from day-ahead on the shocked days: +40 means real-time clears 40% ABOVE day-ahead, "
                     "-30 means 30% below. It is a percentage, not the dollar gap, and must be strictly greater than -100 (so never -100 or lower)."),
        "spike_days": "Number of shocked days on which the on-peak daily average is at least spike_daily_avg_usd; must not exceed duration_days.",
        "spike_daily_avg_usd": f"{ref} on-peak daily average price on spike days, $/MWh; must not exceed the scenario price cap.",
        "duration_days": "Number of consecutive days the shocks apply, at most the horizon.",
        "stated_loss_usd": "Your own estimate of the book's total loss over the scenario in USD, as a positive number when the book loses money.",
    }


def book_summary(market: Market | None = None) -> str:
    """One paragraph that states which scenarios help and which hurt the book, in the market's zone names."""
    m = market or get_market()
    ref, pocket = m.reference_zone, m.pocket_zone
    return (
        f"P1 (when its size is positive) and P4 are LONG {ref} power, so higher {ref} prices make them GAIN (a negative P1 size is a SHORT swap that loses "
        f"when {ref} rises); higher gas lowers P4. The book loses mainly through: "
        f"a widening {pocket} minus {ref} spread and high load (P5), real-time prices above day-ahead (P3), and {ref} on-peak spikes "
        f"above K6 (P6). A scenario that only raises prices and gas makes the book gain, not lose; a loss needs the adverse channels to "
        f"outweigh the gains of P1, P4 and P2."
    )


def factor_ceilings(model: RiskModel, fit_panel: pd.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    """Per season and shock key: the largest move seen in history and the move beyond which the plausibility score says 'implausible'.

    Moves are measured from the season's typical (median) day: gas and load and dart in percent or ratio, spread in $/MWh,
    the on-peak level residual in percent (the part of the price move NOT explained by the gas and load pass-through).
    """
    fac = compute_factors(fit_panel, model.price_model)
    out: dict[str, dict[str, dict[str, float]]] = {}
    for season, lim in model.limits.items():
        sub = fac[fac["season"] == season]
        if sub.empty:
            continue
        med = {f: float(sub[f].median()) for f in ("g", "l", "s", "c", "d")}
        hmin = {f: float(sub[f].min()) for f in med}
        hmax = {f: float(sub[f].max()) for f in med}

        def pct(f: str, v: float) -> float:
            return round(100.0 * (float(np.exp(v - med[f])) - 1.0), 1)

        def ratio(f: str, v: float) -> float:
            return round(float(np.exp(v - med[f])), 3)

        def usd(f: str, v: float) -> float:
            return round(v - med[f], 1)

        out[season] = {
            "gas_hh_pct": {"hist_min": pct("g", hmin["g"]), "hist_max": pct("g", hmax["g"]),
                           "implausible_below": pct("g", lim["g"][0]), "implausible_above": pct("g", lim["g"][1])},
            "load_peak_ratio": {"hist_min": ratio("l", hmin["l"]), "hist_max": ratio("l", hmax["l"]),
                                "implausible_below": ratio("l", lim["l"][0]), "implausible_above": ratio("l", lim["l"][1])},
            "ref_onpeak_pct": {"hist_min": pct("s", hmin["s"]), "hist_max": pct("s", hmax["s"]),
                               "implausible_below": pct("s", lim["s"][0]), "implausible_above": pct("s", lim["s"][1])},
            "pocket_minus_ref_usd": {"hist_min": usd("c", hmin["c"]), "hist_max": usd("c", hmax["c"]),
                                     "implausible_below": usd("c", lim["c"][0]), "implausible_above": usd("c", lim["c"][1])},
            "dart_pct": {"hist_min": pct("d", hmin["d"]), "hist_max": pct("d", hmax["d"]),
                         "implausible_below": pct("d", lim["d"][0]), "implausible_above": pct("d", lim["d"][1])},
        }
    return out


def price_extremes(fit_panel: pd.DataFrame, market: Market | None = None) -> dict[str, float]:
    """Highest observed daily on-peak averages in the fit panel ($/MWh) and the scenario cap, for spike inputs."""
    m = market or get_market()
    on = fit_panel[fit_panel["wh_on"].notna()]
    return {
        "max_daily_onpeak_ref_usd": round(float(on["wh_on"].max()), 1),
        "max_daily_onpeak_pocket_usd": round(float(on["dom_on"].max()), 1),
        "scenario_price_cap_usd": float(m.energy_cap_usd),  # NYISO: a stated assumption (Market.cap_note)
    }


def shock_sensitivities(
    pnl_fn: Callable[[Mapping[str, float], str], Mapping[str, float]],
    season: str,
    market: Market | None = None,
    fallback: bool | None = None,
) -> dict[str, Any]:
    """P&L by position (USD) of one standard shock step lasting SENSITIVITY_DAYS days, one key at a time.

    pnl_fn(shock, season) must return the shock-attributable P&L by position over the scenario (positive = gain).
    Use a separate engine instance for this so the equal-budget engine-call count of the arms is not changed.
    """
    positions = active_positions(fallback)
    table: dict[str, dict[str, float]] = {}
    for name, step in SENSITIVITY_STEPS.items():
        shock = {**NEUTRAL_SHOCK, **step}
        pnl = pnl_fn(shock, season)
        table[name] = {p: round(float(pnl.get(p, 0.0))) for p in positions}
        table[name]["total"] = round(sum(table[name].values()))
    steps = {name: {AGENT_KEY.get(k, k): v for k, v in step.items()} for name, step in SENSITIVITY_STEPS.items()}
    return {"season": season, "duration_days": SENSITIVITY_DAYS, "steps": steps, "pnl_usd_by_position": table,
            "note": "positive = the book gains; one key moved at a time from a neutral scenario; effects are not additive in general"}


def enrich_context(
    ctx: dict[str, Any],
    params: BookParams,
    model: RiskModel,
    fit_panel: pd.DataFrame,
    market: Market | None = None,
    fallback: bool | None = None,
    pnl_fn: Callable[[Mapping[str, float], str], Mapping[str, float]] | None = None,
    seasons: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Copy of ctx with the book table, summary, ceilings, price extremes and (if pnl_fn is given) sensitivities added."""
    m = market or get_market()
    out = dict(ctx)
    out["book"] = book_table(params, m, fallback)
    out["book_summary"] = book_summary(m)
    out["shock_glossary"] = shock_glossary(m)
    out["shock_ceilings_by_season"] = factor_ceilings(model, fit_panel)
    out["price_extremes_usd_mwh"] = price_extremes(fit_panel, m)
    if pnl_fn is not None and seasons:
        out["shock_sensitivities"] = {s: shock_sensitivities(pnl_fn, s, m, fallback) for s in seasons}
    return out
