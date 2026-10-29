import numpy as np
import pytest

from revstress import config
from revstress.book import pnl
from revstress.shock import PassThrough, apply_shock, validate_shock
from conftest import make_panel

ZERO = PassThrough(gas_beta=0.0, load_beta1=0.0, load_beta2=0.0)


def test_neutral_shock_is_identity(panel):
    out = apply_shock(panel, {}, 0)
    for c in panel.columns:
        if c == "date":
            assert (out[c] == panel[c]).all()
        else:
            assert np.allclose(out[c], panel[c])
    assert not out["shock_day"].any()


def test_input_not_modified(panel):
    before = panel.copy()
    apply_shock(panel, {"gas_hh_pct": 50, "duration_days": 3, "spike_days": 1, "spike_daily_avg_usd": 500}, 1)
    assert panel.equals(before)


def test_duration_limits_shock_to_first_days(panel):
    out = apply_shock(panel, {"wh_onpeak_pct": 100, "duration_days": 2}, 0, ZERO)
    assert list(out["shock_day"]) == [True, True, False, False, False]
    assert np.allclose(out["wh_on"], [200, 200, 100, 100, 100])
    assert np.allclose(out["rt_wh_on"], out["wh_on"])
    assert np.allclose(out["da_wh_on"], [190, 190, 95, 95, 95])
    assert np.allclose(out["hh_usd"], 4.0)


def test_gas_shock_sign_and_exact_hh(panel):
    up = apply_shock(panel, {"gas_hh_pct": 100, "duration_days": 5}, 0)
    dn = apply_shock(panel, {"gas_hh_pct": -50, "duration_days": 5}, 0)
    assert np.allclose(up["hh_usd"], 8.0) and np.allclose(dn["hh_usd"], 2.0)
    assert (up["wh_on"] > panel["wh_on"]).all() and (dn["wh_on"] < panel["wh_on"]).all()
    assert np.allclose(up["wh_on"], 100 * np.exp(0.6 * np.log(2)))


def test_load_ratio_and_dc_shock(panel):
    out = apply_shock(panel, {"load_peak_ratio": 1.1, "dc_load_shock_mw": 1000, "duration_days": 3}, 0)
    assert np.allclose(out["load_peak_mw"], [155_000.0] * 3 + [140_000.0] * 2)
    assert (out["wh_on"].iloc[:3] > 100).all() and np.allclose(out["wh_on"].iloc[3:], 100)
    assert np.allclose(out["load_normal_mw"], 140_000.0)
    lower = apply_shock(panel, {"load_peak_ratio": 0.9, "duration_days": 3}, 0)
    assert (lower["wh_on"].iloc[:3] < 100).all()


def test_dom_spread_and_dart(panel):
    out = apply_shock(panel, {"dom_minus_wh_usd": 40, "dart_pct": 25, "duration_days": 5}, 0, ZERO)
    assert np.allclose(out["dom_on"] - out["wh_on"], 10 + 40)
    assert np.allclose(out["dom_off"] - out["wh_off"], 10 + 40)
    assert np.allclose(out["rt_wh_off"], 60 * 1.25) and np.allclose(out["da_wh_off"], 65)
    assert np.allclose(out["rt_wh_on"], 125)


def test_spikes_count_determinism_and_placement(panel):
    sh = {"spike_days": 2, "spike_daily_avg_usd": 600, "duration_days": 4}
    a, b = apply_shock(panel, sh, 7), apply_shock(panel, sh, 7)
    assert a.equals(b)
    assert a["spike_day"].sum() == 2 and not a["spike_day"].iloc[4]
    assert np.allclose(a.loc[a["spike_day"], "wh_on"], 600)
    assert np.allclose(a.loc[~a["spike_day"], "wh_on"], 100)
    placements = {tuple(apply_shock(panel, sh, s)["spike_day"]) for s in range(20)}
    assert len(placements) > 1


