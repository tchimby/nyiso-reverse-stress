"""Tests for the book-size selection rule, the warm-started plausibility-constrained optimizer and the sensitivity table.

Hand-made fixtures only (stub engine, made-up records); no data files, no network, no Claude.
"""

import numpy as np
import pandas as pd
import pytest

from revstress import config
from revstress.baselines import cond_gaussian_search, optimizer_search, random_search
from revstress.baselines.common import FACTOR_ORDER
from revstress.eval import diagnostics as dg
from revstress.eval import metrics, sizing
from stub_engine import stub_engine_fn, stub_spec

TARGET = 5e6


# ---------------------------------------------------------------- selection rule (small fixture)

def _rec(season, channel_losses, pos_losses, z, q=0.02, loss=None):
    """Baseline-schema record with a made-up engine result (positive numbers in the dicts are losses)."""
    by_channel = {c: -channel_losses.get(c, 0.0) for c in config.CHANNELS}
    by_pos = {p: -pos_losses.get(p, 0.0) for p in config.POSITIONS}
    total = sum(by_pos.values())
    return {
        "season": season, "driver_class": "cold_snap", "rules_failed": [], "rules_passed": True,
        "loss_usd": -total if loss is None else loss,
        "engine": {"pnl_total": total, "pnl_by_channel": by_channel, "pnl_by_position": by_pos, "q": q, "d2": 100.0,
                   "severity": "adverse", "z": dict(zip(FACTOR_ORDER, z)), "hard_rule_failures": []},
    }


def _seed_records(n, season, channel, pos_loss=6e6, hedge_gain=1e6, start=0):
    """n distinct breaches, 5 units apart in z space; position loss pos_loss, net loss pos_loss - hedge_gain."""
    out = []
    for i in range(n):
        z = [5.0 * (start + i), 0.0, 0.0, 0.0, 0.0]
        pos = {"P5": pos_loss, "P2": -hedge_gain}
        ch = {"zone_volume": pos_loss, "congestion": -hedge_gain}
        if channel != "zone_volume":
            pos = {"P1": pos_loss, "P2": -hedge_gain}
            ch = {"system": pos_loss, "congestion": -hedge_gain}
        out.append(_rec(season, ch, pos, z))
    return out


def test_largest_position_share_and_stats():
    r = _rec("winter", {"zone_volume": 6e6}, {"P5": 6e6, "P2": -1e6}, [0] * 5)
    assert r["loss_usd"] == pytest.approx(5e6)
    assert sizing.largest_position_share(r) == pytest.approx(6e6 / 5e6)
    assert np.isnan(sizing.largest_position_share({"engine": {"pnl_by_position": {}}, "loss_usd": 1.0}))
    seeds = {s: _seed_records(6, "winter", "zone_volume") for s in (0, 1, 2)}
    st = sizing.candidate_stats(seeds, 3.5e6, target_usd=TARGET)
    assert st["breaches_per_seed"] == [6, 6, 6] and st["min_breaches"] == 6
    assert st["share"] == pytest.approx(1.2)
    assert st["n_channels"] == 1 and st["n_seasons"] == 1 and st["worst_30d_ratio"] == pytest.approx(0.7)
    assert sizing.failed_conditions(st) == ["b", "c"]
    assert sizing.failed_conditions(st, relax=("c", "b")) == []


def test_select_candidate_prefers_admissible_then_relaxes_c_then_b():
    sizes = {"P1": 50, "P2": 50, "P3": 25, "P4": 100, "P5": 100, "P6": 25}

    def cand(min_b, share, n_ch, n_se, w, gross_scale=1.0):
        st = {"min_breaches": min_b, "share": share, "n_channels": n_ch, "n_seasons": n_se, "worst_30d_ratio": w}
        return {"sizes": {k: v * gross_scale for k, v in sizes.items()}, "stats": st}

    full = [cand(5, 0.9, 1, 1, 0.8), cand(7, 0.5, 2, 2, 0.8), cand(9, 0.5, 2, 2, 1.4), cand(6, 0.4, 2, 2, 0.8)]
    idx, relaxed = sizing.select_candidate(full)
    assert (idx, relaxed) == (1, ())  # 7 beats 6; candidate 2 fails (d) and candidate 0 fails (b), (c)
    # tie on breaches: lower share wins, then smaller gross MW
    tie = [cand(6, 0.5, 2, 2, 0.8, 2.0), cand(6, 0.4, 2, 2, 0.8, 3.0), cand(6, 0.4, 2, 2, 0.8, 1.0)]
    assert sizing.select_candidate(tie)[0] == 2
    # nothing passes (c): relax (c) first
    no_c = [cand(5, 0.5, 1, 1, 0.8), cand(8, 0.7, 1, 1, 0.8), cand(9, 0.4, 1, 2, 0.8)]
    assert sizing.select_candidate(no_c) == (2, ("c",))  # candidate 1 fails (b); 2 has the most breaches
    # (c) and (b) both fail everywhere: relax both in that order
    bad_b = [cand(5, 0.9, 1, 1, 0.8), cand(8, 1.2, 1, 1, 0.8)]
    assert sizing.select_candidate(bad_b) == (1, ("c", "b"))
    # (a) or (d) can never be relaxed
    assert sizing.select_candidate([cand(4, 0.4, 2, 2, 0.8), cand(9, 0.4, 2, 2, 0.3)]) == (None, ("c", "b", "no_candidate"))


