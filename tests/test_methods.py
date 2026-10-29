"""Tests for the conditional-Gaussian baseline, loop diagnostics (stated-vs-implied, gate stats, dispersion),
the severity-anchoring ablation and the run manifest. Stubs and FakeClient only; no network."""

import json

import numpy as np
import pytest

from revstress import config, manifest
from revstress.agent import client as cl
from revstress.agent import prompts
from revstress.agent.loop import run_loop, run_target_ablation
from revstress.baselines import cond_gaussian_search, random_search
from revstress.eval import metrics
from stub_engine import stub_engine_fn, stub_spec

RECORD_KEYS = {
    "scenario_id", "arm", "seed", "iteration", "driver_class", "season", "horizon_days", "narrative", "shocks",
    "analogue", "confidence", "engine", "loss_usd", "rules_failed", "rules_passed", "breach",
}
TARGET = 2e6


# ------------------------------------------------------------------ conditional Gaussian


def test_cond_gaussian_budget_schema_determinism():
    spec, eng = stub_spec(), stub_engine_fn()
    a = cond_gaussian_search(eng, spec, budget=30, seed=1, target_usd=TARGET)
    b = cond_gaussian_search(eng, spec, budget=30, seed=1, target_usd=TARGET)
    c = cond_gaussian_search(eng, spec, budget=30, seed=2, target_usd=TARGET)
    assert len(a) == 30 and all(set(r) == RECORD_KEYS and r["arm"] == "cond_gaussian" for r in a)
    assert [r["shocks"] for r in a] == [r["shocks"] for r in b]
    assert [r["shocks"] for r in a] != [r["shocks"] for r in c]
    assert all(r["narrative"] for r in a) and all(r["loss_usd"] == -r["engine"]["pnl_total"] for r in a)


def test_cond_gaussian_hits_target_with_small_d2():
    spec, eng = stub_spec(), stub_engine_fn()
    recs = cond_gaussian_search(eng, spec, budget=40, seed=3, target_usd=TARGET)
    feas = [r for r in recs if r["loss_usd"] >= TARGET]
    assert feas
    near = [r for r in feas if r["loss_usd"] <= 1.1 * TARGET]
    assert near, "the Newton correction should land just above the target"
    best = min(r["engine"]["d2"] for r in feas)
    rnd = random_search(eng, spec, budget=40, seed=3, target_usd=TARGET)
    rnd_feas = [r["engine"]["d2"] for r in rnd if r["loss_usd"] >= TARGET]
    assert not rnd_feas or best <= min(rnd_feas)
    # linearised hyperplane bound: D2 >= (target - L0)^2 / (g' Sigma g) up to nonlinearity (loss is convex in l)
    assert 0 < best < 200


def test_cond_gaussian_base_point_already_breaching_and_zero_gradient():
    spec = stub_spec()
    base = stub_engine_fn()

    def always_loses(shock):
        out = base(shock)
        out["pnl_total"] = -1e7
        return out

    recs = cond_gaussian_search(always_loses, spec, budget=12, seed=0, target_usd=5e6)
    assert 0 < len(recs) <= 12 and recs[0]["loss_usd"] == 1e7  # flat loss: zero gradient, no hang


def test_cond_gaussian_tiny_budget_and_engine_error():
    spec = stub_spec()
    assert len(cond_gaussian_search(stub_engine_fn(), spec, budget=3, seed=0, target_usd=TARGET)) == 3

    def broken(shock):
        raise ValueError("bad shock")

    recs = cond_gaussian_search(broken, spec, budget=8, seed=0)
    assert recs and all(r["engine"] is None and not r["breach"] for r in recs)


# ------------------------------------------------------------------ stated vs implied


def test_stated_vs_implied_hand_values():
    recs = [
        {"prompt_version": "v3", "stated_loss_usd": 4e6, "loss_usd": 5e6},  # -20%
        {"prompt_version": "v3", "stated_loss_usd": 7.5e6, "loss_usd": 5e6},  # +50%
        {"prompt_version": "v3", "stated_loss_usd": None, "loss_usd": 5e6},
        {"prompt_version": "v2", "scenario": {"stated_loss_usd": 10e6}, "loss_usd": 5e6},  # +100%
        {"prompt_version": "v2", "scenario": {}, "loss_usd": None},
    ]
    df = metrics.stated_vs_implied(recs)
    v3, v2 = df.loc["v3"], df.loc["v2"]
    assert v3["n"] == 3 and v3["n_stated"] == 2 and v3["n_scored"] == 2
    assert v3["abs_err_mean"] == pytest.approx(1.75e6) and v3["abs_err_median"] == pytest.approx(1.75e6)
    assert v3["rel_abs_median"] == pytest.approx(0.35) and v3["rel_err_median"] == pytest.approx(0.15)
    assert v3["share_within_20pct"] == pytest.approx(0.5)
    assert v2["n_scored"] == 1 and v2["rel_abs_median"] == pytest.approx(1.0) and v2["share_within_20pct"] == 0.0


