import warnings

import numpy as np
import pandas as pd
import pytest

from revstress import config
from revstress.baselines import optimizer_search, random_search
from revstress.book import fit_book_params
from revstress.eval import analogues, metrics, replay, rubric
from revstress.synthetic import generate_synthetic_panel
from stub_engine import stub_engine_fn, stub_spec


# analogues
def test_lookup_and_scoring():
    row = analogues.lookup("Winter Storm Elliott", "forecast_peak_mw")
    assert row.value == 126968 and row.unit == "MW" and row.source and row.vintage
    assert analogues.score_claim("elliott", "forecast_peak_mw", 126968) == "correct"
    assert analogues.score_claim("elliott", "forecast_peak_mw", 127000) == "correct"
    assert analogues.score_claim("elliott", "forecast_peak_mw", 150000) == "within30"
    assert analogues.score_claim("elliott", "forecast_peak_mw", 50000) == "wrong"
    assert analogues.score_claim("elliott", "no_such_metric", 1) == "not_in_table"
    assert analogues.score_claim("jan2014", "western_hub_price_usd_mwh", 500) == "not_in_table"
    assert analogues.lookup("jan2014", "western_hub_price_usd_mwh").value is None
    assert analogues.score_claim("fake storm", "peak_mw", 1) == "not_in_table"


def test_table_covers_events_and_has_no_missing_labels():
    events = {a.event for a in analogues.ANALOGUES}
    assert events == {"elliott", "jan2014", "jan2025", "jun2025", "datacenter"}
    assert all(a.unit and a.source and a.vintage for a in analogues.ANALOGUES)
    assert len({(a.event, a.metric) for a in analogues.ANALOGUES}) == len(analogues.ANALOGUES)
    assert analogues.lookup("jun2025", "peak_mw_24jun").value < analogues.lookup("jun2025", "record_peak_mw_2006").value


def test_score_analogue_block():
    block = {"event": "Jan 2025", "claimed": {"instantaneous_peak_mw": 145060, "hourly_peak_mw": 100000, "bogus": 1}}
    assert analogues.score_analogue(block) == {"instantaneous_peak_mw": "correct", "hourly_peak_mw": "wrong", "bogus": "not_in_table"}


# replay
@pytest.fixture(scope="module")
def synth():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return generate_synthetic_panel(seed=7, start="2022-01-01", end="2022-12-31", warn=False)


def test_replay_identity_when_event_equals_base(synth):
    params = fit_book_params(synth)
    win = synth.iloc[10:20].reset_index(drop=True)
    res = replay.replay_event(win, win, params, spike_threshold_usd=1e9)
    assert all(abs(v) < 1e-6 for k, v in res.shock.items() if k not in ("duration_days", "load_peak_ratio"))
    assert res.table["gap_usd"].abs().max() < 1.0
    assert {"P1", "P6", "system", "total"} <= set(res.table.index)


def test_replay_stressed_event_reports_gap_by_position(synth):
    params = fit_book_params(synth)
    base = synth.iloc[10:20].reset_index(drop=True)
    ev = base.copy()
    ev["wh_on"] = ev["rt_wh_on"] = base["wh_on"] * 1.5
    ev.loc[3, ["wh_on", "rt_wh_on"]] = 600.0
    ev["dom_on"] = ev["wh_on"] + 10.0
    ev["load_peak_mw"] = base["load_peak_mw"] * 1.1
    res = replay.replay_event(ev, base, params, spike_threshold_usd=500.0)
    assert res.shock["spike_days"] == 1 and res.shock["spike_daily_avg_usd"] == 600.0
    t = res.table
    assert list(t.columns) == ["engine_usd", "actual_usd", "gap_usd", "rel_gap", "within30", "sign_match"]
    assert np.allclose(t["gap_usd"], t["engine_usd"] - t["actual_usd"])
    assert t.loc["P1", "actual_usd"] > 0
    assert set(replay.cold_snap_sign_check(t)) <= {"P1", "P3", "P4", "P5", "P6"}


def test_replay_length_mismatch(synth):
    with pytest.raises(ValueError):
        replay.event_to_shock(synth.iloc[:5], synth.iloc[:6])