def test_energy_component_clipped_dom_may_exceed(panel):
    out = apply_shock(panel, {"spike_days": 1, "spike_daily_avg_usd": 9000, "duration_days": 2}, 3, ZERO)
    cap = config.ENERGY_COMPONENT_CAP_USD
    assert out["wh_on"].max() == cap and out["rt_wh_on"].max() == cap
    assert out["energy_clipped"].sum() == 1
    assert out["dom_on"].max() == pytest.approx(cap + 10)  # spread added after clipping
    big = apply_shock(panel, {"wh_onpeak_pct": 5000, "duration_days": 5}, 0, ZERO)
    assert (big["wh_on"] <= cap).all() and (big["da_wh_on"] <= cap).all() and big["energy_clipped"].all()


def test_spike_never_lowers_price(panel):
    out = apply_shock(panel, {"spike_days": 1, "spike_daily_avg_usd": 50, "duration_days": 1}, 0, ZERO)
    assert (out["wh_on"] >= 100).all()


@pytest.mark.parametrize(
    "bad",
    [
        {"duration_days": 6},
        {"duration_days": 2, "spike_days": 3},
        {"load_peak_ratio": 0},
        {"gas_hh_pct": -100},
        {"wh_onpeak_pct": -120},
        {"dart_pct": -100},
        {"spike_daily_avg_usd": -1},
        {"nonsense": 1},
    ],
)
def test_invalid_shocks_raise(panel, bad):
    with pytest.raises(ValueError):
        apply_shock(panel, bad, 0)


def test_validate_fills_defaults():
    assert validate_shock({"gas_hh_pct": 10}, 5)["load_peak_ratio"] == 1.0
    assert set(validate_shock({}, 5)) == set(config.SHOCK_KEYS)


def test_cold_snap_signs_on_pnl(params):
    p = make_panel(10)
    base = pnl(p, params, fallback=False).drop(columns="date").sum()
    sh = {
        "gas_hh_pct": 60, "load_peak_ratio": 1.1, "wh_onpeak_pct": 50, "dart_pct": 30,
        "dom_minus_wh_usd": 30, "spike_days": 3, "spike_daily_avg_usd": 600, "duration_days": 10,
    }
    snap = pnl(apply_shock(p, sh, 0), params, fallback=False).drop(columns="date").sum()
    assert snap["P1"] > base["P1"] and snap["P4"] > base["P4"]
    assert snap["P3"] < base["P3"] and snap["P5"] < base["P5"] and snap["P6"] < base["P6"]
    assert snap["P2"] > base["P2"]  # long DOM-WH spread gains when the spread widens
    flip = apply_shock(p, {"dom_minus_wh_usd": -30, "duration_days": 10}, 0)
    assert pnl(flip, params, fallback=False)["P2"].sum() < base["P2"]


def test_weather_slopes_map_load_ratio_to_degree_days(panel):
    from revstress.shock import DegreeDaySlopes, fit_degree_day_slopes

    slopes = DegreeDaySlopes(hdd=0.002, cdd=0.004)
    out = apply_shock(panel, {"load_peak_ratio": 1.1, "duration_days": 3}, 0, weather=slopes)
    assert out["hdd"].iloc[:3].to_numpy() == pytest.approx(30.0 + np.log(1.1) / 0.002)
    assert (out["hdd"].iloc[3:] == 30.0).all() and (out["cdd"] == 0.0).all()
    cooler = apply_shock(panel, {"load_peak_ratio": 0.5, "duration_days": 3}, 0, weather=slopes)
    assert (cooler["hdd"].iloc[:3] == 0.0).all()
    unchanged = apply_shock(panel, {"load_peak_ratio": 1.1, "duration_days": 3}, 0)
    assert (unchanged["hdd"] == 30.0).all()
    zero = apply_shock(panel, {"load_peak_ratio": 1.1, "duration_days": 3}, 0, weather=DegreeDaySlopes(0.0, 0.0))
    assert (zero["hdd"] == 30.0).all()
    from revstress.synthetic import generate_synthetic_panel

    fitted = fit_degree_day_slopes(generate_synthetic_panel(1, "2019-01-01", "2021-12-31", warn=False))
    assert fitted.hdd > 0 and fitted.cdd > 0