def test_stated_vs_implied_empty_group_is_nan():
    df = metrics.stated_vs_implied([{"prompt_version": "v1", "loss_usd": 1e6}])
    assert df.loc["v1", "n_scored"] == 0 and np.isnan(df.loc["v1", "abs_err_mean"])


# ------------------------------------------------------------------ gate stats and dispersion


def _hv(rule, passed):
    return {"rule": rule, "passed": passed, "hard": True}


def _sv(rule, passed, pen):
    return {"rule": rule, "passed": passed, "hard": False, "penalty": pen}


def test_gate_rejection_stats_counts_and_rates():
    recs = [
        {"accepted": False, "hard_verdicts": [_hv("a", False), _hv("b", True)], "schema_errors": [], "engine_error": None},
        {"accepted": False, "hard_verdicts": [_hv("a", False), _hv("b", False)], "schema_errors": ["x"], "engine_error": None},
        {"accepted": False, "hard_verdicts": [_hv("a", True)], "schema_errors": [], "engine_error": "ValueError: bad"},
        {"accepted": True, "hard_verdicts": [_hv("a", True)], "schema_errors": [], "engine_error": None, "penalty": 1.0,
         "soft_verdicts": [_sv("narrative_length", False, 1.0), _sv("q_not_too_small", True, 0.0)]},
    ]
    g = metrics.gate_rejection_stats(recs)
    assert (g["n_scenarios"], g["n_accepted"], g["n_rejected"]) == (4, 1, 3) and g["rejection_rate"] == 0.75
    assert g["hard"]["a"] == {"count": 2, "rate": 0.5} and g["hard"]["b"]["count"] == 1
    assert g["hard"]["schema"]["count"] == 1 and g["hard"]["engine_error"]["count"] == 1
    assert g["soft"] == {"narrative_length": {"count": 1, "rate": 1.0, "penalty_sum": 1.0}}
    assert g["mean_penalty"] == 1.0
    assert np.isnan(metrics.gate_rejection_stats([])["rejection_rate"])


def test_repeat_dispersion_matches_run_metrics():
    spec, eng = stub_spec(), stub_engine_fn()
    reps = [random_search(eng, spec, budget=60, seed=s, sigma_mult=3.0, target_usd=5e5) for s in range(4)]
    df = metrics.repeat_dispersion(reps, target_usd=5e5)
    counts = [metrics.run_metrics(r, target_usd=5e5)["n_breaches"] for r in reps]
    assert list(df.index) == list(metrics.DISPERSION_METRICS)
    assert df.loc["n_breaches", "sd"] == pytest.approx(np.std(counts, ddof=1))
    assert df.loc["n_breaches", "min"] == min(counts) and df.loc["n_breaches", "max"] == max(counts)
    one = metrics.repeat_dispersion(reps[:1], target_usd=5e5)
    assert np.isnan(one.loc["n_breaches", "sd"])


# ------------------------------------------------------------------ prompts flag, loop, ablation


def nyiso_engine(shock):
    """Made-up engine on ENGINE keys (NYISO agent keys already translated): loss grows with gas and spike days."""
    assert "dc_load_shock_mw" in shock and "large_load_shock_mw" not in shock
    loss = 1e5 * shock["gas_hh_pct"] / 10.0 + 2e5 * shock["spike_days"] + 3e6 * (shock["load_peak_ratio"] - 1.0)
    return {
        "pnl_total": -loss, "pnl_by_position": {}, "pnl_by_channel": {"gas": -loss}, "d2": 6.0, "q": 0.02,
        "marginals": {}, "z": {"g": loss / 1e6, "l": 0.0, "s": 0.0, "c": 0.0, "d": 0.0}, "nearest_date": "2022-12-23",
        "severity": "adverse", "spike_exceedance": 0.0,
    }


