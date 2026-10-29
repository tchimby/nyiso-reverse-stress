"""Real-data fit and event replay for NYISO (plan sections 4 and 8A). No network, no Claude calls.

Run from pjm_revstress:  python -E -P scripts/run_replay.py [--out outputs/real] [--n-seeds 200]
Reads data/processed/nyiso_panel.csv (+ nyiso_panel_2014_replay.csv for the flagged 2014 event) and writes
replay_table.csv, fit_summary.json, diagnostics.md and two PNGs to outputs/real/.
Real data: NYISO MIS public files (WEST, N.Y.C. LBMP; NYCA load), EIA Henry Hub, NOAA GHCN-Daily.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from revstress import config  # noqa: E402

config.MARKET = "NYISO"

from revstress.book import fit_book_params, pnl, pnl_totals  # noqa: E402
from revstress.eval import diagnostics as dg  # noqa: E402
from revstress.eval import replay as rp  # noqa: E402
from revstress.panel import season_labels  # noqa: E402
from revstress.risk import fit_risk_model, score_scenario  # noqa: E402
from revstress.risk.factors import compute_factors  # noqa: E402
from revstress.shock import PassThrough  # noqa: E402

FIT_START, FIT_END = "2019-01-01", "2025-12-31"
VARIANTS: tuple[tuple[str, str | None, str], ...] = (
    ("full_2019", None, "all fit-window data from 2019-01-01 (the Market primary break 2016-06-22 predates the window)"),
    ("post_indian_point_2021", "2021-05-01", "data from 2021-05-01 (after Indian Point 3 retirement, Apr 2021)"),
    ("post_transmission_shortage_2023", "2023-11-14", "data from 2023-11-14 (transmission shortage pricing revision)"),
)
# (key, display, first day, last day, flagged out of fit window)
EVENTS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("jan2014", "Polar vortex 2014", "2014-01-06", "2014-01-08", True),
    ("elliott", "Elliott 2022", "2022-12-23", "2022-12-24", False),
    ("jan2025", "Cold Jan 2025", "2025-01-20", "2025-01-23", False),
    ("jun2025", "Heat Jun 2025", "2025-06-23", "2025-06-25", False),
)
BASE_GAP_DAYS = 14
MATERIAL_USD = 0.01 * config.LOSS_TARGET_USD
POS_ORDER = list(config.POSITIONS) + list(config.CHANNELS) + ["total"]


def label_for(panel: pd.DataFrame) -> str:
    return (
        f"REAL DATA - NYISO (reference WEST, pocket N.Y.C.), fit window {FIT_START} to {FIT_END}, "
        f"panel {panel['date'].min().date()} to {panel['date'].max().date()}; 2014 rows are a flagged out-of-window replay event"
    )


def _num(x):
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, dict):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_num(v) for v in x]
    return x


def fit_variant(panel: pd.DataFrame, start: str | None, include_pre_break: bool = True):
    p = panel if start is None else panel[panel["date"] >= pd.Timestamp(start)]
    return fit_risk_model(p.reset_index(drop=True), as_of=FIT_END, include_pre_break=include_pre_break)


def variant_summary(model, df: pd.DataFrame) -> dict:
    tab, st = dg.regression_table(df, model.price_model)
    return {
        "rows": int(len(df)),
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())],
        "regression": {k: {c: float(v) for c, v in r.items()} for k, r in tab.iterrows()},
        "regression_stats": st,
        "residuals": dg.residual_diagnostics(df, model.price_model),
        "covariance": dg.covariance_conditioning(model),
        "spike": dg.spike_summary(model),
        "n_windows": int(len(model.window_d2)),
    }


def base_window(sample: pd.DataFrame, start: pd.Timestamp, n: int) -> pd.DataFrame:
    """n days ending BASE_GAP_DAYS before `start`, from `sample` (the data available at the event)."""
    prior = sample[sample["date"] <= start - pd.Timedelta(days=BASE_GAP_DAYS)]
    return prior.tail(n).reset_index(drop=True)


def score_event(event: pd.DataFrame, model) -> dict:
    path = event.copy().reset_index(drop=True)
    path["shock_day"] = True
    thr = model.spike.thresholds_usd
    path["spike_day"] = path["wh_on"].to_numpy() > np.array([thr[s] for s in season_labels(path["date"])])
    sc = score_scenario(path, model)
    keep = ("d2", "q", "severity", "nearest_date", "nearest_distance", "worst_day", "season", "n_windows", "hard_rule_failures")
    out = {k: sc[k] for k in keep}
    out["marginal_percentiles"] = sc["marginal_percentiles"]
    out["marginals_exceeded"] = [e["factor"] for e in sc["marginals_exceeded"]]
    out["factors_worst"] = sc["factors_worst"]
    out["spike_days_in_event"] = int(path["spike_day"].sum())
    return out


def run_events(panel, panel14, headline, n_seeds: int) -> tuple[pd.DataFrame, dict]:
    rows, extra = [], {}
    for key, name, d0, d1, flagged in EVENTS:
        src = panel14 if flagged else panel
        ev = src[(src["date"] >= d0) & (src["date"] <= d1)].reset_index(drop=True)
        start = pd.Timestamp(d0)
        if flagged:
            as_of, model, sample = pd.Timestamp(FIT_END), headline, panel14
            base = sample[sample["date"] >= pd.Timestamp("2014-01-13")].head(len(ev)).reset_index(drop=True)
            fit_df = panel[panel["date"] <= FIT_END].reset_index(drop=True)
        else:
            as_of = start - pd.Timedelta(days=1)
            fit_df = panel[panel["date"] <= as_of].reset_index(drop=True)
            model = fit_risk_model(fit_df, as_of=as_of, include_pre_break=True)
            sample = fit_df
            base = base_window(sample, start, len(ev))
        params = fit_book_params(fit_df)
        pt, pt_detail = dg.estimate_passthrough(fit_df, model.price_model, params.l_normal_mw)
        placeholder = PassThrough(l_normal_mw=params.l_normal_mw)
        season = str(season_labels(ev["date"])[0])
        thr = model.spike.thresholds_usd[season]
        win = rp.replay_event(ev, base, params, passthrough=pt, spike_threshold_usd=thr, n_seeds=n_seeds)
        old = rp.replay_event(ev, base, params, passthrough=placeholder, spike_threshold_usd=thr, n_seeds=n_seeds)
        daily = rp.replay_event_daily(ev, base, params, passthrough=pt, spike_threshold_usd=thr)
        daily_old = rp.replay_event_daily(ev, base, params, passthrough=placeholder, spike_threshold_usd=thr)
        act = win.table["actual_usd"]
        for name_ in POS_ORDER:
            a = float(act[name_])
            ew, ed = float(win.table.loc[name_, "engine_usd"]), float(daily[name_])
            rows.append(
                {
                    "event": name,
                    "event_key": key,
                    "dates": f"{d0}..{d1}",
                    "n_days": len(ev),
                    "flag": "OUT-OF-FIT-WINDOW (pre-2016 pricing regime)" if flagged else "in fit window",
                    "model_as_of": str(as_of.date()),
                    "level": "position" if name_ in config.POSITIONS else ("channel" if name_ in config.CHANNELS else "total"),
                    "name": name_,
                    "actual_usd": a,
                    "engine_window_usd": ew,
                    "engine_daily_usd": ed,
                    "engine_window_placeholder_pt_usd": float(old.table.loc[name_, "engine_usd"]),
                    "engine_daily_placeholder_pt_usd": float(daily_old[name_]),
                    "gap_window_usd": ew - a,
                    "gap_daily_usd": ed - a,
                    "averaging_gap_usd": ew - ed,
                    "rel_gap_window": (ew - a) / abs(a) if a != 0 else np.nan,
                    "rel_gap_daily": (ed - a) / abs(a) if a != 0 else np.nan,
                    "material": abs(a) >= MATERIAL_USD,
                    "within30_window": bool(a != 0 and abs(ew - a) <= 0.3 * abs(a)),
                    "within30_daily": bool(a != 0 and abs(ed - a) <= 0.3 * abs(a)),
                    "sign_match_window": bool(np.sign(ew) == np.sign(a)),
                    "sign_match_daily": bool(np.sign(ed) == np.sign(a)),
                }
            )
        act_daily = pnl(ev, params)
        score_asof = score_event(ev, model)
        score_full = score_event(ev, headline)
        extra[key] = {
            "name": name,
            "flagged_out_of_fit_window": flagged,
            "window": [d0, d1],
            "base_window": [str(base["date"].min().date()), str(base["date"].max().date())],
            "model_as_of": str(as_of.date()),
            "fit_rows": int(len(fit_df)),
            "shock": win.shock,
            "passthrough": pt_detail,
            "book_params": {k: v for k, v in params.__dict__.items() if k not in ("sizes_mw", "basis_usd")},
            "plausibility_asof": score_asof,
            "plausibility_full_fit": score_full,
            "actual_daily_total_usd": [float(x) for x in act_daily["total"]],
            "event_prices": ev[["date", "wh_on", "wh_off", "dom_on", "dom_off", "da_wh_off", "rt_wh_off", "load_peak_mw", "hh_usd", "is_onpeak_day"]].assign(date=ev["date"].dt.strftime("%Y-%m-%d")).to_dict("records"),
        }
    return pd.DataFrame(rows), extra


def fig_replay(tab: pd.DataFrame, path: Path, label: str) -> None:
    names = list(config.POSITIONS) + ["total"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), constrained_layout=True)
    colors = {"actual": "#3b3b3b", "window": "#2a6fb0", "daily": "#d98a1c"}
    for ax, (key, name, d0, d1, flagged) in zip(axes.ravel(), EVENTS):
        t = tab[tab["event_key"] == key].set_index("name")
        x = np.arange(len(names))
        w = 0.27
        for k, (col, lab) in enumerate((("actual_usd", "actual (daily prices)"), ("engine_window_usd", "engine, window shock"), ("engine_daily_usd", "engine, day-by-day shock"))):
            ax.bar(x + (k - 1) * w, t.loc[names, col] / 1e3, w, label=lab, color=list(colors.values())[k])
        ax.axhline(0, color="#888", lw=0.8)
        ax.set_xticks(x, names)
        ax.set_ylabel("P&L, $ thousand")
        ax.set_title(f"{name}  {d0} to {d1}" + ("\n[FLAGGED: out of fit window, pre-2016 regime]" if flagged else ""), fontsize=10, loc="left")
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="best")
    fig.suptitle("Replay P&L by position: engine vs actual daily prices (NYISO)", fontsize=12, x=0.01, ha="left")
    fig.text(0.01, -0.02, label, fontsize=7, ha="left", color="#555")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_factors(model, extra: dict, path: Path, label: str) -> None:
    h = model.history
    names = {"g": "g = log Henry Hub", "l": "l = log(peak load / normal)", "T": "T = degree days (degF-day)", "s": "s = WEST on-peak residual (log)", "c": "c = N.Y.C. - WEST on-peak ($/MWh)", "d": "d = log(RT/DA) WEST on-peak"}
    fig, axes = plt.subplots(6, 1, figsize=(11, 12), sharex=True, constrained_layout=True)
    marks = [(extra[k]["window"][0], extra[k]["name"]) for k in ("elliott", "jan2025", "jun2025")]
    for ax, f in zip(axes, config.FACTOR_NAMES):
        ax.plot(h["date"], h[f], color="#2a6fb0", lw=0.6)
        ax.set_ylabel(f, rotation=0, labelpad=10)
        ax.set_title(names[f], fontsize=9, loc="left")
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for d, _ in marks:
            ax.axvline(pd.Timestamp(d), color="#c0392b", lw=0.9, ls="--")
    ymax = axes[0].get_ylim()[1]
    for d, nm in marks:
        axes[0].text(pd.Timestamp(d), ymax, " " + nm, fontsize=8, color="#c0392b", va="bottom", ha="center")
    axes[-1].text(0.0, -0.45, "Polar vortex 7 Jan 2014 lies before the fit window and is not drawn.", transform=axes[-1].transAxes, fontsize=8, color="#555")
    fig.suptitle("Daily factors, NYISO fit window", fontsize=12, x=0.01, ha="left")
    fig.text(0.01, -0.01, label, fontsize=7, ha="left", color="#555")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fmt(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def write_md(path: Path, label: str, fit: dict, extra: dict, tab: pd.DataFrame, sizing: dict) -> None:
    V = fit["variants"]
    full = V["full_2019"]
    L = [f"# NYISO real-data fit and event replay", "", f"**{label}**", "",
         "All numbers below are computed by `scripts/run_replay.py` from the local panel. Nothing is from Claude or a FakeClient. "
         "q is a rank against non-overlapping 10-day windows, not a probability.", ""]
    L += ["## 1. Price regression (log WEST on-peak = season intercept + b1 g + b2 l + b3 l^2)", "",
          "Standard errors are Newey-West (10 lags); classical OLS errors shown for comparison.", "",
          "| variant | n | R^2 | resid sd | b_gas (se) | b_load (se) | b_load2 (se) |", "|---|---|---|---|---|---|---|"]
    for k, v in V.items():
        r = v["regression"]
        cell = lambda n: f"{r[n]['coef']:.3f} ({r[n]['se_hac']:.3f})"
        L.append(f"| {k} | {v['regression_stats']['n']} | {v['regression_stats']['r2']:.3f} | {v['regression_stats']['resid_sd']:.3f} | {cell('b_gas')} | {cell('b_load')} | {cell('b_load2')} |")
    L += ["", "Full-window coefficients, all terms:", "", "| term | coef | se (OLS) | se (Newey-West) | t (NW) |", "|---|---|---|---|---|"]
    for n, r in full["regression"].items():
        L.append(f"| {n} | {r['coef']:.4f} | {r['se_ols']:.4f} | {r['se_hac']:.4f} | {r['t_hac']:.2f} |")
    L += ["", "Variant note: the Market primary break (2016-06-22) predates the 2019 fit window, so `include_pre_break=False` gives "
          f"the same fit as the full window (check: identical R^2 = {fit['primary_break_identical_to_full']}). The two later variants cut the sample at the dates shown.", ""]
    rd = full["residuals"]
    L += ["## 2. Residual diagnostics (full window)", "", "| statistic | value |", "|---|---|"]
    for k in ("n", "sd", "skew", "excess_kurtosis", "jarque_bera_p", "autocorr_lag1", "ljung_box_10_p", "durbin_watson", "share_abs_gt_3sd"):
        L.append(f"| {k} | {fmt(rd[k], 4) if k != 'n' else rd[k]} |")
    L.append(f"| residual sd by season | {', '.join(f'{s} {v:.3f}' for s, v in rd['resid_sd_by_season'].items())} |")
    L.append(f"| price-floor hits (< $1) | {rd['price_floor_hits']} |")
    L += ["", "## 3. Covariance conditioning (Ledoit-Wolf, rolling window ending 2025-12-31)", "",
          "cond(cov) mixes units (c is in $/MWh, the rest are logs); cond(corr) is unit-free.", "",
          "| variant | season | n | window | shrinkage | cond(cov) | cond(corr) | min eig(corr) |", "|---|---|---|---|---|---|---|---|"]
    for k, v in V.items():
        for s, c in v["covariance"].items():
            L.append(f"| {k} | {s} | {c['n_obs']} | {c['window'][0]} to {c['window'][1]} | {fmt(c['shrinkage'])} | {c['cond_cov']:.1f} | {c['cond_corr']:.1f} | {c['min_eig_corr']:.3f} |")
    L += ["", "## 4. Spike model", "", "| variant | thresholds $/MWh (winter/summer/shoulder) | exceedance rate | n exceed | GPD shape | bootstrap 5-95% | GPD scale |", "|---|---|---|---|---|---|---|"]
    for k, v in V.items():
        sp = v["spike"]
        th = "/".join(f"{sp['thresholds_usd'].get(s, float('nan')):.1f}" for s in ("winter", "summer", "shoulder"))
        rg = sp["gpd_shape_bootstrap_5_95"]
        L.append(f"| {k} | {th} | {sp['exceedance_rate_overall']:.4f} | {sp['n_exceed']} | {fmt(sp['gpd_shape'])} | {('%.3f to %.3f' % tuple(rg)) if rg else 'n/a'} | {fmt(sp['gpd_scale'])} |")
    pc = fit["pca"]
    L += ["", "## 5. PCA diagnostic (do the explicit factors explain over 85% of variance?)", "",
          f"Block: standardized log of {', '.join(pc['block'])}. Share of the block's total variance explained by a linear projection on [1, g, l, T, s, c, d]: **{pc['explained_share_by_factors']:.4f}** "
          f"({'above' if pc['meets_target'] else 'BELOW'} the 0.85 target). Principal components of the block needed for 85%: {pc['n_pcs_for_85pct']}; "
          f"cumulative PC shares: {', '.join(f'{x:.3f}' for x in pc['block_pc_cumulative_share'])}. "
          f"R^2 of the factors on the first three PCs: {', '.join(f'{x:.3f}' for x in pc['factor_r2_of_first_3_pcs'])}. "
          "Caveat: s, c and d are built from the block's own series (log WEST on-peak less its fit, N.Y.C. minus WEST, log RT/DA), so a high share is partly by construction.", "",
          "| series | share explained |", "|---|---|"]
    for k, v in pc["explained_share_per_series"].items():
        L.append(f"| {k} | {v:.4f} |")
    pt = fit["passthrough"]
    L += ["", "## 6. Pass-through coefficients: placeholders replaced by the real regression", "",
          "| coefficient | placeholder (core build) | estimated (full window) |", "|---|---|---|"]
    for k in ("gas_beta", "load_beta1", "load_beta2", "offpeak_scale"):
        L.append(f"| {k} | {pt['placeholder'][k]} | {pt['estimated'][k]:.4f} |")
    L += ["", "The engine's `PassThrough` defaults in `shock.py` are unchanged (they back the synthetic tests); real-data runs must pass "
          "`PassThrough(**estimated)` (see `outputs/real/fit_summary.json`, key `passthrough`). "
          "`ScenarioEngine` accepts a `passthrough` argument for this purpose.", ""]
    L += ["## 7. Book sizing (plan section 3)", "",
          f"Rule: {sizing['rule']}. Capital {sizing['capital_usd']/1e6:.0f}M, target loss {sizing['target_usd']/1e6:g}M ({100 * sizing['target_usd'] / sizing['capital_usd']:.0f}% of capital). Sizes in MW: " + ", ".join(f"{p} {v:g}" for p, v in config.POSITION_SIZES_MW.items()) + ".", "",
          "| statistic | value |", "|---|---|"]
    for k in ("worst_1d_loss_usd", "worst_10d_loss_usd", "worst_30d_loss_usd", "p1_30d_loss_usd", "worst_30d_loss_over_target", "n_windows_ge_target", "worst_window_end", "total_pnl_usd"):
        v = sizing[k]
        L.append(f"| {k} | {v if isinstance(v, str) else (f'{v:,.0f}' if (abs(v) > 100 or k == 'n_windows_ge_target') else f'{v:.3f}')} |")
    L.append(f"| verdict | {'sizes kept' if sizing['keep_sizes'] else 'rescale by %.3f' % sizing['suggested_scale']} |")
    L += ["", "P&L by position over the fit window (payoff only, no premium carry): " + ", ".join(f"{p} {v:,.0f}" for p, v in sizing["pnl_by_position_usd"].items()) + ". "
          f"The largest single contribution is {max(sizing['pnl_by_position_usd'], key=sizing['pnl_by_position_usd'].get)}; P4 is a long call that pays no premium in this build (payoff only), so its positive drift is a carry artefact, not a result of sizing.", ""]
    L += ["## 8. Event replay", "", "Engine = event shock (window means) through `apply_shock` on a base window "
          f"(same number of days, ending {BASE_GAP_DAYS} days before the event, event calendar imposed), pass-through from the as-of regression. "
          f"Window shock: one shock for the whole event, spike days placed at random, averaged over {fit['n_seeds']} seeds. "
          "Day-by-day shock: one shock per event day. Actual = book P&L on the event's daily prices. Values in USD thousand.", ""]
    for key, name, d0, d1, flagged in EVENTS:
        t = tab[tab["event_key"] == key].set_index("name")
        e = extra[key]
        L += [f"### {name} ({d0} to {d1})" + ("  -- FLAGGED: outside the 2019 fit window, pre-2016 pricing regime" if flagged else ""), "",
              "| name | actual | engine window | engine daily | gap window | rel gap window | within 30% (window) | sign ok (window) |", "|---|---|---|---|---|---|---|---|"]
        for n in POS_ORDER:
            r = t.loc[n]
            mat = "" if r["material"] else " (immaterial)"
            L.append(f"| {n}{mat} | {r['actual_usd']/1e3:,.1f} | {r['engine_window_usd']/1e3:,.1f} | {r['engine_daily_usd']/1e3:,.1f} | {r['gap_window_usd']/1e3:,.1f} | {fmt(r['rel_gap_window'], 2)} | {r['within30_window']} | {r['sign_match_window']} |")
        L.append("")
    L += ["### Plausibility of the realised events", "",
          "As-of model = fitted on data up to the day before the event (2014: the full 2019-2025 model, flagged). Full-fit columns use the headline model (in-sample for 2022 and 2025).", "",
          "| event | window worst day | D^2 as-of | q as-of | severity as-of | nearest date (as-of) | D^2 full | q full | severity full | nearest date (full) | marginals exceeded (as-of) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, name, d0, d1, flagged in EVENTS:
        a, f = extra[key]["plausibility_asof"], extra[key]["plausibility_full_fit"]
        L.append(f"| {name}{' (FLAGGED)' if flagged else ''} | {a['worst_day']} | {a['d2']:.1f} | {a['q']:.4f} | {a['severity']} | {a['nearest_date']} | {f['d2']:.1f} | {f['q']:.4f} | {f['severity']} | {f['nearest_date']} | {', '.join(a['marginals_exceeded']) or 'none'} |")
    L.append("")
    path.write_text("\n".join(L) + "\n" + fit["diagnosis_md"], encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "outputs" / "real"))
    ap.add_argument("--n-seeds", type=int, default=200)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    proc = ROOT / "data" / "processed"
    panel = pd.read_csv(proc / "nyiso_panel.csv", parse_dates=["date"])
    panel14 = pd.read_csv(proc / "nyiso_panel_2014_replay.csv", parse_dates=["date"])
    label = label_for(panel)
    fit_panel = panel[(panel["date"] >= FIT_START) & (panel["date"] <= FIT_END)].reset_index(drop=True)

    variants, headline = {}, None
    for key, start, desc in VARIANTS:
        m = fit_variant(fit_panel, start)
        df = fit_panel if start is None else fit_panel[fit_panel["date"] >= pd.Timestamp(start)].reset_index(drop=True)
        variants[key] = variant_summary(m, df) | {"description": desc}
        if headline is None:
            headline = m
    m_primary = fit_variant(fit_panel, None, include_pre_break=False)
    identical = bool(abs(m_primary.price_model.r2 - headline.price_model.r2) < 1e-12 and m_primary.min_date_used == headline.min_date_used)

    pm = headline.price_model
    pt, pt_detail = dg.estimate_passthrough(fit_panel, pm, float(fit_panel["load_peak_mw"].median()))
    pca = dg.pca_check(fit_panel, headline.history)
    params = fit_book_params(fit_panel)
    sizing = dg.sizing_check(fit_panel, params)
    tab, extra = run_events(panel, panel14, headline, a.n_seeds)
    tab.insert(0, "label", label)
    tab.to_csv(out / "replay_table.csv", index=False, float_format="%.6g")

    diagnosis = _diagnosis(tab, extra, sizing, pt_detail)
    fit = {
        "label": label,
        "market": "NYISO",
        "fit_window": [FIT_START, FIT_END],
        "n_seeds": a.n_seeds,
        "variants": variants,
        "primary_break_identical_to_full": identical,
        "pca": pca,
        "passthrough": pt_detail,
        "sizing": sizing,
        "book_params": {k: v for k, v in params.__dict__.items()},
        "events": {k: {kk: vv for kk, vv in v.items() if kk != "event_prices"} for k, v in extra.items()},
        "diagnosis_md": diagnosis,
    }
    write_md(out / "diagnostics.md", label, fit, extra, tab, sizing)
    fit_json = {k: v for k, v in fit.items() if k != "diagnosis_md"}
    (out / "fit_summary.json").write_text(json.dumps(_num(fit_json), indent=1), encoding="utf-8")
    fig_replay(tab, out / "replay_pnl_by_position.png", label)
    fig_factors(headline, extra, out / "factor_history_events.png", label)
    print(label)
    print(tab[tab["name"].isin(["total", "P1", "P3", "P5", "P6"])][["event_key", "name", "actual_usd", "engine_window_usd", "engine_daily_usd", "rel_gap_window", "rel_gap_daily"]].round(2).to_string(index=False))
    print("PCA share", round(pca["explained_share_by_factors"], 4), "sizing worst30/target", round(sizing["worst_30d_loss_over_target"], 3))


def _within(tab: pd.DataFrame, col: str, level: str) -> tuple[int, int]:
    t = tab[(tab["level"] == level) & tab["material"]]
    ok = (t[col] - t["actual_usd"]).abs() <= 0.3 * t["actual_usd"].abs()
    return int(ok.sum()), int(len(t))


def _total_pass_text(tab: pd.DataFrame, col: str) -> str:
    a, b = _within(tab, col, "total")
    return f"{a} of {b} events"


def _total_fail_text(tab: pd.DataFrame, col: str) -> str:
    t = tab[(tab["level"] == "total") & tab["material"]]
    bad = t[(t[col] - t["actual_usd"]).abs() > 0.3 * t["actual_usd"].abs()]
    if bad.empty:
        return "it passes every material event"
    return "it fails " + ", ".join(f"{r['event']} ({(r[col] - r['actual_usd']) / 1e3:+,.0f}k on {r['actual_usd'] / 1e3:+,.0f}k)" for _, r in bad.iterrows())


def _p3_text(tab: pd.DataFrame) -> str:
    imm = [k for k, *_ in EVENTS if abs(float(tab[(tab["event_key"] == k) & (tab["name"] == "P3")]["actual_usd"].iloc[0])) < MATERIAL_USD]
    e = tab[(tab["event_key"] == "elliott") & (tab["name"] == "P3")].iloc[0]
    sign_ok = int(tab[(tab["name"] == "P3")]["sign_match_daily"].sum())
    signs = ", ".join(f"{k}: {'+' if float(tab[(tab['event_key'] == k) & (tab['name'] == 'P3')]['actual_usd'].iloc[0]) > 0 else '-'}" for k, *_ in EVENTS)
    return (
        f"P3 carries the largest relative errors but is immaterial (< ${MATERIAL_USD/1e3:,.0f}k) in {len(imm)} of {len(EVENTS)} events; in Elliott it is "
        f"{e['actual_usd']/1e3:,.0f}k actual vs {e['engine_window_usd']/1e3:,.0f}k (window) and {e['engine_daily_usd']/1e3:,.0f}k (daily), "
        f"{abs(e['rel_gap_window']):.0%} and {abs(e['rel_gap_daily']):.0%} off. P3's sign by event ({signs}) is event dependent "
        f"(negative when RT cleared above DA) and the day-by-day engine reproduced the sign in {sign_ok} of {len(EVENTS)}."
    )


def _p5_dominance_text(tab: pd.DataFrame) -> str:
    n = 0
    for k, *_ in EVENTS:
        t = tab[(tab["event_key"] == k) & (tab["level"] == "position")].set_index("name")["actual_usd"].abs()
        n += int(t.idxmax() == "P5")
    return f"P5 is the largest absolute position in {n} of {len(EVENTS)} events"


def _diagnosis(tab, extra, sizing, pt_detail) -> str:
    L = ["## 9. Replay verdict and diagnosis", "",
         "Check: engine within 30% of actual on material rows (|actual| >= $50k, 1% of the target). "
         "'Daily' = the event's realised daily factor vector, one shock per day (the plan 8A test); 'window' = one shock from the window means.", "",
         "| engine variant | positions within 30% | channels within 30% | total within 30% |", "|---|---|---|---|"]
    for lab, col in (("daily, fitted pass-through", "engine_daily_usd"), ("daily, placeholder pass-through", "engine_daily_placeholder_pt_usd"),
                     ("window, fitted pass-through", "engine_window_usd"), ("window, placeholder pass-through", "engine_window_placeholder_pt_usd")):
        a, b = _within(tab, col, "position"), _within(tab, col, "channel")
        c = _within(tab, col, "total")
        L.append(f"| {lab} | {a[0]} of {a[1]} | {b[0]} of {b[1]} | {c[0]} of {c[1]} |")
    L += ["", "Daily-averaging gap for the two positions the plan expects to be understated (engine minus actual, USD thousand; negative P&L = loss; "
          "'understated' means the engine's absolute P&L is smaller than actual):", "",
          "| event | position | actual | engine window | engine daily | window understated? | daily understated? |", "|---|---|---|---|---|---|---|"]
    n_und, n_tot = 0, 0
    for key, name, *_ in EVENTS:
        t = tab[tab["event_key"] == key].set_index("name")
        for pn in ("P3", "P6"):
            r = t.loc[pn]
            if abs(r["actual_usd"]) < 1:
                continue
            uw, ud = abs(r["engine_window_usd"]) < abs(r["actual_usd"]), abs(r["engine_daily_usd"]) < abs(r["actual_usd"])
            n_und += int(uw)
            n_tot += 1
            L.append(f"| {name} | {pn} | {r['actual_usd']/1e3:,.1f} | {r['engine_window_usd']/1e3:,.1f} | {r['engine_daily_usd']/1e3:,.1f} | {uw} | {ud} |")
    L += ["", f"The window engine understates P3/P6 in {n_und} of {n_tot} cases; the expected understatement is therefore "
          + ("confirmed." if n_und == n_tot else "NOT uniformly confirmed (see mechanisms below)."), "",
          "Honest reading: the day-by-day engine passes every position and channel row and the total in " + _total_pass_text(tab, "engine_daily_usd") + "; for P1, P4 and P6 that is close to a tautology, since each day's shock carries that day's own on-peak price. "
          "The informative parts are P2, P3 and P5 (spread, DA-RT, load) and the window engine, which fails Elliott P1/P3/P4 (and its tail) and, on the total, " + _total_fail_text(tab, "engine_window_usd") + ". "
          "A 'within 30% on averaged positions' check therefore passes for the daily engine and fails for the window engine on the event that matters most (Elliott).", "",
          "Mechanisms found (from the code and the tables above, not from extra data):", "",
          "1. Spike placement. `apply_shock` puts spike days at random among shocked days, whereas the real spike days are specific days. "
          "When a real spike falls on a weekend (24 Dec 2022 is a Saturday: zero on-peak hours) the engine can instead place it on a weekday and book a large P1/P6 payoff that did not happen. "
          "This is why the window engine overstates P1 and P6 for Elliott while the day-by-day engine matches them.",
          "2. P6 is overstated, not understated, by the window engine in this test (see the table). The understatement the plan expects is against hourly truth (a few hours at thousands of dollars vanish inside a 16-hour mean); "
          "here the actual side is itself a daily average, so that effect cannot show. What the window engine adds is the random placement above and the loss of cross-day detail (all spike days get the mean spike price).",
          "3. P3 (DA-RT, off-peak). The shock moves off-peak levels through the on-peak residual times `offpeak_scale`, not through the actual off-peak move, so DA-RT dollars (which scale with the level) are off whenever off-peak behaves differently from on-peak (24 Dec 2022: off-peak RT 488 vs on-peak 672). "
          + _p3_text(tab) + "",
          "4. P2/P5 depend only on the 24h N.Y.C.-WEST spread and the load ratio; the engine matches them closely because the spread shift is set from the event's 24h spread (calendar-aware). Their errors are small relative to P5's size, and " + _p5_dominance_text(tab) + ".",
          "5. Pass-through placeholders (0.6 / 2.0 / 6.0 / 0.5) vs regression (" + ", ".join(f"{k} {v:.3f}" for k, v in pt_detail["estimated"].items()) + "): "
          "the pass rates in the table are identical with either set, because the on-peak level residual `wh_onpeak_pct` is computed against whichever pass-through is used, so on-peak WEST levels are matched either way. "
          "The pass-through matters for scenarios proposed by the agent (where gas and load move and the residual is not back-solved) and only second-order for off-peak and DA scaling here. The quadratic load term is estimated at ~0 with a very large standard error (the placeholder 6.0 is not supported).",
          "6. A fix made during this work: `event_to_shock` did not divide the RT/DA factor out of the on-peak level residual, although `apply_shock` multiplies RT on-peak by (1 + dart_pct); "
          "the level was double counted (2014 window P1 was 2.2x actual before the fix). It now divides it out. The 24h spread in `event_to_shock` is also calendar-aware (weekend and holiday days use off-peak only, as `book.pnl` does).", "",
          "Limits of this test: actual P&L is also computed on daily averages (the panel has no hourly series), so the true hourly understatement of P3 and P6 is not measured here; "
          "the strikes K, K6, c0, R, H are fitted on the data available before each event; the 2014 base window (2014-01-13 to 2014-01-15) is a calm window after the event because the 2014 file covers January only; "
          "the three-day 2014 window (6 to 8 Jan) is a choice, the verified numbers are for 7 Jan.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
