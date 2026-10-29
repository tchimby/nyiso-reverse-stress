"""Tests for revstress.eval.diagnostics and the replay additions. Hand-made fixtures; real-data smoke tests skip
cleanly if data/processed/nyiso_panel.csv is missing. No network."""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from revstress import config
from revstress.book import BookParams, pnl
from revstress.eval import diagnostics as dg
from revstress.eval import replay
from revstress.risk.factors import compute_factors, fit_price_model
from revstress.synthetic import generate_synthetic_panel

REAL = Path(__file__).resolve().parents[1] / "data" / "processed" / "nyiso_panel.csv"


@pytest.fixture(scope="module")
def df():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return generate_synthetic_panel(seed=3, start="2021-01-01", end="2022-12-31", warn=False)


def test_regression_table_matches_price_model(df):
    pm = fit_price_model(df, daily=False)  # regression_table is the season-intercept spec; the daily model adds harmonics
    tab, st = dg.regression_table(df, pm)
    assert tab.loc["b_gas", "coef"] == pytest.approx(pm.b_gas)
    assert tab.loc["b_load", "coef"] == pytest.approx(pm.b_load)
    assert st["r2"] == pytest.approx(pm.r2)
    assert (tab["se_ols"] > 0).all() and (tab["se_hac"] > 0).all()
    assert st["n"] == len(df)


def test_daily_model_adds_harmonics_and_improves_fit(df):
    base, daily = fit_price_model(df, daily=False), fit_price_model(df)
    assert base.harm == () and len(daily.harm) == 6
    assert daily.r2 >= base.r2 - 1e-12 and daily.n_obs == base.n_obs


def test_regression_recovers_exact_relation():
    n = 300
    d = pd.date_range("2021-01-01", periods=n)
    rng = np.random.default_rng(0)
    base = pd.DataFrame({"date": d, "load_peak_mw": 20000 * np.exp(rng.normal(0, 0.05, n)), "hh_usd": np.exp(rng.normal(1, 0.2, n))})
    base["wh_on"] = 1.0
    pm = fit_price_model(base)
    g = np.log(base["hh_usd"])
    l = np.log(base["load_peak_mw"] / np.array([pm.load_normal_mw_by_month[m] for m in d.month]))
    base["wh_on"] = np.exp(2.0 + 0.5 * g + 3.0 * l)
    pm = fit_price_model(base)
    tab, st = dg.regression_table(base, pm)
    assert tab.loc["b_gas", "coef"] == pytest.approx(0.5, abs=1e-6)
    assert tab.loc["b_load", "coef"] == pytest.approx(3.0, abs=1e-6)
    assert st["r2"] == pytest.approx(1.0, abs=1e-9)


def test_residual_diagnostics_keys(df):
    r = dg.residual_diagnostics(df, fit_price_model(df))
    assert r["n"] == len(df) and 0.0 <= r["ljung_box_10_p"] <= 1.0 and set(r["resid_sd_by_season"]) <= set(config.SEASONS)


def test_pca_check_bounds_and_identity(df):
    pm = fit_price_model(df)
    fac = compute_factors(df, pm)
    out = dg.pca_check(df, fac)
    assert 0.0 <= out["explained_share_by_factors"] <= 1.0
    assert out["block_pc_cumulative_share"][-1] == pytest.approx(1.0)
    assert out["meets_target"] == (out["explained_share_by_factors"] > 0.85)


def test_passthrough_estimate_is_fitted_not_placeholder(df):
    pt, detail = dg.estimate_passthrough(df, fit_price_model(df), 20000.0)
    assert pt.l_normal_mw == 20000.0 and 0.0 <= pt.offpeak_scale <= 1.5
    assert detail["estimated"]["gas_beta"] == pt.gas_beta


def test_sizing_check_rule_by_hand():
    n = 40
    p = pd.DataFrame(
        {
            "date": pd.date_range("2023-03-06", periods=n),
            "wh_on": 100.0, "wh_off": 60.0, "dom_on": 100.0, "dom_off": 60.0, "da_wh_off": 60.0, "rt_wh_off": 60.0,
            "da_wh_on": 100.0, "rt_wh_on": 100.0, "load_peak_mw": 20000.0, "hh_usd": 1.0, "hdd": 0.0, "cdd": 0.0,
            "is_onpeak_day": True,
        }
    )
    p.loc[10:12, ["wh_on", "rt_wh_on"]] = 100.0 + 50.0  # +50 on 3 days: P1 pays 16*50*50 = 40,000/day (long), no loss
    params = BookParams(k1_usd=100.0, c0_usd=0.0, k6_usd=1e9, r_usd=100.0, h_usd=100.0, l_normal_mw=20000.0)
    s = dg.sizing_check(p, params, horizon_days=10)
    assert s["worst_30d_loss_usd"] == s["worst_30d_loss_usd"]  # key kept for any horizon
    daily = pnl(p, params)["total"]
    assert s["worst_1d_loss_usd"] == pytest.approx(-daily.min())
    assert s["keep_sizes"] == (0.5 <= s["worst_30d_loss_over_target"] <= 1.0)


def test_wh24_is_calendar_aware():
    d = pd.DataFrame({"date": pd.to_datetime(["2023-03-03", "2023-03-04"]), "wh_on": [90.0, 90.0], "wh_off": [30.0, 30.0]})
    w = replay._wh24(d)
    assert w.iloc[0] == pytest.approx((16 * 90 + 8 * 30) / 24)  # Friday
    assert w.iloc[1] == pytest.approx(30.0)  # Saturday: off-peak only


def test_replay_daily_length_mismatch(df):
    from revstress.book import fit_book_params

    with pytest.raises(ValueError):
        replay.replay_event_daily(df.iloc[:3], df.iloc[:4], fit_book_params(df))


def test_replay_daily_identity(df):
    from revstress.book import fit_book_params

    params = fit_book_params(df)
    win = df.iloc[20:25].reset_index(drop=True)
    eng = replay.replay_event_daily(win, win, params, spike_threshold_usd=1e9)
    act = pnl(win, params)[["P1", "P2", "P3", "P4", "P5", "P6", "total"]].sum()
    assert np.allclose(eng[act.index].to_numpy(), act.to_numpy(), atol=1.0)


@pytest.mark.skipif(not REAL.exists(), reason="data/processed/nyiso_panel.csv missing")
def test_real_panel_fit_and_event_days():
    from revstress.risk import fit_risk_model

    old = config.MARKET
    config.MARKET = "NYISO"
    try:
        p = pd.read_csv(REAL, parse_dates=["date"])
        fit = p[(p["date"] >= "2019-01-01") & (p["date"] <= "2025-12-31")].reset_index(drop=True)
        m = fit_risk_model(fit, as_of="2025-12-31")
        assert m.max_date_used <= pd.Timestamp("2025-12-31")
        tab, st = dg.regression_table(fit, m.price_model)
        assert st["n"] == len(fit) and tab["se_hac"].gt(0).all()
        ev = p[p["date"] == "2025-06-24"].iloc[0]
        assert ev["wh_on"] == pytest.approx(416.5, rel=0.01) and ev["dom_on"] == pytest.approx(625.5, rel=0.01)
    finally:
        config.MARKET = old
