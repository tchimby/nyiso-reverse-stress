"""The ranked-scenario report: eligibility, ordering by D^2, exclusion reasons."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("make_ranked_report", Path(__file__).resolve().parents[1] / "scripts" / "make_ranked_report.py")
mrr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mrr)


def rec(sid, loss, d2, severity="adverse", q=0.02, hard=(), fab=False, engine=True):
    eo = {"pnl_by_position": {"P5": -loss}, "pnl_by_channel": {"zone_volume": -loss}, "d2": d2, "q": q, "severity": severity,
          "marginals": {"g": 0.5}, "marginals_exceeded": ["c"], "hard_rule_failures": list(hard), "nearest_date": "2022-12-24"}
    return {"scenario_id": sid, "loss_usd": loss, "stated_loss_usd": loss, "fabricated_analogue": fab, "engine_error": None,
            "engine_output": eo if engine else None, "hard_verdicts": [{"rule": "sign_consistent", "passed": False}],
            "penalty": 0.0, "scenario": {"driver_class": "cold_snap", "season": "winter", "narrative": "n", "confidence": "low",
                                          "shocks": {"duration_days": 5, "pocket_minus_ref_usd": 100}, "analogue": {}}}


def test_ranking_and_exclusions(tmp_path):
    log = tmp_path / "run" / "audit_log.jsonl"
    log.parent.mkdir()
    rows = [rec("A", 6e6, 200.0), rec("B", 5.5e6, 100.0), rec("C", 4e6, 50.0), rec("D", 9e6, 30.0, severity="implausible"),
            rec("E", 7e6, 40.0, severity="ordinary", q=0.2), rec("F", 7e6, 40.0, engine=False), rec("G", 8e6, 10.0, fab=True)]
    log.write_text(json.dumps({"model": "m", "client_kind": "live", "scenarios": rows}) + "\n", encoding="utf-8")
    text = mrr.build(mrr.load_records([log]), 5e6, 10)
    assert text.index("#1 B") < text.index("#2 A")  # lower D^2 first
    assert "ranked (eligible): 2" in text
    for why in ("below target", "implausible", "ordinary world", "rejected before the engine", "fabricated analogue"):
        assert why in text