def test_prompt_flag_removes_target_and_default_unchanged():
    for market in (None, "NYISO"):
        default = prompts.build_seed_prompt("v3", {}, "cold_snap", "winter", market=market)
        on = prompts.build_seed_prompt("v3", {}, "cold_snap", "winter", market=market, include_loss_target=True)
        off = prompts.build_seed_prompt("v3", {}, "cold_snap", "winter", market=market, include_loss_target=False)
        assert default == on and on != off
        tgt = f"{config.LOSS_TARGET_USD:,.0f}"
        assert tgt in on[1][0]["content"] and tgt not in off[1][0]["content"]
        assert "loss target" not in off[1][0]["content"]
    fb = [{"scenario_id": "S-1", "verdicts": [], "engine": None, "loss_usd": 1.0}]
    f_on = prompts.build_feedback_message(fb, 3, True, 2, 5e6)
    f_off = prompts.build_feedback_message(fb, 3, True, 2, 5e6, include_loss_target=False)
    assert "5,000,000" in f_on and "breaching scenarios found so far" in f_on
    assert "5,000,000" not in f_off and "breaching" not in f_off


def test_run_loop_records_and_summary_gate_stats(tmp_path):
    log = tmp_path / "a.jsonl"
    res = run_loop(cl.FakeClient(market="NYISO"), nyiso_engine, ["cold_snap"], iterations=2, log_path=log,
                   market="NYISO", early_stop_breaches=99, tau=0.0)
    assert len(res.scenario_records) == 6
    r0 = res.scenario_records[0]
    assert r0["prompt_version"] == "v3" and r0["stated_loss_usd"] == config.LOSS_TARGET_USD
    summary = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()][-1]
    assert summary["event"] == "summary" and summary["gate_stats"]["n_scenarios"] == 6
    assert summary["gate_stats"] == json.loads(json.dumps(res.gate_stats()))
    sv = metrics.stated_vs_implied(res.scenario_records)
    assert sv.loc["v3", "n_scored"] == 6
    recs = metrics.records_from_loop(res.scenario_records)
    assert len(recs) == 6 and recs[0]["driver_class"] == "cold_snap"
    assert metrics.run_metrics(recs)["rule_pass_share"] == 1.0


def test_target_ablation_identical_seeds_and_report(tmp_path):
    made = []

    def factory():
        c = cl.FakeClient(market="NYISO")
        made.append(c)
        return c

    arms = run_target_ablation(
        factory, nyiso_engine, ["cold_snap", "heat_wave"], log_dir=tmp_path, run_id="abl", iterations=2,
        market="NYISO", early_stop_breaches=99, tau=0.0,
    )
    assert len(made) == 2 and set(arms) == {"with_target", "without_target"}
    logs = {a: [json.loads(x) for x in (tmp_path / f"abl_{a}.jsonl").read_text(encoding="utf-8").splitlines()] for a in arms}
    for a, flag in (("with_target", True), ("without_target", False)):
        calls = [r for r in logs[a] if r["event"] == "call"]
        assert all(r["include_loss_target"] is flag for r in calls)
        assert (f"{config.LOSS_TARGET_USD:,.0f}" in calls[0]["messages_in"][0]["content"]) is flag
        assert logs[a][-1]["include_loss_target"] is flag
    drivers = {a: [r["driver_class"] for r in logs[a] if r["event"] == "call"] for a in arms}
    assert drivers["with_target"] == drivers["without_target"]
    rep = metrics.target_anchoring_report({a: r.scenario_records for a, r in arms.items()}, target_usd=config.LOSS_TARGET_USD)
    assert set(rep.index) == {"with_target", "without_target"} and (rep["n_scenarios"] == 12).all()
    assert (rep["share_within_tol"].between(0, 1)).all() and (rep["loss_p10"] <= rep["loss_p90"]).all()
    assert all("FAKE CLIENT - not Claude results" in s["scenario"]["narrative"] for r in arms.values() for s in r.scenario_records)


def test_target_anchoring_report_hand_values():
    recs = [{"loss_usd": v} for v in (3.9e6, 4.0e6, 5.0e6, 6.0e6, 6.1e6)] + [{"loss_usd": None, "breach": False}]
    rep = metrics.target_anchoring_report({"x": recs}, target_usd=5e6)
    row = rep.loc["x"]
    assert row["n_scenarios"] == 6 and row["n_engine"] == 5
    assert row["share_within_tol"] == pytest.approx(3 / 5)  # 4.0, 5.0, 6.0 inside +-20%
    assert row["share_above_target"] == pytest.approx(3 / 5) and row["loss_median"] == 5e6


# ------------------------------------------------------------------ manifest


