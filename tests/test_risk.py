"""Risk-model tests on the SYNTHETIC panel (no real data, no network)."""

import numpy as np
import pandas as pd
import pytest

from revstress import config
from revstress.panel import panel_window
from revstress.risk import fit_risk_model, score_scenario
from revstress.shock import apply_shock
from revstress.synthetic import generate_synthetic_panel


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return generate_synthetic_panel(seed=1, warn=False)


@pytest.fixture(scope="module")
def model(panel):
    return fit_risk_model(panel, n_boot=40)


def test_windows_non_overlapping(model):
    ws, we = model.window_start, model.window_end
    assert len(ws) == len(model.window_d2) > 100
    assert ((we - ws).days == config.WINDOW_DAYS - 1).all()
    assert (ws[1:] > we[:-1]).all()


def test_shrinkage_covariance_psd(model):
    for sc in model.season_cov.values():
        assert np.allclose(sc.cov, sc.cov.T)
        assert np.linalg.eigvalsh(sc.cov).min() > 0
        assert 0.0 <= sc.shrinkage <= 1.0


def test_mcd_alternative_runs(panel):
    m = fit_risk_model(panel, covariance_method="mcd", n_boot=5)
    assert all(np.linalg.eigvalsh(sc.cov).min() > 0 for sc in m.season_cov.values())


def test_q_monotone_in_severity(model):
    sc = model.season_cov["winter"]
    sd = np.sqrt(np.diag(sc.cov))
    res = []
    for k in [0, 1, 2, 3, 4, 6, 8, 12]:
        vec = dict(zip(("g", "l", "s", "c", "d"), sc.mu + k * sd))
        res.append(score_scenario(vec, model, season="winter"))
    d2 = [r["d2"] for r in res]
    q = [r["q"] for r in res]
    assert d2 == sorted(d2)
    assert all(a >= b for a, b in zip(q, q[1:]))
    assert q[0] == 1.0 and q[-1] == 0.0
    assert all(r["q_is_probability"] is False for r in res)


def test_q_monotone_on_paths(model, panel):
    base = panel_window(panel, "2025-01-05", 10)
    out = []
    for pct in (0, 50, 150, 400):
        shock = {"gas_hh_pct": pct, "load_peak_ratio": 1.0 + pct / 1000, "duration_days": 10}
        out.append(score_scenario(apply_shock(base, shock, rng_seed=0), model))
    pairs = sorted((r["d2"], r["q"]) for r in out)
    qs = [q for _, q in pairs]
    assert all(a >= b for a, b in zip(qs, qs[1:]))
    assert out[0]["spike"] is not None and out[0]["nearest_date"]


def test_no_data_after_as_of(panel):
    as_of = pd.Timestamp("2023-06-30")
    m1 = fit_risk_model(panel, as_of=as_of, n_boot=10)
    truncated = panel[panel["date"] <= as_of].copy()
    tampered = panel.copy()
    tampered.loc[tampered["date"] > as_of, ["wh_on", "rt_wh_on", "hh_usd", "load_peak_mw"]] *= 3.0
    m2 = fit_risk_model(truncated, n_boot=10)
    m3 = fit_risk_model(tampered, as_of=as_of, n_boot=10)
    assert m1.max_date_used <= as_of
    for m in (m2, m3):
        assert m.price_model == m1.price_model
        assert np.array_equal(m.window_d2, m1.window_d2)
        for s in m1.season_cov:
            assert np.array_equal(m.season_cov[s].cov, m1.season_cov[s].cov)
        assert m.spike.thresholds_usd == m1.spike.thresholds_usd


def test_structural_break_argument(panel):
    full = fit_risk_model(panel, n_boot=5)
    post = fit_risk_model(panel, include_pre_break=False, n_boot=5)
    assert post.min_date_used >= pd.Timestamp("2022-10-01")
    assert full.min_date_used < pd.Timestamp("2022-10-01")
    assert len(post.window_d2) < len(full.window_d2)


def test_severity_classes(model):
    h = model.history
    # ordinary: the seasonal centre
    sc = model.season_cov["shoulder"]
    centre = dict(zip(("g", "l", "s", "c", "d"), sc.mu))
    assert score_scenario(centre, model, season="shoulder")["severity"] == "ordinary"

    # adverse: a historical day whose D^2 sits near the 97th percentile of window D^2
    target = np.quantile(model.window_d2, 0.97)
    cand = h[h["d2"] >= target].sort_values("d2").iloc[0]
    r = score_scenario({**{f: cand[f] for f in ("g", "l", "T", "s", "c", "d")}, "season": cand["season"]}, model)
    assert 0.01 <= r["q"] <= 0.05 and r["severity"] == "adverse"

    # severe: the most extreme historical day (q = 1 window of ~250), inside every marginal limit
    top = h.sort_values("d2").iloc[-1]
    r = score_scenario({**{f: top[f] for f in ("g", "l", "T", "s", "c", "d")}, "season": top["season"]}, model)
    assert r["q"] < 0.01 and r["severity"] == "severe" and not r["marginals_exceeded"]

    # implausible: marginal beyond 1.25x historical max
    sc = model.season_cov["winter"]
    vec = dict(zip(("g", "l", "s", "c", "d"), sc.mu))
    vec["l"] = model.limits["winter"]["l"][1] + 0.05
    r = score_scenario(vec, model, season="winter")
    assert r["severity"] == "implausible" and r["marginals_exceeded"][0]["factor"] == "l"


def test_hard_rule_weather_with_falling_load(model, panel):
    base = panel_window(panel, "2025-01-05", 10)
    shock = {"load_peak_ratio": 0.8, "duration_days": 10}
    cold = base.assign(hdd=base["hdd"] + 40.0)
    r = score_scenario(apply_shock(cold, shock, rng_seed=0), model)
    assert "extreme_weather_with_falling_load_winter" in r["hard_rule_failures"]
    assert r["severity"] == "implausible"


def test_hard_rule_energy_cap(model, panel):
    path = apply_shock(panel_window(panel, "2025-01-05", 10), {"duration_days": 10}, rng_seed=0)
    path.loc[0, "wh_on"] = 4000.0
    assert "energy_component_above_3700" in score_scenario(path, model)["hard_rule_failures"]


def test_spike_component(model):
    sp = model.spike
    assert set(sp.thresholds_usd) == set(config.SEASONS)
    assert sp.gpd_shape_range is not None and sp.gpd_shape_range[0] <= sp.gpd_shape <= sp.gpd_shape_range[1]
    assert abs(np.mean(list(sp.hist_exceed_share.values())) - 0.025) < 0.01


def test_vector_input_errors(model):
    with pytest.raises(ValueError):
        score_scenario({"g": 1.0}, model, season="winter")
    with pytest.raises(ValueError):
        score_scenario({"g": 1, "l": 0, "s": 0, "c": 0, "d": 0}, model)
