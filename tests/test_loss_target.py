"""Loss target (plan 25% of capital, with re-set book sizes): default value and a deterministic conditional-Gaussian breach on
the real NYISO panel.

Uses the processed NYISO panel in data/processed (skipped if absent); no network, no API.
"""

import json
from pathlib import Path

import pytest

from revstress import config, pipeline_real as pr
from revstress.baselines import cond_gaussian_search
from revstress.book import fit_book_params
from revstress.eval import diagnostics as dg
from revstress.eval import metrics
from revstress.pipeline import HORIZON_DAYS, ScenarioEngine, season_spec
from revstress.risk import fit_risk_model

PLAN_TARGET_USD = 5e6  # 25% of capital; the sizes were re-set so that this target is a tail event
PANEL = Path(pr.DATA_ROOT) / "processed" / pr.PANEL_FILE


def test_default_target_is_the_plan_value_and_the_selection_rule_is_documented():
    assert config.LOSS_TARGET_USD == PLAN_TARGET_USD
    assert config.LOSS_TARGET_USD / config.ALLOCATED_CAPITAL_USD == pytest.approx(0.25)
    text = Path(config.__file__).read_text(encoding="utf-8")
    assert "BOOK-SIZE SELECTION RULE" in text and "written BEFORE" in text


def test_manifest_market_is_nyiso_not_pjm(tmp_path):
    """Regression: a review saw 'MARKET: PJM' in an NYISO run manifest; the demo must stamp NYISO everywhere."""
    from revstress import manifest

    assert config.MARKET == "PJM"  # the global flag is back to the default when outputs are written
    path = manifest.write_run_manifest(
        "run", model="fake-client", temperature=None, seed=0, prompt_version="v3", system="s",
        messages=[{"role": "user", "content": "m"}], market="NYISO", label="FAKE CLIENT - not Claude results",
        data_root=tmp_path / "data", outputs_root=tmp_path / "out",
    )
    man = json.loads(path.read_text(encoding="utf-8"))
    assert man["market"]["name"] == "NYISO" and man["config"]["MARKET"] == "NYISO"
    assert "PJM" not in json.dumps(man["market"]) and "PJM" not in json.dumps(man["config"])


@pytest.mark.skipif(not PANEL.exists(), reason="processed NYISO panel not present")
def test_cond_gaussian_finds_a_breach_at_the_default_target(monkeypatch):
    # Snap-back engine (no persistence tail): the book was calibrated on it. With the tail ON the same book loses more per shock,
    # 5M is reached by ordinary worlds and the cond-Gaussian point is no longer a tail event (config.py RESULT v3).
    monkeypatch.setattr(config, "DAILY_PERSISTENCE", False)
    with pr.nyiso_market():
        _, fit = pr.load_real_panel()
        params = fit_book_params(fit)
        model = fit_risk_model(fit, as_of=pr.FIT_END, seed=0, n_boot=5)
        pt, _ = dg.estimate_passthrough(fit, model.price_model, params.l_normal_mw)
        eng = ScenarioEngine(fit, params, model, seed=0, passthrough=pt).for_season("winter")
        recs = cond_gaussian_search(
            eng, season_spec(model, "winter"), budget=60, seed=0, season="winter", horizon_days=HORIZON_DAYS,
            target_usd=config.LOSS_TARGET_USD,
        )
        # neutral shock is exactly zero shock-attributable P&L (no base-window artefact)
        assert abs(eng(dict(config.NEUTRAL_SHOCK))["pnl_total"]) < 1e-6
    breaches = [r for r in recs if metrics.is_breaching(r, config.LOSS_TARGET_USD)]
    assert len(breaches) >= 1
    b = breaches[0]
    assert b["loss_usd"] >= config.LOSS_TARGET_USD and b["engine"]["q"] < config.Q_ADVERSE_MAX and not b["rules_failed"]