def _make_data(root):
    raw = root / "raw" / "nyiso_prices"
    raw.mkdir(parents=True)
    (raw / "a.zip").write_bytes(b"alpha")
    (raw / "MANIFEST.json").write_text(
        json.dumps({"files": {"nyiso_prices/a.zip": {"sha256": manifest.hashlib.sha256(b"alpha").hexdigest(),
                                                   "downloaded_utc": "2026-01-01T00:00:00Z"}}}), encoding="utf-8")
    proc = root / "processed"
    proc.mkdir()
    (proc / "panel.csv").write_bytes(b"date,wh_on\n2019-01-01,1\n")
    (proc / "x_manifest.json").write_text(
        json.dumps({"label": "REAL DATA test", "built_utc": "2026-01-02T00:00:00Z",
                    "panel": {"file": "panel.csv", "sha256": manifest.sha256_file(proc / "panel.csv"),
                              "date_min": "2019-01-01", "date_max": "2019-01-01"}}), encoding="utf-8")


def test_write_and_verify_manifest(tmp_path):
    root = tmp_path / "data"
    _make_data(root)
    system, messages = prompts.build_seed_prompt("v3", {}, "cold_snap", "winter", market="NYISO")
    path = manifest.write_run_manifest(
        "run1", model="claude-sonnet-5-5", temperature=0.0, seed=7, prompt_version="v3", system=system, messages=messages,
        market="NYISO", label="FAKE CLIENT - not Claude results", data_root=root, outputs_root=tmp_path / "out",
    )
    assert path == tmp_path / "out" / "run1" / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["prompt"] == {"version": "v3", "sha256": prompts.prompt_hash(system, messages)}
    assert m["model"] == {"id": "claude-sonnet-5-5", "temperature": 0.0, "seed": 7}
    assert m["market"]["name"] == "NYISO" and m["market"]["cap_is_assumption"] is True
    assert m["label"] == "FAKE CLIENT - not Claude results"
    assert m["environment"]["numpy"] == np.__version__ and m["environment"]["python"]
    assert m["package"]["version"].startswith("0.1.0+src.")
    assert m["data"]["raw"]["nyiso_prices/a.zip"]["downloaded_utc"] == "2026-01-01T00:00:00Z"
    assert m["data"]["processed"]["panel.csv"]["built_utc"] == "2026-01-02T00:00:00Z"
    assert m["data"]["panel_date_range"] == {"processed/x_manifest.json": ["2019-01-01", "2019-01-01"]}
    ok = manifest.verify_manifest(path, data_root=root)
    assert ok["ok"] and ok["checked"] == 2 and ok["package_ok"] is True
    (root / "processed" / "panel.csv").write_bytes(b"changed")
    bad = manifest.verify_manifest(path, data_root=root)
    assert not bad["ok"] and bad["mismatched"] == ["processed/panel.csv"]
    (root / "raw" / "nyiso_prices" / "a.zip").unlink()
    gone = manifest.verify_manifest(path, data_root=root)
    assert gone["missing"] == ["raw/nyiso_prices/a.zip"]
    assert manifest.verify_manifest(path, data_root=root, check_raw=False)["missing"] == []


def test_manifest_requires_prompt_and_tolerates_missing_data(tmp_path):
    with pytest.raises(ValueError):
        manifest.write_run_manifest("r", model="m", temperature=None, seed=None, prompt_version="v1",
                                    data_root=tmp_path, outputs_root=tmp_path)
    p = manifest.write_run_manifest("r", model="m", temperature=None, seed=None, prompt_version="v1", prompt_hash="abc",
                                    data_root=tmp_path / "none", outputs_root=tmp_path)
    m = json.loads(p.read_text(encoding="utf-8"))
    assert m["data"]["raw"] == {} and m["market"]["name"] == config.MARKET and m["model"]["temperature"] is None


def test_manifest_records_requested_market_and_hashes_hh_file(tmp_path):
    root = tmp_path / "data"
    _make_data(root)
    gas = root / "raw" / "eia_gas_ice"
    gas.mkdir()
    (gas / "hh_daily_2013-12_onward_parsed.csv").write_text("date,hh_usd\n2020-01-01,2\n", encoding="utf-8")
    assert config.MARKET == "PJM"
    path = manifest.write_run_manifest(
        "run2", model="fake-client", temperature=None, seed=0, prompt_version="v3", prompt_hash="abc",
        market="NYISO", label="FAKE CLIENT - not Claude results", data_root=root, outputs_root=tmp_path / "out",
    )
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["config"]["MARKET"] == "NYISO"
    rec = m["data"]["raw"]["eia_gas_ice/hh_daily_2013-12_onward_parsed.csv"]
    assert rec["sha256"] == manifest.sha256_file(gas / "hh_daily_2013-12_onward_parsed.csv") and "eia.gov" in rec["source_url"]
    assert manifest.verify_manifest(path, data_root=root)["ok"]