# ---------------------------------------------------------------- optimizer: warm start + plausibility inside the search

def toy_engine(spec, l_cap=None, slope=2.6e6):
    """Deterministic made-up engine (not a risk model): loss linear in the standardised factors (c, l, g), scaled by
    duration / 7; D^2 analytic (chi-square(5) rank); 'T' listed as exceeded when the load ratio is above l_cap."""
    from scipy.stats import chi2, norm

    sd = spec.sd

    def engine(shock):
        if shock["duration_days"] < 0 or shock["load_peak_ratio"] <= 0:
            raise ValueError("bad shock")
        x = np.array([np.log1p(shock["gas_hh_pct"] / 100.0), np.log(shock["load_peak_ratio"]),
                      np.log1p(shock["wh_onpeak_pct"] / 100.0), shock["dom_minus_wh_usd"], np.log1p(shock["dart_pct"] / 100.0)])
        z = x / sd
        loss = slope * (0.5 * z[3] + 0.4 * z[1] + 0.2 * z[0]) * shock["duration_days"] / 7.0
        d2 = spec.d2(x)
        q = float(chi2.sf(d2, 5))
        exceeded = ["T"] if (l_cap is not None and shock["load_peak_ratio"] > l_cap) else []
        severity = "implausible" if (exceeded or np.abs(z).max() > 6) else ("severe" if q < 0.01 else "adverse" if q <= 0.05 else "ordinary")
        return {
            "pnl_total": -float(loss), "pnl_by_position": {}, "pnl_by_channel": {c: 0.0 for c in config.CHANNELS},
            "d2": d2, "q": q, "marginals": {f: float(norm.cdf(v)) for f, v in zip(FACTOR_ORDER, z)},
            "z": dict(zip(FACTOR_ORDER, map(float, z))), "nearest_date": "2022-12-23", "severity": severity,
            "spike_exceedance": 0.0, "marginals_exceeded": exceeded, "hard_rule_failures": [],
        }

    return engine


TAIL_D2 = 12.0  # chi-square(5) rank q = 0.034 < 5%


def test_optimizer_warm_start_returns_rule_passing_tail_breaches():
    spec = stub_spec()
    eng = toy_engine(spec)
    recs = optimizer_search(eng, spec, budget=48, seed=3, target_usd=TARGET, tail_d2=TAIL_D2)
    assert 0 < len(recs) <= 48 and all(r["arm"] == "optimizer" for r in recs)
    # warm start structure (the closed-form conditional-Gaussian point, with this arm's own calls): the base point first,
    # then one forward-difference step per core factor, each moving exactly one factor
    assert recs[0]["shocks"] == config.NEUTRAL_SHOCK | {"duration_days": 7}
    moved = [sum(abs(r["shocks"][k] - recs[0]["shocks"][k]) > 1e-12 for k in ("gas_hh_pct", "load_peak_ratio", "wh_onpeak_pct", "dom_minus_wh_usd", "dart_pct")) for r in recs[1:6]]
    assert moved == [1, 1, 1, 1, 1]
    good = [r for r in recs if r["breach"]]
    assert len(good) >= 5, "the warm-started optimizer should return several rule-passing breaches on the toy engine"
    assert all(r["rules_passed"] and r["engine"]["q"] < config.Q_ADVERSE_MAX and r["loss_usd"] >= TARGET for r in good)
    assert all(r["engine"]["d2"] > TAIL_D2 * 0.99 for r in good)
    # the unconstrained most-likely point is NOT a tail point here (that is why the tail constraint is needed)
    plain = optimizer_search(eng, spec, budget=48, seed=3, target_usd=TARGET)
    assert any(r["loss_usd"] >= TARGET and r["engine"]["q"] > config.Q_ADVERSE_MAX for r in plain[:12])


