import warnings

import pytest

from revstress import config
from revstress.agent import context as cx
from revstress.book import fit_book_params
from revstress.market import NYISO
from revstress.risk import fit_risk_model
from revstress.synthetic import generate_synthetic_panel


@pytest.fixture(scope="module")
def fitted():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = generate_synthetic_panel(0, "2019-01-01", "2024-12-31", warn=False)
        return panel, fit_book_params(panel), fit_risk_model(panel, seed=0, n_boot=10)


def test_book_table_has_every_position_with_the_market_zone_names(fitted):
    _, params, _ = fitted
    rows = cx.book_table(params, NYISO, fallback=False)
    assert [r["position"] for r in rows] == list(config.POSITIONS)
    text = " ".join(r["what"] + r["gains_when"] + r["loses_when"] for r in rows)
    assert "WEST" in text and "N.Y.C." in text
    p5 = next(r for r in rows if r["position"] == "P5")
    assert f"{params.sizes_mw['P5']:g} MW" in p5["what"] and "widens" in p5["loses_when"]
    assert {r["channel"] for r in rows} == set(config.CHANNELS)


def test_book_table_follows_the_fallback_book_and_the_sizes(fitted):
    from dataclasses import replace

    _, params, _ = fitted
    assert [r["position"] for r in cx.book_table(params, NYISO, fallback=True)] == list(config.FALLBACK_POSITIONS)
    resized = replace(params, sizes_mw={**params.sizes_mw, "P5": 123.0})
    assert "123 MW" in next(r for r in cx.book_table(resized, NYISO, False) if r["position"] == "P5")["what"]


def test_summary_states_that_price_rises_alone_make_the_book_gain():
    s = cx.book_summary(NYISO)
    assert "GAIN" in s and "P1" in s and "P4" in s and "P5" in s


def test_glossary_covers_every_agent_shock_key_and_defines_dart_as_a_percentage():
    from revstress.agent import schema

    g = cx.shock_glossary(NYISO)
    keys = set(schema.scenario_schema(NYISO)["properties"]["shocks"]["properties"])
    assert keys <= set(g), keys - set(g)
    assert "stated_loss_usd" in g
    assert "percentage" in g["dart_pct"] and "-100" in g["dart_pct"] and "WEST" in g["ref_onpeak_pct"] and "N.Y.C." in g["pocket_minus_ref_usd"]


def test_ceilings_are_ordered_and_cover_every_shock_key_and_season(fitted):
    panel, _, model = fitted
    c = cx.factor_ceilings(model, panel)
    assert set(c) <= {"winter", "summer", "shoulder"} and c
    for season, keys in c.items():
        assert set(keys) == {"gas_hh_pct", "load_peak_ratio", "ref_onpeak_pct", "pocket_minus_ref_usd", "dart_pct"}
        for k, v in keys.items():
            assert v["hist_min"] <= v["hist_max"], (season, k)
            assert v["implausible_below"] <= v["hist_min"] + 1e-9 and v["implausible_above"] >= v["hist_max"] - 1e-9, (season, k)


def test_price_extremes(fitted):
    panel, _, _ = fitted
    e = cx.price_extremes(panel, NYISO)
    assert e["max_daily_onpeak_ref_usd"] == round(float(panel["wh_on"].max()), 1)
    assert e["scenario_price_cap_usd"] == 5000.0


def test_sensitivities_use_agent_key_names_and_the_injected_engine(fitted):
    _, params, _ = fitted
    calls = []

    def pnl_fn(shock, season):
        calls.append((dict(shock), season))
        return {"P1": 10.0 * shock["gas_hh_pct"], "P5": -1.0}

    out = cx.shock_sensitivities(pnl_fn, "winter", NYISO, fallback=False)
    assert len(calls) == len(cx.SENSITIVITY_STEPS) and all(s == "winter" for _, s in calls)
    assert all(c[0]["duration_days"] == cx.SENSITIVITY_DAYS for c in calls)
    assert "ref_onpeak_pct" in out["steps"] and "pocket_minus_ref_usd" in out["steps"]
    assert out["pnl_usd_by_position"]["gas_hh_pct"]["P1"] == 250 and out["pnl_usd_by_position"]["gas_hh_pct"]["P5"] == -1
    assert out["pnl_usd_by_position"]["gas_hh_pct"]["total"] == 249


def test_enrich_context_adds_blocks_without_mutating_the_input(fitted):
    panel, params, model = fitted
    base = {"market": "NYISO"}
    out = cx.enrich_context(base, params, model, panel, NYISO, False, pnl_fn=lambda s, se: {"P1": 1.0}, seasons=("winter",))
    assert base == {"market": "NYISO"}
    assert {"book", "book_summary", "shock_ceilings_by_season", "price_extremes_usd_mwh", "shock_sensitivities"} <= set(out)
    assert "winter" in out["shock_sensitivities"]


def test_glossary_states_the_sign_a_large_load_shortfall_needs_and_matches_the_hard_rule():
    from revstress.agent import prompts, rules

    g = cx.shock_glossary(NYISO)
    assert "large_load_shortfall" in g["large_load_shock_mw"] and "NEGATIVE" in g["large_load_shock_mw"]
    assert "large_load_shortfall" in g["load_peak_ratio"] and "1.0 or below" in g["load_peak_ratio"]
    assert "large_load_shock_mw must be zero or negative" in prompts._method(prompts.PROMPT_V3)

    def verdicts(mw):
        sc = {"driver_class": "large_load_shortfall", "season": "summer", "shocks": {"large_load_shock_mw": mw, "load_peak_ratio": 1.0}}
        return rules._rule_sign_consistency(sc, sc["shocks"], NYISO)

    assert not verdicts(800.0).passed and verdicts(-500.0).passed
