"""Integration tests on the SYNTHETIC panel: no network, no API."""

import json
import socket
import warnings

import pytest

from revstress import config
from revstress.agent import client as client_mod
from revstress.pipeline import ScenarioEngine, records_from_log, run_pipeline


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    warnings.simplefilter("ignore", UserWarning)


def scripted_breach(system, messages):
    """One scenario whose summer congestion spread loses more than 5 USD million over 27 days."""
    sc = client_mod.canned_scenarios("transmission", 0, 1)[0]
    sc["scenario_id"] = "T-breach"
    sc["season"] = "summer"
    sc["shocks"].update(
        gas_hh_pct=0.0, load_peak_ratio=1.0, dc_load_shock_mw=0.0, wh_onpeak_pct=0.0, dom_minus_wh_usd=55.0,
        dart_pct=0.0, spike_days=0, spike_daily_avg_usd=0.0, duration_days=27,
    )
    return json.dumps({"scenarios": [sc]})


# the scripted scenario below is sized for the plan's original starting book; the production sizes in
# config.POSITION_SIZES_MW were re-set for NYISO, so this synthetic integration test pins the original sizes explicitly
ORIGINAL_SIZES_MW = {"P1": 50.0, "P2": 50.0, "P3": 25.0, "P4": 100.0, "P5": 200.0, "P6": 25.0}


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    log = tmp_path_factory.mktemp("out") / "audit.jsonl"
    client = client_mod.FakeClient(responses=[scripted_breach] * 200)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "POSITION_SIZES_MW", dict(ORIGINAL_SIZES_MW))
        return run_pipeline(seed=0, budget=21, client=client, log_path=log, loss_target_usd=5e6), log


def test_equal_engine_budget(result):
    res, _ = result
    assert res.engine_calls["claude"] == res.engine_calls["random"] == res.engine_calls["optimizer"] > 0
    assert set(res.table.index) == {"claude", "random", "optimizer"}
    assert (res.table["data_label"] == "SYNTHETIC").all()


def test_scripted_scenario_is_a_breach(result):
    res, log = result
    assert len(res.loop_result.breaches) >= 1
    top = res.loop_result.breaches[0]
    assert top.scenario["scenario_id"] == "T-breach"
    assert top.loss_usd >= 5e6 and top.engine["q"] < config.Q_ADVERSE_MAX
    recs = records_from_log(log)
    assert any(r["breach"] for r in recs)
    assert res.table.loc["claude", "n_breaches_mean"] >= 1


def test_engine_output_contract(result):
    res, _ = result
    out = res.engine(dict(config.NEUTRAL_SHOCK), season="winter")
    for k in ("pnl_total", "pnl_by_position", "pnl_by_channel", "d2", "q", "marginals", "nearest_date", "severity", "spike_exceedance"):
        assert k in out
    assert set(out["marginals"]) == set(config.GAUSSIAN_CORE_FACTORS)
    assert all(0.0 <= v <= 1.0 for v in out["marginals"].values())
    assert set(out["pnl_by_channel"]) == set(config.CHANNELS)


def test_engine_rejects_invalid_shock(result):
    res, _ = result
    with pytest.raises(ValueError):
        res.engine({**config.NEUTRAL_SHOCK, "duration_days": 99}, season="winter")


def test_fallback_book_has_zero_inactive_positions(result):
    res, _ = result
    eng = ScenarioEngine(res.panel, res.params, res.model, fallback=True)
    out = eng({**config.NEUTRAL_SHOCK, "dom_minus_wh_usd": 50.0, "duration_days": 20}, season="summer")
    assert all(out["pnl_by_position"][p] == 0.0 for p in ("P2", "P3", "P5"))


def test_deterministic(result, tmp_path, monkeypatch):
    res, _ = result
    monkeypatch.setattr(config, "POSITION_SIZES_MW", dict(ORIGINAL_SIZES_MW))
    again = run_pipeline(seed=0, budget=21, client=client_mod.FakeClient(responses=[scripted_breach] * 200), log_path=tmp_path / "a.jsonl", loss_target_usd=5e6)
    assert again.table.drop(columns="data_label").equals(res.table.drop(columns="data_label"))


def test_engine_reports_unsaturated_z(result):
    res, _ = result
    mild = res.engine({**config.NEUTRAL_SHOCK, "gas_hh_pct": 300.0, "duration_days": 10}, season="winter")
    wild = res.engine({**config.NEUTRAL_SHOCK, "gas_hh_pct": 900.0, "duration_days": 10}, season="winter")
    assert set(mild["z"]) == set(config.GAUSSIAN_CORE_FACTORS)
    assert mild["marginals"]["g"] == wild["marginals"]["g"] == 1.0  # percentiles saturate beyond history
    assert wild["z"]["g"] > mild["z"]["g"] > 0.0  # z keeps ordering