def test_optimizer_is_deterministic_and_respects_budget():
    spec, eng = stub_spec(), toy_engine(stub_spec())
    a = optimizer_search(eng, spec, budget=30, seed=1, target_usd=TARGET, tail_d2=TAIL_D2)
    b = optimizer_search(eng, spec, budget=30, seed=1, target_usd=TARGET, tail_d2=TAIL_D2)
    c = optimizer_search(eng, spec, budget=30, seed=2, target_usd=TARGET, tail_d2=TAIL_D2)
    assert len(a) <= 30 and [r["shocks"] for r in a] == [r["shocks"] for r in b]
    assert [r["shocks"] for r in a] != [r["shocks"] for r in c]  # restarts depend on the seed


def test_optimizer_marginal_limits_are_constraints():
    spec = stub_spec()
    eng = toy_engine(spec)
    lim = {f: (-4.0, 1.8) for f in FACTOR_ORDER}  # upper z limit 1.8 would be violated by the unconstrained tail point
    free = optimizer_search(eng, spec, budget=48, seed=0, target_usd=TARGET, tail_d2=TAIL_D2)
    con = optimizer_search(eng, spec, budget=48, seed=0, target_usd=TARGET, tail_d2=TAIL_D2, z_limits=lim)
    zmax_free = max(max(r["engine"]["z"].values()) for r in free if r["breach"])
    ok = [r for r in con if r["breach"]]
    assert ok
    inside = [r for r in ok if max(r["engine"]["z"].values()) <= 1.8 + 0.1]
    assert inside, "with z limits the optimizer should return breaches whose factors respect the limits"
    assert zmax_free > 1.9


