"""Market refactor tests (plan section 12): Market object, NYISO cap and labels, analogues, agent boundary, FakeClient.

Hand-made fixtures and SYNTHETIC / FAKE CLIENT data only; zero network calls.
"""

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest

from revstress import config
from revstress.agent import client as client_mod
from revstress.agent import loop, prompts, rules, schema
from revstress.baselines.common import SpikeOverlay, classify_driver, template_narrative
from revstress.eval import analogues
from revstress.market import NYISO, PJM, get_market
from revstress.panel import panel_window, validate_panel
from revstress.risk import fit_risk_model, score_scenario
from revstress.shock import apply_shock, validate_shock
from revstress.synthetic import SYNTHETIC_WARNING, generate_synthetic_panel, synthetic_warning


@pytest.fixture
def nyiso(monkeypatch):
    monkeypatch.setattr(config, "MARKET", "NYISO")
    return NYISO


# ----------------------------------------------------------------------------- Market object


def test_get_market_default_and_names():
    assert get_market() is PJM and get_market("pjm") is PJM and get_market("NYISO") is NYISO
    assert get_market(NYISO) is NYISO
    with pytest.raises(ValueError):
        get_market("ERCOT")
    assert config.MARKET == "PJM" and config.active_market() is PJM


def test_market_is_frozen_and_labels():
    with pytest.raises(dataclasses.FrozenInstanceError):
        NYISO.name = "X"  # type: ignore[misc]
    assert (NYISO.reference_zone, NYISO.pocket_zone) == ("WEST", "N.Y.C.")
    assert (PJM.reference_zone, PJM.pocket_zone) == ("Western Hub", "Dominion")
    assert NYISO.onpeak_hours == 16 and NYISO.nerc_holidays
    assert dict(NYISO.weather_stations)["NYC_CentralPark"] == "USW00094728"
    assert NYISO.typical_peak_by_season["summer"] == 31_600.0


def test_cap_values_and_assumption_flag():
    assert PJM.energy_cap_usd == 3700.0 == config.ENERGY_COMPONENT_CAP_USD and not PJM.cap_is_assumption
    assert NYISO.energy_cap_usd == 5000.0 and NYISO.cap_is_assumption
    assert "ASSUMPTION" in NYISO.cap_note and "not a NYISO number" in NYISO.cap_note
    assert config.energy_cap_usd() == 3700.0


def test_cap_follows_active_market(nyiso):
    assert config.energy_cap_usd() == 5000.0
    assert config.gas_basis_by_season() == NYISO.gas_basis_by_season
    assert SpikeOverlay().max_avg_usd == 5000.0


def test_structural_breaks_from_market(nyiso):
    br = config.structural_breaks()
    assert br["scarcity_pricing"] == "2016-06-22" and br["transmission_shortage_pricing"] == "2023-11-14"
    assert br["indian_point_2_retirement"] == "2020-04" and br["indian_point_3_retirement"] == "2021-04"
    assert br["chpe_in_service"] is None  # unverified, plan section 4
    assert config.break_cutoff() == "2016-06-22"


def test_pjm_breaks_unchanged():
    assert config.STRUCTURAL_BREAKS["reserve_market_redesign"] == "2022-10-01"
    assert config.break_cutoff() == "2022-10-01"


def test_shock_key_maps_cover_engine_keys():
    assert PJM.agent_shock_keys == config.SHOCK_KEYS == PJM.engine_shock_keys
    assert set(NYISO.engine_shock_keys) - set(config.SHOCK_KEYS) == set(config.OPTIONAL_SHOCK_KEYS)
    assert len(NYISO.agent_shock_keys) == 10


# ----------------------------------------------------------------------------- analogues


def test_nyiso_analogue_values_from_plan():
    t = analogues.analogue_table("NYISO")
    jan14 = t["Polar vortex January 2014 (NYISO)"]
    assert jan14["west_rt_onpeak_usd_mwh"] == 354.4 and jan14["nyc_da_onpeak_usd_mwh"] == 224.8
    assert jan14["nyca_peak_mw"] == 25737.8
    assert t["Winter Storm Elliott (NYISO)"]["nyca_peak_mw_24dec"] == 22003.9
    assert t["January 2025 cold (NYISO)"]["nyca_peak_mw_22jan"] == 23521.3
    assert t["June 2025 heat (NYISO)"]["nyca_peak_mw_24jun"] == 31857.2
    gb = t["NYISO Gold Book large-load series"]
    assert [gb[f"large_load_summer_{y}_mw"] for y in (2026, 2030, 2035, 2040)] == [538, 1831, 2643, 2880]