def test_weather_shock_moves_degree_days_and_enables_weather_rule(result):
    """Regression: apply_shock left hdd/cdd at base values, so T never responded and the weather rule was dead."""
    from revstress.risk import score_scenario

    res, _ = result
    calm, _ = res.engine.path({**config.NEUTRAL_SHOCK, "duration_days": 10}, "winter")
    cold, _ = res.engine.path({**config.NEUTRAL_SHOCK, "load_peak_ratio": 1.12, "duration_days": 10}, "winter")
    assert (cold["hdd"].iloc[:10] > calm["hdd"].iloc[:10]).all() and (cold["hdd"].iloc[10:] == calm["hdd"].iloc[10:]).all()
    assert score_scenario(cold, res.model)["hard_rule_failures"] == []
    odd, _ = res.engine.path({**config.NEUTRAL_SHOCK, "load_peak_ratio": 1.12, "dc_load_shock_mw": -30000.0, "duration_days": 10}, "winter")
    assert "extreme_weather_with_falling_load_winter" in score_scenario(odd, res.model)["hard_rule_failures"]


def test_protocol_matches_plan(result):
    """Regression: plan sections 5 and 8D: 4 seeds (one per family), 12 iterations, per-seed equal budgets, >= 5 repeats."""
    import inspect

    from revstress.pipeline import protocol_iterations

    res, _ = result
    assert config.N_SEEDS == 4 and len(config.SEED_FAMILIES) >= config.N_SEEDS and config.N_REPEATS >= 5
    assert inspect.signature(run_pipeline).parameters["n_repeats"].default == config.N_REPEATS
    assert protocol_iterations(144) == protocol_iterations(10**6) == config.ITERATIONS_PER_SEED == 12
    assert protocol_iterations(21) == 1
    assert (res.table["n_repeats"] == config.N_REPEATS).all()
    assert all(len(res.repeats[a]) == config.N_REPEATS for a in res.repeats)
    for rep in range(config.N_REPEATS):
        claude = res.repeats["claude"][rep]
        assert {r["seed"] for r in claude} <= set(range(config.N_SEEDS))
        assert {r["driver_class"] for r in claude if r["seed"] == 0} <= set(config.DRIVER_CLASSES)
        for season in config.SEASONS:
            n_claude = sum(1 for r in claude if r["engine"] is not None and config.SEED_FAMILIES[r["seed"]][1] == season)
            assert sum(1 for r in res.repeats["random"][rep] if r["season"] == season) == n_claude
    for arm in ("random", "optimizer"):
        assert [len(x) for x in res.repeats[arm]] == [len(x) for x in res.repeats["claude"]]


def test_engine_pnl_is_shock_attributable(result):
    res, _ = result
    eng = res.engine
    zero = eng({}, season="summer")
    assert abs(zero["pnl_total"]) < 1e-6 and abs(zero["pnl_by_position"]["P5"]) < 1e-6
    assert zero["pnl_total_raw"] == pytest.approx(zero["pnl_base_total"])
    out = eng({"dom_minus_wh_usd": 55.0, "duration_days": 27}, season="summer")
    assert out["pnl_total"] == pytest.approx(out["pnl_total_raw"] - out["pnl_base_total"])
    assert sum(out["pnl_by_position"].values()) == pytest.approx(out["pnl_total"])


def test_base_windows_carry_seasonal_normal_load(result):
    res, _ = result
    for w in res.engine.base.values():
        assert "load_normal_mw" in w.columns
        months = w["date"].dt.month
        for m in months.unique():
            assert w.loc[months == m, "load_normal_mw"].iloc[0] == pytest.approx(res.model.price_model.load_normal_mw_by_month[int(m)])


def test_implausible_scenario_is_not_a_loop_breach():
    from revstress.agent import loop as loop_mod

    def engine(shock, season=None):
        return {"pnl_total": -9e6, "q": 0.001, "severity": "implausible", "hard_rule_failures": ["x"], "d2": 1.0,
                "pnl_by_position": {}, "pnl_by_channel": {}, "marginals": {}, "nearest_date": None}

    engine.takes_season = True
    sc = json.loads(scripted_breach("", []))["scenarios"][0]
    srec, _, breach = loop_mod._evaluate(sc, engine, None, {}, [], (lambda a, b: 9.0), 1.0,
                                         config.LOSS_TARGET_USD, config.Q_ADVERSE_MAX, 0, 0)
    assert breach is None and srec["breach"] is False


def test_loop_log_rows_carry_client_kind(result):
    _, log = result
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    calls = [r for r in rows if r.get("event") == "call"]
    assert calls and all(r["client_kind"] == "fake" and "FAKE CLIENT" in r["label"] and r["model"] == "fake-client" for r in calls)
    assert [r for r in rows if r.get("event") == "summary"][-1]["client_kind"] == "fake"