def test_optimizer_handles_the_temperature_limit_by_a_load_cap():
    spec = stub_spec()
    cap = 1.05  # the unconstrained tail point has a load ratio around 1.08
    eng = toy_engine(spec, l_cap=cap)
    free = optimizer_search(toy_engine(spec), spec, budget=48, seed=0, target_usd=TARGET, tail_d2=TAIL_D2)
    recs = optimizer_search(eng, spec, budget=48, seed=0, target_usd=TARGET, tail_d2=TAIL_D2)
    assert max(r["shocks"]["load_peak_ratio"] for r in free if r["breach"]) > cap
    ok = [r for r in recs if r["breach"]]
    assert ok and all(r["shocks"]["load_peak_ratio"] <= cap for r in ok)
    # once the limit is hit the search backs off: late points are mostly feasible, not stuck above the limit
    late = recs[len(recs) // 2:]
    assert np.mean([r["shocks"]["load_peak_ratio"] <= cap for r in late]) > 0.5


def test_optimizer_legacy_mode_and_small_budget_still_work():
    spec, eng = stub_spec(), stub_engine_fn()
    legacy = optimizer_search(eng, spec, budget=24, seed=0, warm_start=False)
    assert 0 < len(legacy) <= 24
    assert 1 <= len(optimizer_search(eng, spec, budget=2, seed=0)) <= 2


def test_equal_budget_for_all_arms_on_the_stub():
    spec, eng = stub_spec(), stub_engine_fn()
    n = {
        "random": len(random_search(eng, spec, budget=40, seed=0)),
        "optimizer": len(optimizer_search(eng, spec, budget=40, seed=0, target_usd=TARGET)),
        "cond": len(cond_gaussian_search(eng, spec, budget=40, seed=0, target_usd=TARGET)),
    }
    assert n["random"] == 40 and n["cond"] == 40 and 30 <= n["optimizer"] <= 40


# ---------------------------------------------------------------- sensitivity table

def _records_for_sensitivity():
    # two repeats; repeat 0 has three distinct breaches (z 0, 0.8, 3 apart on the first axis), repeat 1 none
    def r(zx, d2, loss=6e6):
        return {"season": "winter", "driver_class": "cold_snap", "rules_failed": [], "loss_usd": loss,
                "engine": {"pnl_total": -loss, "pnl_by_channel": {"zone_volume": -loss}, "pnl_by_position": {"P5": -loss},
                           "q": 0.5, "d2": d2, "severity": "adverse", "z": dict(zip(FACTOR_ORDER, [zx, 0, 0, 0, 0])),
                           "hard_rule_failures": []}}
    rep0 = [r(0.0, 200.0), r(0.8, 150.0), r(3.0, 120.0)]
    rep1 = [r(0.0, 1.0, loss=1e6)]
    return {"cond_gaussian": [rep0, rep1]}


def test_sensitivity_table_shape_and_monotone_in_tau():
    windows = {5: np.array([10.0, 20.0, 30.0, 40.0] * 10), 10: np.arange(1.0, 101.0), 14: np.arange(1.0, 51.0)}
    tab = metrics.sensitivity_table(_records_for_sensitivity(), windows, target_usd=TARGET)
    assert list(tab.columns) == list(metrics.SENSITIVITY_COLUMNS)
    assert len(tab) == 1 * 3 * 3  # arms x window lengths x taus
    assert set(tab["window_days"]) == {5, 10, 14} and set(tab["tau"]) == {0.5, 1.0, 2.0}
    for w, g in tab.groupby("window_days"):
        g = g.sort_values("tau")
        assert (np.diff(g["n_breaches_mean"].to_numpy()) <= 1e-12).all()  # a larger tau merges more breaches
    row = tab[(tab.window_days == 10) & (tab.tau == 1.0)].iloc[0]
    # window 10: q = share of windows with D^2 >= d2: 200 -> 0, 150 -> 0, 120 -> 0 (all above the 100 windows)
    assert row["n_breaches_mean"] == pytest.approx((2 + 0) / 2)  # z 0 and 0.8 merge at tau 1; z 3 is separate
    assert row["repeats_with_breach"] == 1 and row["weakest_q_max"] == 0.0
    assert row["n_repeats"] == 2


def test_sensitivity_window_length_changes_q_and_can_remove_breaches():
    rec = _records_for_sensitivity()
    # the short-window history has many windows at D^2 above 120, so the same scenario is no longer in the tail
    heavy = {5: np.full(100, 500.0), 10: np.arange(1.0, 101.0), 14: np.arange(1.0, 51.0)}
    tab = metrics.sensitivity_table(rec, heavy, target_usd=TARGET)
    assert tab[(tab.window_days == 5)]["n_breaches_mean"].max() == 0.0
    assert np.isnan(tab[(tab.window_days == 5)]["weakest_q_mean"]).all()
    assert tab[(tab.window_days == 10)]["n_breaches_mean"].max() > 0
    # requantile follows the model's definition q = mean(windows >= d2)
    out = metrics.requantile(rec["cond_gaussian"][0], np.array([100.0, 130.0, 160.0, 400.0]))
    assert out[0]["engine"]["q"] == 0.25 and out[1]["engine"]["q"] == 0.5 and out[2]["engine"]["q"] == 0.75


def test_window_d2_by_length_uses_model_history():
    dates = pd.date_range("2022-01-01", periods=28, freq="D")
    d2 = np.arange(28.0)
    model = type("M", (), {"history": pd.DataFrame({"date": dates, "d2": d2})})()
    w = dg.window_d2_by_length(model, (5, 10, 14))
    assert set(w) == {5, 10, 14}
    assert list(w[14]) == [13.0, 27.0] and list(w[10]) == [9.0, 19.0] and list(w[5]) == [4.0, 9.0, 14.0, 19.0, 24.0]


# ---------------------------------------------------------------- production book sizes: sums and identities

def test_production_sizes_sum_and_identities():
    from revstress.book import BookParams, pnl

    sz = config.POSITION_SIZES_MW
    assert tuple(sz) == config.POSITIONS and all(v > 0 for v in sz.values())
    assert sz == {"P1": 100.0, "P2": 25.0, "P3": 50.0, "P4": 50.0, "P5": 140.0, "P6": 25.0}  # selected by the scan
    assert sum(sz.values()) == 390.0
    assert 0.0 < sz["P2"] / sz["P5"] < 1.0  # the congestion hedge covers part of the retail obligation, not all of it
    assert config.LOSS_TARGET_USD == 5e6 and config.LOSS_TARGET_USD / config.ALLOCATED_CAPITAL_USD == pytest.approx(0.25)
    assert BookParams(k1_usd=1, c0_usd=1, k6_usd=1, r_usd=1, h_usd=1, l_normal_mw=1).sizes_mw == sz  # default book = config


def test_book_pnl_identities_at_production_sizes(panel, params):
    from dataclasses import replace

    from revstress.book import pnl

    prod = replace(params, sizes_mw=dict(config.POSITION_SIZES_MW))
    r = pnl(panel.iloc[[0]], prod, fallback=False).iloc[0]  # a flat weekday: wh 100/60, dom 110/70, load = normal
    wh24, dom24 = (16 * 100 + 8 * 60) / 24, (16 * 110 + 8 * 70) / 24
    assert r["P1"] == pytest.approx(16 * 100 * (100 - 90))
    assert r["P2"] == pytest.approx(24 * 25 * ((dom24 - wh24) - 8.0))
    assert r["P3"] == pytest.approx(8 * 50 * (65 - 60))
    assert r["P5"] == pytest.approx(24 * 140 * ((80 - dom24) + (wh24 - 75)))
    assert r["total"] == pytest.approx(sum(r[p] for p in config.POSITIONS))
    assert r["total"] == pytest.approx(sum(r[c] for c in config.CHANNELS))
    # linearity in size: doubling every position doubles every P&L column
    dbl = pnl(panel.iloc[[0]], replace(prod, sizes_mw={k: 2 * v for k, v in prod.sizes_mw.items()}), fallback=False).iloc[0]
    assert all(dbl[c] == pytest.approx(2 * r[c]) for c in config.POSITIONS + config.CHANNELS + ("total",))


def test_sizing_check_quotes_the_actual_target_and_production_book_is_in_range():
    from pathlib import Path

    from revstress import pipeline_real as pr
    from revstress.book import fit_book_params

    real = Path(pr.DATA_ROOT) / "processed" / pr.PANEL_FILE
    if not real.exists():
        pytest.skip("processed NYISO panel not present")
    with pr.nyiso_market():
        _, fit = pr.load_real_panel()
        s = dg.sizing_check(fit, fit_book_params(fit))
    assert s["target_usd"] == 5e6 and "5M" in s["rule"] and "7M" not in s["rule"]
    assert 0.5 <= s["worst_30d_loss_over_target"] <= 1.0 and s["keep_sizes"]  # condition (d) of the selection rule


# ---------------------------------------------------------------- multi-channel rule v2
def _st(min_b=6, share=0.5, w=0.7):
    return {"min_breaches": min_b, "share": share, "worst_30d_ratio": w}


def test_v2_conditions_need_two_channels_two_seasons_and_no_dominant_channel():
    ok = {"channel_counts": {"zone_volume": 4, "system": 3}, "season_counts": {"winter": 4, "summer": 3}, "max_channel_share": 4 / 7}
    assert sizing.failed_conditions_v2(_st(), ok) == []
    one = {"channel_counts": {"zone_volume": 19}, "season_counts": {"winter": 19}, "max_channel_share": 1.0}
    assert sizing.failed_conditions_v2(_st(), one) == ["c2"]
    assert sizing.failed_conditions_v2(_st(min_b=4, share=1.1, w=1.4), one) == ["a", "b", "c2", "d"]
    thin = {"channel_counts": {"zone_volume": 9, "system": 2}, "season_counts": {"winter": 9, "summer": 2}, "max_channel_share": 9 / 11}
    assert "c2" in sizing.failed_conditions_v2(_st(), thin)


def test_v2_selection_prefers_admissible_and_never_relaxes():
    good = {"channel_counts": {"zone_volume": 4, "system": 3}, "season_counts": {"winter": 4, "summer": 3}, "max_channel_share": 0.57}
    bad = {"channel_counts": {"zone_volume": 19}, "season_counts": {"winter": 19}, "max_channel_share": 1.0}
    c = [{"sizes": {"P1": 1}, "stats": _st(9), "mix": bad}, {"sizes": {"P1": 2}, "stats": _st(6), "mix": good}]
    assert sizing.select_candidate_v2(c) == (1, [])
    i, f = sizing.select_candidate_v2([c[0]])
    assert (i, f) == (0, ["c2"])
    assert sizing.select_candidate_v2([]) == (None, ["no_candidate"])


def test_fit_book_params_sets_fair_value_premiums(panel):
    from revstress.book import fit_book_params

    p = fit_book_params(panel)
    assert p.p4_premium_usd > 0 and p.p6_premium_usd >= 0
