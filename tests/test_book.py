import numpy as np
import pandas as pd
import pytest

from revstress import config
from conftest import make_panel
from revstress.book import fit_book_params, is_breach, pnl, pnl_totals, scenario_loss_usd
from revstress.panel import nerc_holidays, onpeak_day_flags
from revstress.synthetic import generate_synthetic_panel


def test_hand_computed_day(panel, params):
    r = pnl(panel.iloc[[0]], params, fallback=False).iloc[0]
    assert r["P1"] == pytest.approx(16 * 50 * 10)  # 8000
    assert r["P2"] == pytest.approx(24 * 50 * (10 - 8))  # 2400
    assert r["P3"] == pytest.approx(8 * 25 * (65 - 60))  # 1000
    assert r["P4"] == pytest.approx(16 * 100 * (100 - 8 * 5.5 - 3))  # winter basis 1.5, G=5.5 -> 84800
    assert r["P5"] == pytest.approx(24 * 200 * 1.0 * ((80 - 96.6666667) + (86.6666667 - 75)))  # -24000
    assert r["P6"] == pytest.approx(-16 * 25 * 5)  # -2000
    assert r["total"] == pytest.approx(8000 + 2400 + 1000 + 84800 - 24000 - 2000)


def test_channels_and_totals(panel, params):
    res = pnl(panel, params, fallback=False)
    assert len(res) == 5
    for p, ch in config.POSITION_CHANNEL.items():
        assert np.allclose(res[p], res[ch])
    assert np.allclose(res[list(config.POSITIONS)].sum(axis=1), res["total"])
    assert pnl_totals(res)["total"] == pytest.approx(5 * res["total"].iloc[0])


def test_p5_scales_with_load(panel, params):
    p = panel.copy()
    p["load_peak_mw"] = 154_000.0
    base = pnl(panel.iloc[[0]], params, fallback=False)["P5"].iloc[0]
    assert pnl(p.iloc[[0]], params, fallback=False)["P5"].iloc[0] == pytest.approx(1.1 * base)
    p["load_normal_mw"] = 154_000.0
    assert pnl(p.iloc[[0]], params, fallback=False)["P5"].iloc[0] == pytest.approx(base)


def test_options_zero_out_of_the_money(panel, params):
    p = panel.copy()
    p["wh_on"] = p["rt_wh_on"] = 40.0
    r = pnl(p.iloc[[0]], params, fallback=False).iloc[0]
    assert r["P4"] == 0.0 and r["P6"] == 0.0
    assert r["P1"] == pytest.approx(16 * 50 * (40 - 90))


def test_summer_basis_changes_p4(panel, params):
    p = panel.copy()
    p["date"] = pd.date_range("2027-07-12", periods=len(p), freq="D")  # July, Monday start
    assert pnl(p.iloc[[0]], params, fallback=False)["P4"].iloc[0] == pytest.approx(16 * 100 * (100 - 8 * 4.3 - 3))


def test_fallback_book_only_p1_p4_p6(panel, params):
    thin = panel[["date", "wh_on", "hh_usd"]]
    res = pnl(thin, params, fallback=True)
    assert (res[["P2", "P3", "P5", "congestion", "dart", "zone_volume"]] == 0).all().all()
    full = pnl(panel, params, fallback=False)
    for c in ("P1", "P4", "P6"):
        assert np.allclose(res[c], full[c])


def test_fallback_flag_from_config(panel, params, monkeypatch):
    monkeypatch.setattr(config, "FALLBACK_BOOK", True)
    assert (pnl(panel, params)["P2"] == 0).all()


def test_loss_and_breach(panel, params):
    res = pnl(panel, params, fallback=False)
    assert scenario_loss_usd(res) == pytest.approx(-res["total"].sum())
    assert not is_breach(res)
    res["total"] = -(config.LOSS_TARGET_USD + 1e6) / len(res)
    assert is_breach(res)


def test_fit_params_and_determinism():
    df = generate_synthetic_panel(5, "2019-01-01", "2021-12-31", warn=False)
    bp = fit_book_params(df)
    on_days = df.loc[onpeak_day_flags(df), "wh_on"]
    assert bp.k6_usd == pytest.approx(on_days.quantile(0.99)) and bp.k6_usd > bp.k1_usd
    assert bp.k1_usd == pytest.approx(on_days.mean())
    a, b = pnl(df, bp, fallback=False), pnl(df, bp, fallback=False)
    assert a.equals(b)
    assert abs(a["P1"].mean()) < 1e-6


def test_nerc_holidays_and_onpeak_flags():
    h = nerc_holidays(2027)
    assert pd.Timestamp("2027-05-31") in h and pd.Timestamp("2027-09-06") in h and pd.Timestamp("2027-11-25") in h
    assert pd.Timestamp("2027-07-05") in h  # July 4 is a Sunday: observed Monday
    assert pd.Timestamp("2027-12-24") not in h  # Christmas on a Saturday is not observed on Friday
    df = pd.DataFrame({"date": pd.to_datetime(["2027-01-08", "2027-01-09", "2027-01-10", "2027-01-11", "2027-01-01"])})
    assert list(onpeak_day_flags(df)) == [True, False, False, True, False]  # Fri, Sat, Sun, Mon, New Year (Fri)
    assert list(onpeak_day_flags(df.assign(is_onpeak_day=[True] * 5))) == [True] * 5


def test_weekend_has_no_onpeak_legs(params):
    """Regression: weekends and NERC holidays have 0 on-peak hours (plan section 3: HE8-23 on weekdays)."""
    wk = make_panel(2, "2027-01-15")  # Friday, Saturday
    res = pnl(wk, params, fallback=False)
    fri, sat = res.iloc[0], res.iloc[1]
    assert fri["P1"] == pytest.approx(16 * 50 * 10)
    assert sat["P1"] == 0.0 and sat["P4"] == 0.0 and sat["P6"] == 0.0
    assert sat["P2"] == pytest.approx(24 * 50 * ((70 - 60) - 8))  # 24 h off-peak spread
    assert sat["P3"] == pytest.approx(24 * 25 * (65 - 60))
    wh24, dom24 = 60.0, 70.0
    assert sat["P5"] == pytest.approx(24 * 200 * 1.0 * ((80 - dom24) + (wh24 - 75)))
    only_fri = pnl(wk.iloc[[0]], params, fallback=False)
    assert pnl_totals(res)["P1"] == pytest.approx(only_fri["P1"].iloc[0])