def test_nyiso_unverified_rows_are_none_and_hidden():
    row = analogues.lookup("elliott", "z6_ny_gas_usd_mmbtu", "NYISO")
    assert row is not None and row.value is None
    for ev in ("jan2014", "elliott", "jan2025", "jun2025"):
        assert analogues.lookup(ev, "event_day_max_lbmp_usd_mwh", "NYISO").value is None
        assert analogues.lookup(ev, "shortage_intervals", "NYISO").value is None
    shown = analogues.analogue_table("NYISO")
    assert all("z6_ny_gas_usd_mmbtu" not in v and "shortage_intervals" not in v for v in shown.values())
    assert analogues.score_claim("elliott", "z6_ny_gas_usd_mmbtu", 50.0, "NYISO") == "not_in_table"


def test_every_nyiso_row_has_source_and_vintage():
    rows = analogues.analogue_rows("NYISO")
    assert rows and all(r.source and r.vintage for r in rows)


def test_nyiso_scoring_and_aliases():
    assert analogues.score_claim("Polar vortex Jan 2014", "west_rt_onpeak_usd_mwh", 354.4, "NYISO") == "correct"
    assert analogues.score_claim("jan 2014", "west_rt_onpeak_usd_mwh", 300.0, "NYISO") == "within30"
    assert analogues.score_claim("jan 2014", "west_rt_onpeak_usd_mwh", 100.0, "NYISO") == "wrong"
    assert analogues.normalise_event("Gold Book", "NYISO") == "datacenter"


def test_pjm_analogues_unchanged_and_default():
    assert analogues.analogue_table() == analogues.analogue_table("PJM")
    assert analogues.lookup("elliott", "actual_peak_mw_metered").value == 134700
    assert analogues.lookup("elliott", "actual_peak_mw_metered", "NYISO") is None


def test_active_market_switches_analogue_table(nyiso):
    assert analogues.lookup("jun2025", "nyca_peak_mw_24jun").value == 31857.2
    assert "Winter Storm Elliott (NYISO)" in rules.default_analogue_table()


# ----------------------------------------------------------------------------- agent boundary


def test_key_mapping_roundtrip():
    sh = {"ref_onpeak_pct": 10.0, "pocket_minus_ref_usd": 5.0, "large_load_shock_mw": -500.0, "ny_gas_basis_usd": 3.0, "gas_hh_pct": 1.0}
    eng = rules.to_engine_shocks(sh, "NYISO")
    assert eng == {"wh_onpeak_pct": 10.0, "dom_minus_wh_usd": 5.0, "dc_load_shock_mw": -500.0, "ny_gas_basis_usd": 3.0, "gas_hh_pct": 1.0}
    assert rules.to_agent_shocks(eng, "NYISO") == sh
    assert rules.to_engine_shocks({"wh_onpeak_pct": 1.0}, "PJM") == {"wh_onpeak_pct": 1.0}
    assert "ref_onpeak_pct = wh_onpeak_pct" in rules.SHOCK_MAPPING_LINE
    assert "pocket_minus_ref_usd = dom_minus_wh_usd" in rules.SHOCK_MAPPING_LINE


def _ny_scenario(driver="heat_wave", **shock):
    s = client_mod.canned_scenarios(driver, 0, 1, "v3", "NYISO")[0]
    s["shocks"].update(shock)
    return s


def test_canned_nyiso_scenarios_pass_schema_and_rules():
    for driver in NYISO.driver_classes:
        for it in (0, 5, 11):
            sc = client_mod.canned_scenarios(driver, it, 3, "v3", "NYISO")[2]
            assert schema.validate_scenario(sc, "NYISO") == [], (driver, it)
            assert rules.hard_pass(rules.check_hard_rules(sc, market="NYISO")), (driver, it)
            assert set(sc["shocks"]) == set(NYISO.agent_shock_keys)
            assert sc["shocks"]["spike_daily_avg_usd"] <= 5000.0
            assert client_mod.FAKE_CLIENT_LABEL in sc["narrative"]
            assert len(sc["narrative"].split()) >= rules.NARRATIVE_MIN_WORDS


