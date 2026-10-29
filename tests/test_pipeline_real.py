"""Tests for pipeline_real and run_nyiso_demo on a small SYNTHETIC NYISO-scale panel (hand-made, no data files, no network).

The synthetic panel stands in for the real one only to test wiring; nothing computed here is a result.
"""

import json
import socket
import sys
import warnings
from pathlib import Path

import pytest

from revstress import config
from revstress.agent import client as client_mod
from revstress.pipeline_real import ARMS, FAKE_LABEL, gate_table, nyiso_market, run_real_pipeline
from revstress.synthetic import generate_synthetic_panel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_nyiso_demo as demo  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    warnings.simplefilter("ignore", UserWarning)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = generate_synthetic_panel(1, start="2020-01-01", end="2023-12-31", warn=False, market="NYISO")
    return run_real_pipeline(
        seed=0, budget=12, repeats=2, panel=panel, fit_panel=panel, n_boot=5, log_dir=tmp_path_factory.mktemp("logs")
    )


def test_market_restored_and_arms(result):
    assert config.MARKET == "PJM"
    assert set(result.table.index) == set(ARMS)
    assert result.fake and FAKE_LABEL in result.label and "REAL DATA - NYISO" in result.label
    assert (result.table["label"] == result.label).all()


def test_equal_engine_budget(result):
    ec = result.engine_calls
    assert ec["claude"] > 0
    assert ec["random"] == ec["optimizer"] == ec["cond_gaussian"] >= ec["claude"]
    assert (result.table["engine_calls_agent"] == ec["claude"]).all()


def test_baseline_budgets_have_a_floor():
    from revstress.pipeline_real import baseline_budgets

    nominal = config.ITERATIONS_PER_SEED * config.SCENARIOS_PER_CALL
    assert baseline_budgets([6, 40, 0, nominal]) == [nominal, 40, 0, nominal]
    assert baseline_budgets([6, 40], minimum=0) == [6, 40]


def test_nyiso_agent_keys_and_cap_rule(result):
    sc = result.loop_result.scenario_records[0]["scenario"]
    assert "ref_onpeak_pct" in sc["shocks"] and "stated_loss_usd" in sc
    assert FAKE_LABEL in sc["narrative"]


def test_ablation_plumbing(result):
    assert set(result.ablation_runs) == {"anchor_with_target", "anchor_without_target", "prompt_v1", "prompt_v2", "prompt_v3"}
    assert list(result.prompt_versions.index) == ["v1", "v2", "v3"]
    assert set(result.anchoring.index) == {"with_target", "without_target"}
    assert result.stated_vs_implied is not None and len(result.stated_vs_implied) >= 1
    off = result.ablation_runs["anchor_without_target"]
    assert off.include_loss_target is False


def test_gate_table_flattens(result):
    t = gate_table(result.gate, result.label)
    assert {"overall"} <= set(t["kind"]) and (t["label"] == result.label).all()
    assert "claude_rep0" in set(t["run"]) and "prompt_v1" in set(t["run"])


def test_write_outputs_are_stamped(result, tmp_path):
    out = tmp_path / "nyiso_demo"
    args = demo.argparse.Namespace(seed=0, fallback_book=False, dry_run=False)
    paths = demo.write_outputs(result, out, args, budget=12, repeats=2)
    for key in ("scenarios", "comparison", "gate", "waterfall", "notice", "manifest", "anchoring", "prompt_versions", "stated_vs_implied", "dispersion"):
        assert paths[key].exists(), key
    first = json.loads(paths["scenarios"].read_text(encoding="utf-8").splitlines()[0])
    assert FAKE_LABEL in first["label"]
    for key in ("comparison", "gate", "anchoring", "prompt_versions"):
        assert FAKE_LABEL in paths[key].read_text(encoding="utf-8").splitlines()[1]
    man = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert FAKE_LABEL in man["label"] and man["market"]["name"] == "NYISO" and man["market"]["cap_is_assumption"] is True
    assert FAKE_LABEL in paths["notice"].read_text(encoding="utf-8")


def test_live_guard():
    assert demo.check_live_guard(False, False, {}) is None
    assert demo.check_live_guard(True, True, {}) == demo.LIVE_REFUSAL_KEY
    assert demo.check_live_guard(True, False, {"ANTHROPIC_API_KEY": "x"}) == demo.LIVE_REFUSAL_COST
    assert demo.check_live_guard(True, True, {"ANTHROPIC_API_KEY": "x"}) is None


def test_live_flag_refuses_without_key_or_confirmation(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(demo, "run_real_pipeline", lambda *a, **k: called.append(1))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert demo.main(["--live", "--i-understand-cost", "--env-file", "no_such_file.env"]) == 2
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    assert demo.main(["--live", "--env-file", "no_such_file.env"]) == 2
    assert not called
    assert "REFUSED" in capsys.readouterr().err


def test_nyiso_market_context_manager_restores():
    with nyiso_market():
        assert config.MARKET == "NYISO"
    assert config.MARKET == "PJM"
    with pytest.raises(RuntimeError):
        with nyiso_market():
            raise RuntimeError
    assert config.MARKET == "PJM"


def test_default_client_is_fake():
    assert client_mod.FakeClient(market="NYISO").cache_kind == "fake"