# metrics
def _rec(z, loss, q=0.02, driver="cold_snap", channel="system", failed=()):
    marg = dict(zip(config.GAUSSIAN_CORE_FACTORS, 0.5 + 0.0 * np.asarray(z)))
    eng = {"pnl_total": -loss, "q": q, "d2": float(np.sum(np.square(z))), "marginals": marg, "z": dict(zip(config.GAUSSIAN_CORE_FACTORS, z)),
           "pnl_by_channel": {channel: -loss, "tail": 0.0}}
    return {"engine": eng, "driver_class": driver, "rules_failed": list(failed), "rules_passed": not failed}


def test_primary_metric_distinctness_and_filters():
    recs = [
        _rec([2, 0, 0, 0, 0], 6e6),
        _rec([2.2, 0, 0, 0, 0], 6e6),  # within tau of first
        _rec([0, 2, 0, 0, 0], 6e6, driver="gas_supply"),
        _rec([0, 0, 3, 0, 0], 4e6),  # loss too small
        _rec([0, 0, 0, 3, 0], 6e6, q=0.2),  # q too high
        _rec([0, 0, 0, 0, 3], 6e6, failed=["sign_inconsistent"]),
        {"engine": None, "driver_class": "policy", "rules_failed": ["invalid_shock"]},
    ]
    assert metrics.primary_metric(recs, target_usd=5e6, tau=1.0) == 2
    assert metrics.primary_metric(recs, target_usd=5e6, tau=0.1) == 3
    m = metrics.run_metrics(recs, target_usd=5e6, tau=1.0)
    assert m["n_breaches"] == 2 and m["driver_coverage"] == 2 / 7 and m["channel_coverage"] == 1 / 6
    assert abs(m["rule_pass_share"] - 5 / 7) < 1e-12 and m["median_q"] == 0.02


def test_novelty_rescaling_vs_new_combination():
    replay_vecs = {"E1": np.array([1.0, 1.0, 0.0, 0.0, 0.0])}
    scaled = _rec([2.0, 2.0, 0, 0, 0], 6e6)
    new = _rec([2.0, -2.0, 0, 0, 0], 6e6)
    dist, share = metrics.novelty([scaled, new], replay_vecs)
    assert share == 0.5 and dist > 0
    assert np.isnan(metrics.novelty([], replay_vecs)[0])


def test_compare_arms_with_stub_baselines():
    spec, eng = stub_spec(), stub_engine_fn()
    runs = {
        "random": [random_search(eng, spec, budget=24, seed=s) for s in range(3)],
        "optimizer": [optimizer_search(eng, spec, budget=24, seed=s) for s in range(3)],
    }
    table = metrics.compare_arms(runs, coherence={"random": [0.5, 0.6, 0.7]})
    assert list(table.index) == ["random", "optimizer"] and (table["n_repeats"] == 3).all()
    assert abs(table.loc["random", "coherence_mean"] - 0.6) < 1e-12 and np.isnan(table.loc["optimizer", "coherence_mean"])
    assert table.loc["optimizer", "n_breaches_mean"] >= table.loc["random", "n_breaches_mean"]


# rubric
GOOD = {
    "narrative": (
        "A four day cold snap drives peak load well above normal and tightens the supply stack so Western Hub on-peak "
        "prices rise because gas fired units set the price. Gas supply is strained and Henry Hub gas moves up which "
        "lifts heat rate costs. Three spike days follow when reserves are short and the Dominion spread widens."
    ),
    "driver_class": "cold_snap",
    "horizon_days": 30,
    "shocks": {"gas_hh_pct": 40, "load_peak_ratio": 1.1, "wh_onpeak_pct": 20, "dom_minus_wh_usd": 15, "spike_days": 3,
               "spike_daily_avg_usd": 500, "duration_days": 4},
    "analogue": {"event": "elliott", "claimed": {"forecast_peak_mw": 126968}},
}


def test_mechanical_checks_pass_and_fail():
    mech = rubric.mechanical_checks(GOOD)
    assert mech["shocks_explained"] == 1 and mech["duration_matches"] == 1 and mech["causal_chain"] is None
    bad = {**GOOD, "narrative": "Cold snap.", "shocks": {**GOOD["shocks"], "load_peak_ratio": 0.9, "duration_days": 6}}
    m2 = rubric.mechanical_checks(bad)
    assert m2["causal_chain"] == 0 and m2["shocks_explained"] == 0 and m2["no_contradiction"] == 0
    wrong = {**GOOD, "analogue": {"event": "elliott", "claimed": {"forecast_peak_mw": 50000}}}
    assert rubric.mechanical_checks(wrong)["analogue_correct_relevant"] == 0