def test_nyiso_schema_requires_stated_loss_and_rejects_pjm_keys():
    sc = _ny_scenario()
    sc2 = {k: v for k, v in sc.items() if k != "stated_loss_usd"}
    assert any("stated_loss_usd" in e["message"] for e in schema.validate_scenario(sc2, "NYISO"))
    pjm_like = client_mod.canned_scenarios("heat_wave", 0, 1, "v3", "PJM")[0]
    assert schema.validate_scenario(pjm_like, "NYISO")
    assert schema.validate_scenario(pjm_like, "PJM") == []


def test_nyiso_cap_rule_fires_above_5000_only():
    ok = rules.check_hard_rules(_ny_scenario(spike_daily_avg_usd=4500.0), market="NYISO")
    assert rules.hard_pass(ok)
    bad = rules.check_hard_rules(_ny_scenario(spike_daily_avg_usd=5000.5), market="NYISO")
    failed = [v for v in bad if not v.passed]
    assert [v.rule for v in failed] == ["scenario_price_cap"]
    pjm = rules.check_hard_rules(client_mod.canned_scenarios("heat_wave", 0, 1, "v3", "PJM")[0], market="PJM")
    assert any(v.rule == "energy_component_cap" for v in pjm)


def test_nyiso_rules_reject_engine_keys_and_wrong_driver():
    sc = _ny_scenario()
    sc["shocks"]["wh_onpeak_pct"] = 1.0
    assert not rules.hard_pass(rules.check_hard_rules(sc, market="NYISO"))
    sc = _ny_scenario()
    sc["driver_class"] = "demand_shock_datacenter"
    assert any(v.rule == "valid_enums" and not v.passed for v in rules.check_hard_rules(sc, market="NYISO"))
    sc = _ny_scenario("large_load_shortfall", large_load_shock_mw=800.0)
    assert any("large_load_shortfall_with_load_up" in v.detail for v in rules.check_hard_rules(sc, market="NYISO"))


def test_nyiso_analogue_rule_uses_nyiso_table():
    sc = _ny_scenario()
    sc["analogue"] = {"event": "Heat June 2025", "dates": "24 Jun 2025", "claimed": {"nyca_peak_mw_24jun": 31857.2}, "source": "x"}
    assert rules.hard_pass(rules.check_hard_rules(sc, market="NYISO"))
    sc["analogue"]["claimed"] = {"nyca_peak_mw_24jun": 20000.0}
    assert rules.is_fabricated(rules.check_hard_rules(sc, market="NYISO"))
    sc["analogue"] = {"event": "Winter Storm Elliott", "dates": "", "claimed": {"actual_peak_mw_metered": 134700}, "source": ""}
    assert rules.is_fabricated(rules.check_hard_rules(sc, market="NYISO"))  # PJM metric is not in the NYISO table


# ----------------------------------------------------------------------------- prompts


def test_nyiso_prompt_text_and_labels():
    system, msgs = prompts.build_seed_prompt("v3", {"note": "x"}, "heat_wave", "summer", market="NYISO")
    user = msgs[0]["content"]
    assert "NYISO" in system and "WEST" in system and "N.Y.C." in system and "30 GW" in system and "PJM" not in system
    assert "scenario cap of $5,000/MWh" in user and "stated assumption" in user and "3,700" not in user
    assert rules.SHOCK_MAPPING_LINE in user
    assert "ny_gas_basis_usd" in user and "large_load_shock_mw" in user and "stated_loss_usd" in user
    assert "dc_load_shock_mw\"" not in user and "tail_high_mw" in user  # large-load ranges shown
    assert "Polar vortex January 2014 (NYISO)" in user and "PJM 2026 load forecast" not in user
    v1 = prompts.build_seed_prompt("v1", {}, "cold_snap", market="NYISO")[1][0]["content"]
    assert "ref_onpeak_pct" in v1 and "pocket_minus_ref_usd" in v1


