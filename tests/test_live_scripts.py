"""Offline coverage of scripts/run_anchoring_live.py and scripts/grade_coherence_llm.py: cost guards and the blind grading flow (stub client, no network)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rec(sid, loss=6e6):
    eo = {"pnl_by_position": {"P5": -loss}, "pnl_by_channel": {"zone_volume": -loss}, "d2": 50.0, "q": 0.02, "severity": "adverse",
          "marginals": {"g": 0.5}, "marginals_exceeded": [], "hard_rule_failures": [], "nearest_date": "2022-12-24"}
    scn = {"scenario_id": sid, "driver_class": "cold_snap", "season": "winter", "confidence": "low", "horizon_days": 5,
           "narrative": "A cold snap raises N.Y.C. load and congestion so the spread between N.Y.C. and WEST widens for five days, hurting the load obligation.",
           "shocks": {"duration_days": 5, "pocket_minus_ref_usd": 100, "load_peak_ratio": 1.1}, "analogue": {}}
    return {"scenario_id": sid, "loss_usd": loss, "stated_loss_usd": loss, "fabricated_analogue": False, "engine_error": None,
            "engine_output": eo, "hard_verdicts": [], "penalty": 0.0, "scenario": scn}


def test_cost_guards_refuse(capsys):
    for name in ("run_anchoring_live", "grade_coherence_llm"):
        mod = load(name)
        argv = sys.argv
        sys.argv = [name] + (["x.jsonl"] if name == "grade_coherence_llm" else [])
        try:
            assert mod.main() == 2
        finally:
            sys.argv = argv
    assert "REFUSED" in capsys.readouterr().err


def test_blind_view_hides_arm_and_loss():
    mod = load("grade_coherence_llm")
    v = mod.view(rec("A"), "B-001")
    assert set(v) == {"blind_id", "driver_class", "season", "narrative", "shocks", "analogue", "confidence"}
    assert "loss_usd" not in json.dumps(v) and "load_peak_ratio" in v["shocks"]


def test_grading_flow_with_stub_client(tmp_path, monkeypatch):
    mod = load("grade_coherence_llm")
    log = tmp_path / "run" / "audit_log.jsonl"
    log.parent.mkdir()
    log.write_text(json.dumps({"model": "m", "client_kind": "live", "scenarios": [rec("A"), rec("B")]}) + "\n", encoding="utf-8")

    class Stub:
        totals = {"input_tokens": 1, "output_tokens": 1}

        def __init__(self, *a, **k):
            pass

        def complete(self, system, messages, version):
            ids = [s["blind_id"] for s in json.loads(messages[0]["content"])]
            body = [{"blind_id": i, "causal_chain": 1, "shocks_explained": 1, "duration_matches": 1,
                     "analogue_correct_relevant": 1, "no_contradiction": 0, "note": "x"} for i in ids]
            return type("R", (), {"text": json.dumps(body), "error": None})()

    monkeypatch.setattr(mod.client_mod, "ClaudeClient", Stub)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(sys, "argv", ["g", str(log), "--i-understand-cost", "--out", str(tmp_path / "o")])
    assert mod.main() == 0
    text = (tmp_path / "o" / "coherence_llm.csv").read_text(encoding="utf-8")
    assert text.count("run:") == 2 and "no_contradiction" in text