def test_duration_mismatch_detected():
    s = {**GOOD, "shocks": {**GOOD["shocks"], "duration_days": 9}}
    assert rubric.mechanical_checks(s)["duration_matches"] == 0
    assert rubric.mechanical_checks({**GOOD, "narrative": GOOD["narrative"].replace("four day", "")})["duration_matches"] is None


def test_score_scenario_combines_human():
    r = rubric.score_scenario(GOOD)
    assert not r.complete and r.total is None
    human = {"causal_chain": 1, "analogue_correct_relevant": 1, "no_contradiction": 1, "duration_matches": 1, "shocks_explained": 1}
    r = rubric.score_scenario(GOOD, human)
    assert r.complete and r.total == 1.0
    capped = rubric.score_scenario({**GOOD, "analogue": {"event": "elliott", "claimed": {"forecast_peak_mw": 1}}}, human)
    assert capped.items["analogue_correct_relevant"] == 0 and capped.total == 0.8


def test_cohen_kappa_known_values():
    assert abs(rubric.cohen_kappa([1, 1, 0, 0], [1, 0, 0, 0]) - 0.5) < 1e-12
    assert rubric.cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert rubric.cohen_kappa([1, 1, 1], [1, 1, 1]) == 1.0
    assert rubric.cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == -1.0
    assert rubric.percent_agreement([1, 0, 1, 0], [1, 1, 1, 1]) == 0.5
    with pytest.raises(ValueError):
        rubric.cohen_kappa([1], [1, 0])


def test_rater_agreement_and_blind_order():
    human1 = {i: 1 for i in rubric.ITEMS}
    human2 = {**human1, "causal_chain": 0}
    r1 = [rubric.score_scenario(GOOD, human1)] * 4
    r2 = [rubric.score_scenario(GOOD, human1), rubric.score_scenario(GOOD, human2)] * 2
    out = rubric.rater_agreement(r1, r2)
    assert out["pooled"]["n_scenarios"] == 4 and out["causal_chain"]["agreement"] == 0.5 and out["shocks_explained"]["kappa"] == 1.0
    recs = [{**GOOD, "scenario_id": f"X-{i}", "arm": "agent"} for i in range(6)]
    view, key = rubric.blind_order(recs, seed=1)
    assert all("arm" not in v and "scenario_id" not in v for v in view)
    assert sorted(key.values()) == sorted(r["scenario_id"] for r in recs)
    assert [v["blind_id"] for v in view] == sorted(key)


def test_distinct_breaches_use_z_not_saturated_percentiles():
    # both records sit beyond the historical max of every factor, so their percentiles are all 1.0
    a, b = _rec([5, 5, 5, 5, 5], 6e6), _rec([9, 9, 9, 9, 9], 6e6)
    for r in (a, b):
        r["engine"]["marginals"] = {f: 1.0 for f in config.GAUSSIAN_CORE_FACTORS}
    assert metrics.primary_metric([a, b], target_usd=5e6, tau=1.0) == 2
    no_z = _rec([5, 5, 5, 5, 5], 6e6)
    del no_z["engine"]["z"]
    assert metrics.factor_vector(no_z) is None and metrics.primary_metric([no_z], target_usd=5e6, tau=1.0) == 0


def test_loop_and_metrics_share_vector_and_tau():
    from revstress.agent import loop as loop_mod

    rec = _rec([1, -2, 3, 0.5, 0], 6e6)
    assert loop_mod.factor_vector(rec["engine"], {}) == list(metrics.factor_vector(rec))
    assert loop_mod.DEFAULT_TAU == metrics.DEFAULT_TAU == config.DISTINCT_TAU_Z


def test_is_breaching_excludes_implausible_severity():
    from revstress.eval import metrics as mm

    eng = {"pnl_total": -9e6, "q": 0.001, "severity": "severe", "hard_rule_failures": []}
    assert mm.is_breaching({"engine": eng, "rules_failed": []})
    assert not mm.is_breaching({"engine": {**eng, "severity": "implausible"}, "rules_failed": []})
    assert not mm.is_breaching({"engine": {**eng, "hard_rule_failures": ["r"]}, "rules_failed": []})
    rec = mm.records_from_loop([{"engine_output": {**eng, "severity": "implausible"}, "accepted": True, "breach": True}])[0]
    assert "implausible_severity" in rec["rules_failed"]