def test_pjm_prompt_unchanged():
    system, msgs = prompts.build_seed_prompt("v3", {"note": "x"}, "cold_snap", "winter")
    assert system == prompts.ROLE and "PJM" in system and "$3,700/MWh" in msgs[0]["content"]
    assert "stated_loss_usd" not in msgs[0]["content"]
    assert prompts.build_seed_prompt("v3", {"note": "x"}, "cold_snap", "winter", market="PJM") == (system, msgs)


def test_nyiso_prompt_follows_active_market(nyiso):
    system, _ = prompts.build_seed_prompt("v2", {}, "heat_wave")
    assert system == prompts.NYISO_ROLE


# ----------------------------------------------------------------------------- FakeClient and loop


def test_fakeclient_nyiso_labelled_and_parseable(tmp_path):
    fc = client_mod.FakeClient(market="NYISO", cache_dir=tmp_path)
    system, msgs = prompts.build_seed_prompt("v3", {}, "reserve_shortage", "summer", market="NYISO")
    resp = fc.complete(system, msgs, "v3")
    parsed, err = schema.extract_scenarios(resp.text)
    assert err is None and len(parsed) == client_mod.config.SCENARIOS_PER_CALL
    assert all(s["driver_class"] == "reserve_shortage" for s in parsed)
    assert all(schema.validate_scenario(s, "NYISO") == [] for s in parsed)
    entry = json.loads(next(tmp_path.glob("fake-*.json")).read_text(encoding="utf-8"))
    assert entry["label"] == "FAKE CLIENT - not Claude results" and entry["synthetic"] is True
    assert client_mod.FAKE_CLIENT_LABEL == "FAKE CLIENT - not Claude results"


def test_fakeclient_pjm_default_keys():
    sc = client_mod.canned_scenarios("cold_snap", 0, 1)[0]
    assert set(sc["shocks"]) == set(config.SHOCK_KEYS) and "stated_loss_usd" not in sc
    assert client_mod.FAKE_CLIENT_LABEL in sc["narrative"]
    assert sc["shocks"]["spike_daily_avg_usd"] <= 3700.0


def test_loop_translates_agent_keys_for_engine():
    seen: list[dict] = []

    def engine(shocks):
        seen.append(dict(shocks))
        return {"pnl_total": -6e6, "pnl_by_position": {}, "pnl_by_channel": {}, "d2": 1.0, "q": 0.02, "marginals": {},
                "nearest_date": "2024-01-02", "severity": "adverse", "spike_exceedance": 0.0}

    fc = client_mod.FakeClient(market="NYISO")
    res = loop.run_loop(fc, engine, ["heat_wave"], iterations=1, prompt_version="v3", market="NYISO")
    assert res.accepted == 3 and seen
    for s in seen:
        assert set(s) == set(NYISO.engine_shock_keys)
        assert "ref_onpeak_pct" not in s and "wh_onpeak_pct" in s and "ny_gas_basis_usd" in s


# ----------------------------------------------------------------------------- shock, synthetic, plausibility


def test_validate_shock_accepts_optional_basis_key_only_when_given():
    assert set(validate_shock({}, 5)) == set(config.SHOCK_KEYS)
    assert validate_shock({"ny_gas_basis_usd": 5.0}, 5)["ny_gas_basis_usd"] == 5.0
    with pytest.raises(ValueError):
        validate_shock({"bogus": 1.0}, 5)


def _flat(n=6, start="2027-01-11"):
    return pd.DataFrame({
        "date": pd.date_range(start, periods=n), "wh_on": 60.0, "wh_off": 40.0, "dom_on": 75.0, "dom_off": 50.0,
        "da_wh_off": 41.0, "rt_wh_off": 40.0, "da_wh_on": 58.0, "rt_wh_on": 60.0, "load_peak_mw": 25_000.0,
        "hh_usd": 4.0, "hdd": 30.0, "cdd": 0.0,
    })


