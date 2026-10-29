import numpy as np

from revstress import config
from revstress.baselines import optimizer_search, random_search
from revstress.baselines.common import FactorSpec, SpikeOverlay, classify_driver, default_hard_rules, factors_to_shock
from stub_engine import stub_engine_fn, stub_spec

RECORD_KEYS = {
    "scenario_id", "arm", "seed", "iteration", "driver_class", "season", "horizon_days", "narrative", "shocks",
    "analogue", "confidence", "engine", "loss_usd", "rules_failed", "rules_passed", "breach",
}


def test_factors_to_shock_neutral_and_units():
    s = factors_to_shock(np.zeros(5), 5)
    assert s["gas_hh_pct"] == 0 and s["load_peak_ratio"] == 1.0 and s["duration_days"] == 5
    s2 = factors_to_shock(np.array([np.log(1.5), np.log(1.1), 0.0, 12.0, 0.0]), 4, 1, 400.0)
    assert abs(s2["gas_hh_pct"] - 50.0) < 1e-9 and abs(s2["load_peak_ratio"] - 1.1) < 1e-12
    assert s2["dom_minus_wh_usd"] == 12.0 and set(s2) == set(config.SHOCK_KEYS)


def test_spike_overlay_bounds_and_determinism():
    ov = SpikeOverlay(prob_per_day=0.5)
    draws = [ov.sample(np.random.default_rng(i), 10) for i in range(50)]
    assert all(0 <= n <= 10 for n, _ in draws)
    assert all((a == 0.0) if n == 0 else (ov.threshold_usd <= a <= ov.max_avg_usd) for n, a in draws)
    assert ov.sample(np.random.default_rng(3), 10) == ov.sample(np.random.default_rng(3), 10)


def test_random_search_budget_schema_determinism():
    spec, eng = stub_spec(), stub_engine_fn()
    a = random_search(eng, spec, budget=48, seed=1)
    b = random_search(eng, spec, budget=48, seed=1)
    c = random_search(eng, spec, budget=48, seed=2)
    assert len(a) == 48 and all(set(r) == RECORD_KEYS for r in a)
    assert [r["shocks"] for r in a] == [r["shocks"] for r in b]
    assert [r["shocks"] for r in a] != [r["shocks"] for r in c]
    assert all(r["arm"] == "random" and r["loss_usd"] == -r["engine"]["pnl_total"] for r in a)


def test_optimizer_budget_not_exceeded_and_records():
    spec, eng = stub_spec(), stub_engine_fn()
    calls = []

    def counting(shock):
        calls.append(1)
        return eng(shock)

    recs = optimizer_search(counting, spec, budget=48, seed=1)
    assert 0 < len(recs) <= 48 and len(calls) == len(recs)
    assert all(set(r) == RECORD_KEYS and r["arm"] == "optimizer" and r["narrative"] for r in recs)


def test_optimizer_beats_random_on_d2_of_breaches_in_stub():
    spec, eng = stub_spec(), stub_engine_fn()
    target = 5e6  # stub losses are tuned to this target, not to the calibrated NYISO default
    opt = optimizer_search(eng, spec, budget=48, seed=5, target_usd=target)
    rnd = random_search(eng, spec, budget=48, seed=5, target_usd=target)
    opt_b = [r["engine"]["d2"] for r in opt if r["loss_usd"] is not None and r["loss_usd"] >= target]
    rnd_b = [r["engine"]["d2"] for r in rnd if r["loss_usd"] is not None and r["loss_usd"] >= target]
    assert opt_b, "optimizer should reach the loss target in the stub"
    assert not rnd_b or min(opt_b) <= min(rnd_b)


def test_engine_rejection_is_recorded_not_raised():
    spec = stub_spec()

    def bad(shock):
        raise ValueError("rejected")

    recs = random_search(bad, spec, budget=5, seed=0)
    assert len(recs) == 5 and all(r["engine"] is None and r["rules_failed"] == ["invalid_shock"] and not r["breach"] for r in recs)


def test_rules_and_driver_classes():
    ok = factors_to_shock(np.array([0.0, 0.1, 0.0, 0.0, 0.0]), 5)
    res = {"severity": "adverse"}
    assert classify_driver(ok, "winter") == "cold_snap" and classify_driver(ok, "summer") == "heat_wave"
    assert default_hard_rules(ok, res, {"horizon_days": 30, "driver_class": "cold_snap"}) == []
    assert default_hard_rules(ok, {"severity": "implausible"}, {"horizon_days": 30}) == ["implausible_severity"]
    assert default_hard_rules(ok, res, {"horizon_days": 3}) == ["duration_over_horizon"]
    low = {**ok, "load_peak_ratio": 0.9}
    assert default_hard_rules(low, res, {"horizon_days": 30, "driver_class": "cold_snap"}) == ["sign_inconsistent"]
    cap = {**ok, "spike_days": 1, "spike_daily_avg_usd": 5000.0}
    assert "energy_component_above_cap" in default_hard_rules(cap, res, {"horizon_days": 30})


def test_factor_spec_validates_shape():
    try:
        FactorSpec(mu=np.zeros(3), cov=np.eye(3))
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_baselines_default_to_plan_sampling_law():
    """Regression: plan 8D(b) samples from N(mu, Sigma); the widened law is an explicit sensitivity option."""
    import inspect

    from revstress.baselines import optimizer_search, random_search

    for fn in (random_search, optimizer_search):
        assert inspect.signature(fn).parameters["sigma_mult"].default == 1.0


def test_optimizer_small_budget_still_evaluates():
    from revstress.baselines import optimizer_search
    from stub_engine import stub_engine_fn, stub_spec

    recs = optimizer_search(stub_engine_fn(), stub_spec(), budget=2, seed=0)
    assert 1 <= len(recs) <= 2