def test_basis_shock_moves_gas_leg_only():
    base = _flat()
    out = apply_shock(base, {"ny_gas_basis_usd": 20.0, "duration_days": 3}, 0)
    assert np.allclose(out["hh_usd"][:3], 24.0) and np.allclose(out["hh_usd"][3:], 4.0)
    assert np.allclose(out["wh_on"], base["wh_on"])  # WEST is the least gas-exposed zone (plan section 3)


def test_scenario_cap_clip_follows_market(nyiso):
    out = apply_shock(_flat(), {"wh_onpeak_pct": 20000, "duration_days": 3}, 0)
    assert out["wh_on"].max() == 5000.0 and out["energy_clipped"].any()


def test_synthetic_nyiso_scale_and_label():
    p = generate_synthetic_panel(3, start="2022-01-01", end="2023-12-31", warn=False, market="NYISO")
    validate_panel(p)
    assert 10_000 < p["load_peak_mw"].min() and p["load_peak_mw"].max() < 40_000
    assert p["wh_on"].max() <= 5000.0 and (p["synthetic_source"] == "SYNTHETIC").all()
    assert "NYISO" in p.attrs["warning"] and "not PJM" not in p.attrs["warning"]
    assert (p["dom_on"] - p["wh_on"]).mean() > 8.0
    pj = generate_synthetic_panel(3, start="2022-01-01", end="2023-12-31", warn=False)
    assert pj.attrs["warning"] == SYNTHETIC_WARNING and pj["load_peak_mw"].max() > 100_000
    assert synthetic_warning("NYISO") != SYNTHETIC_WARNING


def test_synthetic_nyiso_warns():
    with pytest.warns(UserWarning, match="NYISO"):
        generate_synthetic_panel(1, start="2022-01-01", end="2022-03-01", market="NYISO")


def test_plausibility_cap_failure_label_follows_market(monkeypatch):
    p = generate_synthetic_panel(5, warn=False, market="NYISO")
    monkeypatch.setattr(config, "MARKET", "NYISO")
    model = fit_risk_model(p, n_boot=5)
    path = apply_shock(panel_window(p, "2025-01-05", 10), {"duration_days": 10}, rng_seed=0)
    path.loc[0, "wh_on"] = 5200.0
    assert "scenario_cap_above_5000" in score_scenario(path, model)["hard_rule_failures"]
    path.loc[0, "wh_on"] = 4000.0  # above the PJM cap, below the NYISO scenario cap
    assert "scenario_cap_above_5000" not in score_scenario(path, model)["hard_rule_failures"]
    assert model.min_date_used >= pd.Timestamp("2019-01-01")


def test_pre_break_cutoff_uses_market_break(monkeypatch):
    p = generate_synthetic_panel(5, start="2015-01-01", end="2019-12-31", warn=False, market="NYISO")
    monkeypatch.setattr(config, "MARKET", "NYISO")
    m = fit_risk_model(p, include_pre_break=False, n_boot=5)
    assert m.min_date_used >= pd.Timestamp("2016-06-22")


# ----------------------------------------------------------------------------- baselines text


def test_baseline_text_and_driver_follow_market():
    shock = {**config.NEUTRAL_SHOCK, "wh_onpeak_pct": 50.0, "dom_minus_wh_usd": 30.0, "spike_days": 2,
             "spike_daily_avg_usd": 450.0, "duration_days": 5, "dc_load_shock_mw": -800.0, "ny_gas_basis_usd": 10.0}
    txt = template_narrative(shock, "summer", "large_load_shortfall", 6e6, market="NYISO")
    assert "WEST" in txt and "N.Y.C." in txt and "Western Hub" not in txt and "Dominion" not in txt
    assert "New York gas basis" in txt and "-800 MW" in txt
    assert "Western Hub" in template_narrative(shock, "summer", "policy", None, market="PJM")
    assert classify_driver(shock, "summer", "NYISO") == "large_load_shortfall"
    assert classify_driver({**config.NEUTRAL_SHOCK}, "summer", "NYISO") == "reserve_shortage"
    assert classify_driver({**config.NEUTRAL_SHOCK}, "summer", "PJM") == "policy"
    assert classify_driver({**config.NEUTRAL_SHOCK, "dc_load_shock_mw": 100.0}, "summer", "PJM") == "demand_shock_datacenter"
