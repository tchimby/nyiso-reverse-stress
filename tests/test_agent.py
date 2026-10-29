import copy
import json

import pytest

from revstress import config
from revstress.agent import client as cl
from revstress.agent import prompts, rules, schema
from revstress.agent.loop import main, run_loop

CTX = {"book": "table", "target_usd": 5e6}


def good(**over):
    sc = {
        "scenario_id": "S-1",
        "prompt_version": "v3",
        "narrative": " ".join(["word"] * 45),
        "horizon_days": 30,
        "season": "winter",
        "driver_class": "cold_snap",
        "shocks": {
            "gas_hh_pct": 50.0,
            "load_peak_ratio": 1.1,
            "dc_load_shock_mw": 0,
            "wh_onpeak_pct": 10.0,
            "dom_minus_wh_usd": 5.0,
            "dart_pct": 20.0,
            "spike_days": 2,
            "spike_daily_avg_usd": 1500.0,
            "duration_days": 7,
        },
        "analogue": {"event": "", "dates": "", "claimed": {}, "source": ""},
        "confidence": "low",
    }
    sc.update(over)
    return sc


def stub_engine(shock):
    """Stub engine: loss scales with gas shock; not a risk model."""
    loss = shock["gas_hh_pct"] * 1e5
    return {
        "pnl_total": -loss,
        "pnl_by_position": {"P1": -loss},
        "pnl_by_channel": {"system": -loss},
        "d2": 4.0,
        "q": 0.02,
        "marginals": {"g": min(shock["gas_hh_pct"] / 1000, 1.0), "l": 0.5},
        "z": {"g": shock["gas_hh_pct"] / 100.0, "l": 0.0, "s": 0.0, "c": 0.0, "d": 0.0},
        "nearest_date": "2022-12-23",
        "severity": "adverse",
        "spike_exceedance": 0.0,
    }


def rule_names(verdicts, failed_only=True):
    return {v.rule for v in verdicts if not v.passed or not failed_only}


# ------------------------------------------------------------------ schema


def test_schema_accepts_good_and_reports_errors():
    assert schema.validate_scenario(good()) == []
    bad = good(season="monsoon")
    del bad["shocks"]["gas_hh_pct"]
    bad["shocks"]["spike_days"] = "three"
    errs = schema.validate_scenario(bad)
    paths = {e["path"] for e in errs}
    assert {"/season", "/shocks", "/shocks/spike_days"} <= paths
    assert all(set(e) == {"path", "validator", "message"} for e in errs)


def test_extract_scenarios_variants():
    sc = good()
    assert schema.extract_scenarios(json.dumps({"scenarios": [sc]}))[0] == [sc]
    assert schema.extract_scenarios("```json\n" + json.dumps(sc) + "\n```")[0] == [sc]
    assert schema.extract_scenarios("no json here")[1] == "no_json_scenarios_found"


# ------------------------------------------------------------------ rules


def test_hard_rules_pass_for_good():
    assert rules.hard_pass(rules.check_hard_rules(good()))


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda s: s["shocks"].update(spike_daily_avg_usd=4000.0), "energy_component_cap"),
        (lambda s: s["shocks"].update(load_peak_ratio=0.9), "sign_consistent"),
        (lambda s: s["shocks"].update(gas_hh_pct=-10.0), "sign_consistent"),
        (lambda s: s["shocks"].update(duration_days=40), "duration_within_horizon"),
        (lambda s: s["shocks"].update(spike_days=0), "spike_consistent"),
        (lambda s: s.update(driver_class="blizzard"), "valid_enums"),
    ],
)
def test_hard_rule_rejection(mutate, expected):
    sc = good()
    mutate(sc)
    v = rules.check_hard_rules(sc)
    assert expected in rule_names(v)
    assert not rules.hard_pass(v)


def test_analogue_rule():
    ok = good(analogue={"event": "Winter Storm Elliott", "dates": "Dec 2022", "claimed": {"actual_peak_mw_metered": 130000}, "source": "x"})
    assert rules.hard_pass(rules.check_hard_rules(ok))
    off = copy.deepcopy(ok)
    off["analogue"]["claimed"]["actual_peak_mw_metered"] = 200000
    v = rules.check_hard_rules(off)
    assert rules.is_fabricated(v) and not rules.hard_pass(v)
    nov = copy.deepcopy(ok)
    nov["analogue"]["event"] = "Hurricane Zed 2031"
    assert rules.is_fabricated(rules.check_hard_rules(nov))
    none_metric = copy.deepcopy(ok)
    none_metric["analogue"] = {"event": "January 2014", "dates": "", "claimed": {"western_hub_price_usd_mwh": 500}, "source": ""}
    assert rules.is_fabricated(rules.check_hard_rules(none_metric))


def test_analogue_empty_event_with_numbers_is_fabricated():
    sc = good(analogue={"event": "", "dates": "", "claimed": {"actual_peak_mw_metered": 999999}, "source": ""})
    v = rules.check_hard_rules(sc)
    assert rules.is_fabricated(v) and not rules.hard_pass(v)
    blank = good(analogue={"event": "  ", "dates": "", "claimed": {}, "source": ""})
    assert rules.hard_pass(rules.check_hard_rules(blank))


@pytest.mark.parametrize("event", ["Elliott", "Dec 2022", "winter storm elliott", "Winter Storm Elliott, 23-24 Dec 2022"])
def test_analogue_short_event_forms_resolve(event):
    sc = good(analogue={"event": event, "dates": "", "claimed": {"actual_peak_mw_metered": 134700}, "source": ""})
    assert rules.hard_pass(rules.check_hard_rules(sc))
    assert rules.lookup_event(rules.DEFAULT_ANALOGUE_TABLE, "Jan 2014") == "January 2014"
    assert rules.lookup_event(rules.DEFAULT_ANALOGUE_TABLE, "data center") is not None
    assert rules.lookup_event(rules.DEFAULT_ANALOGUE_TABLE, "Hurricane Zed 2031") is None


def test_rules_table_and_scoring_share_one_source():
    from revstress.eval import analogues

    table = rules.DEFAULT_ANALOGUE_TABLE
    assert table == analogues.analogue_table()
    n = 0
    for event, metrics_ in table.items():
        for metric, value in metrics_.items():
            sc = good(analogue={"event": event, "dates": "", "claimed": {metric: value}, "source": ""})
            assert rules.hard_pass(rules.check_hard_rules(sc)), (event, metric)
            assert analogues.score_analogue(sc["analogue"]) == {metric: "correct"}, (event, metric)
            n += 1
    assert n == sum(a.value is not None for a in analogues.ANALOGUES)
    assert "western_hub_price_usd_mwh" not in table["January 2014"]


def test_soft_penalties():
    short = good(narrative="too short")
    v = rules.soft_penalties(short, {"q": 0.0005}, {"cold_snap": 3})
    assert rule_names(v) == {"q_not_too_small", "narrative_length", "driver_class_not_overused"}
    assert rules.total_penalty(v) == 3.0
    assert rules.total_penalty(rules.soft_penalties(good(), {"q": 0.02}, {})) == 0.0


# ------------------------------------------------------------------ prompts


def test_prompt_versions_differ():
    texts = {v: prompts.build_seed_prompt(v, CTX, "cold_snap")[1][0]["content"] for v in prompts.PROMPT_VERSIONS}
    for t in texts.values():
        for part in ("TASK", "INPUTS", "CONSTRAINTS", "METHOD", "OUTPUT FORMAT", "QUALITY CRITERIA"):
            assert part in t
    assert "JSON Schema" not in texts["v1"] and "JSON Schema" in texts["v2"]
    assert "Analogue table" not in texts["v2"] and "Analogue table" in texts["v3"]
    assert prompts.build_seed_prompt("v1", CTX, "cold_snap")[0] == prompts.ROLE
    with pytest.raises(ValueError):
        prompts.build_seed_prompt("v9", CTX, "cold_snap")


def test_feedback_message_numbers_and_verdicts_only():
    hard = [v.to_dict() for v in rules.check_hard_rules(good())]
    msg = prompts.build_feedback_message(
        [{"scenario_id": "S-1", "verdicts": hard, "engine": stub_engine(good()["shocks"]), "loss_usd": 5e6}],
        breaches_so_far=1,
    )
    assert "loss_usd: 5e+06" in msg and "d2: 4" in msg and "rule energy_component_cap: PASS" in msg
    assert "narrative" not in msg
    plain = prompts.build_feedback_message([{"scenario_id": "S-1", "verdicts": hard}], include_engine=False)
    assert "d2" not in plain


# ------------------------------------------------------------------ client


def test_cache_hit_and_miss(tmp_path):
    c = cl.FakeClient(cache_dir=tmp_path)
    msgs = [{"role": "user", "content": "Driver family: cold_snap"}]
    r1 = c.complete("sys", msgs, "v3")
    r2 = c.complete("sys", msgs, "v3")
    assert not r1.cache_hit and r2.cache_hit and r1.text == r2.text and c.live_calls == 1
    assert c._cache_path(r1.cache_key).exists() and c._cache_path(r1.cache_key).name.startswith("fake-")
    c.complete("sys", msgs, "v2")  # different prompt version -> miss
    c.complete("sys", msgs + [{"role": "assistant", "content": "x"}], "v3")  # different messages -> miss
    assert c.live_calls == 3
    assert c.totals["cache_hits"] == 1 and c.totals["output_tokens"] > 0


def test_dry_run_client_never_calls(tmp_path):
    c = cl.FakeClient(cache_dir=tmp_path, dry_run=True)
    r = c.complete("sys", [{"role": "user", "content": "hi"}], "v3")
    assert r.error == "dry_run_cache_miss" and c.live_calls == 0
    rep = cl.dry_run_report("sys", [{"role": "user", "content": "hi"}], "v3", c.model, c.max_tokens, c.cache_kind)
    assert r.cache_key in rep and "hi" in rep


def test_retry_classification():
    assert cl.is_retryable_status(429) and cl.is_retryable_status(500) and cl.is_retryable_status(529)
    assert not cl.is_retryable_status(400) and not cl.is_retryable_status(401) and not cl.is_retryable_status(None)


class Boom(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


def flaky_client(statuses, **kw):
    sleeps = []
    c = cl.FakeClient(responses=["{}"], sleep=sleeps.append, **kw)
    seq = list(statuses)

    def transport(system, messages):
        c.live_calls += 1
        s = seq.pop(0)
        if s is not None:
            raise Boom(s)
        return "ok", 3, 4

    c._transport = transport
    return c, sleeps


def test_retries_429_then_succeeds():
    c, sleeps = flaky_client([429, 503, None])
    r = c.complete("s", [{"role": "user", "content": "x"}], "v1")
    assert r.error is None and r.text == "ok" and r.attempts == 3 and len(sleeps) == 2
    assert sleeps[1] > sleeps[0] * 0.9 and all(s > 0 for s in sleeps)


def test_no_retry_on_400_and_failures_are_fields():
    c, sleeps = flaky_client([400])
    r = c.complete("s", [{"role": "user", "content": "x"}], "v1")
    assert r.error and r.status_code == 400 and r.attempts == 1 and sleeps == []


def test_retry_exhaustion_returns_error():
    c, sleeps = flaky_client([500] * 10, max_retries=2)
    r = c.complete("s", [{"role": "user", "content": "x"}], "v1")
    assert r.error and r.attempts == 3 and len(sleeps) == 2


def test_missing_api_key_is_error_field(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = cl.ClaudeClient().complete("s", [{"role": "user", "content": "x"}], "v1")
    assert r.error and "MissingApiKeyError" in r.error and r.attempts == 1


# ------------------------------------------------------------------ loop


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_loop_end_to_end_and_audit_fields(tmp_path):
    log = tmp_path / "audit.jsonl"
    c = cl.FakeClient()
    res = run_loop(c, stub_engine, ["cold_snap"], iterations=2, log_path=log, context=CTX, early_stop_breaches=99, tau=0.0)
    recs = read_log(log)
    calls = [r for r in recs if r["event"] == "call"]
    assert len(calls) == 2 and recs[-1]["event"] == "summary"
    first = calls[0]
    for key in (
        "prompt_version", "prompt_hash", "messages_in", "response_text", "cache_hit",
        "input_tokens", "output_tokens", "scenarios", "cache_key", "error",
    ):
        assert key in first
    sc = first["scenarios"][0]
    for key in ("scenario", "engine_output", "hard_verdicts", "soft_verdicts", "loss_usd", "schema_errors"):
        assert key in sc
    assert sc["engine_output"]["d2"] == 4.0
    assert calls[1]["messages_in"][-1]["content"].startswith("RESULTS")
    assert res.accepted == 6 and res.input_tokens > 0 and res.stop_reasons == {0: "iteration_budget"}
    assert len(res.breaches) > 0


def test_loop_rejects_hard_rule_violations_and_skips_engine(tmp_path):
    bad = good(shocks={**good()["shocks"], "spike_daily_avg_usd": 5000.0})
    calls = []

    def engine(shock):
        calls.append(shock)
        return stub_engine(shock)

    c = cl.FakeClient(responses=[json.dumps({"scenarios": [bad]})])
    log = tmp_path / "a.jsonl"
    res = run_loop(c, engine, ["cold_snap"], iterations=1, log_path=log)
    assert calls == [] and res.rejected == 1 and res.accepted == 0 and not res.breaches
    sc = read_log(log)[0]["scenarios"][0]
    assert not sc["accepted"] and sc["engine_output"] is None
    assert any(v["rule"] == "energy_component_cap" and not v["passed"] for v in sc["hard_verdicts"])


def test_loop_counts_fabricated_analogue():
    sc = good(analogue={"event": "Winter Storm Elliott", "dates": "", "claimed": {"actual_peak_mw_metered": 999999}, "source": ""})
    c = cl.FakeClient(responses=[json.dumps({"scenarios": [sc]})])
    res = run_loop(c, stub_engine, ["cold_snap"], iterations=1)
    assert res.fabricated_analogues == 1 and res.rejected == 1


def test_early_stop_on_breaches():
    c = cl.FakeClient()
    res = run_loop(c, stub_engine, ["cold_snap"], iterations=12, early_stop_breaches=2, tau=0.0)
    assert res.stop_reasons[0] == "early_stop_breaches"
    assert res.calls < 12 and len(res.breaches) >= 2


def test_early_stop_on_stall():
    def weak(shock):
        out = stub_engine(shock)
        out["pnl_total"] = -1.0
        return out

    c = cl.FakeClient()
    res = run_loop(c, weak, ["cold_snap"], iterations=12)
    assert res.stop_reasons[0] == "stalled" and res.calls == 2 and not res.breaches


def test_distinctness_filters_duplicates():
    sc = good()
    same = json.dumps({"scenarios": [sc, copy.deepcopy(sc)]})
    c = cl.FakeClient(responses=[same])
    res = run_loop(c, stub_engine, ["cold_snap"], iterations=1, tau=0.5, loss_target_usd=5e6)
    assert len(res.breaches) == 1 and res.accepted == 2


def test_loop_cache_hit_flag_in_log(tmp_path):
    log1, log2 = tmp_path / "1.jsonl", tmp_path / "2.jsonl"
    cache = tmp_path / "cache"
    run_loop(cl.FakeClient(cache_dir=cache), stub_engine, ["cold_snap"], iterations=1, log_path=log1, context=CTX)
    c2 = cl.FakeClient(cache_dir=cache)
    res = run_loop(c2, stub_engine, ["cold_snap"], iterations=1, log_path=log2, context=CTX)
    assert read_log(log1)[0]["cache_hit"] is False and read_log(log2)[0]["cache_hit"] is True
    assert c2.live_calls == 0 and res.cache_hits == 1 and res.input_tokens == 0


def test_engine_exception_rejects_scenario():
    def broken(shock):
        raise ValueError("boom")

    res = run_loop(cl.FakeClient(), broken, ["policy"], iterations=1)
    assert res.rejected == 3 and not res.breaches


def test_cli_dry_run_prints_prompt(capsys):
    assert main(["--dry-run", "--version", "v2", "--driver", "heat_wave"]) == 0
    out = capsys.readouterr().out
    assert "cache_key:" in out and "Driver family: heat_wave" in out and config.DEFAULT_MODEL in out


def test_loop_distinctness_uses_z_not_percentiles():
    def eng(shock):
        out = stub_engine(shock)
        out["marginals"] = {"g": 1.0, "l": 1.0}  # saturated percentiles
        out["z"] = {"g": shock["gas_hh_pct"] / 10.0, "l": 0.0, "s": 0.0, "c": 0.0, "d": 0.0}
        return out

    a, b = good(), good()
    b["shocks"] = {**b["shocks"], "gas_hh_pct": 120.0}
    c = cl.FakeClient(responses=[json.dumps({"scenarios": [a, b]})])
    res = run_loop(c, eng, ["cold_snap"], iterations=1, loss_target_usd=5e6)
    assert len(res.breaches) == 2


# ------------------------------------------------------------------ review fixes: client cache and failure handling


def test_fake_and_live_cache_do_not_mix(tmp_path):
    msgs = [{"role": "user", "content": "Driver family: cold_snap"}]
    fake = cl.FakeClient(cache_dir=tmp_path)
    fr = fake.complete("sys", msgs, "v3")
    live = cl.ClaudeClient(cache_dir=tmp_path, dry_run=True)
    lr = live.complete("sys", msgs, "v3")
    assert lr.cache_key != fr.cache_key and lr.error == "dry_run_cache_miss" and not lr.cache_hit
    entry = json.loads(fake._cache_path(fr.cache_key).read_text(encoding="utf-8"))
    assert entry["synthetic"] is True and entry["cache_kind"] == "fake"
    # even a fake entry planted under the live file name is ignored by a live client
    live._cache_path(lr.cache_key).write_text(json.dumps(entry), encoding="utf-8")
    assert not live.complete("sys", msgs, "v3").cache_hit


def test_cache_key_includes_max_tokens(tmp_path):
    msgs = [{"role": "user", "content": "Driver family: cold_snap"}]
    a = cl.FakeClient(cache_dir=tmp_path, max_tokens=100)
    b = cl.FakeClient(cache_dir=tmp_path, max_tokens=200)
    a.complete("sys", msgs, "v3")
    assert not b.complete("sys", msgs, "v3").cache_hit and b.live_calls == 1


def test_circuit_breaker_and_call_cap():
    c, _ = flaky_client([401, 401, 401, 401], max_consecutive_errors=3)
    msgs = [{"role": "user", "content": "x"}]
    for _ in range(3):
        assert c.complete("s", msgs, "v1").status_code == 401
    r = c.complete("s", msgs, "v1")
    assert r.error.startswith("circuit_open") and c.live_calls == 3 and cl.is_fatal(r)
    capped, _ = flaky_client([None, None, None], max_total_calls=2)
    assert capped.complete("s", msgs, "v1").error is None
    assert capped.complete("s", [{"role": "user", "content": "y"}], "v1").error is None
    r = capped.complete("s", [{"role": "user", "content": "z"}], "v1")
    assert r.error.startswith("max_total_calls") and capped.live_calls == 2


def test_retry_after_header_is_honored():
    class Resp:
        headers = {"retry-after": "40"}

    class Limited(Boom):
        response = Resp()

    sleeps = []
    c = cl.FakeClient(responses=["{}"], sleep=sleeps.append)
    seq = [Limited(429), None]

    def transport(system, messages):
        e = seq.pop(0)
        if e is not None:
            raise e
        return "ok", 1, 1

    c._transport = transport
    assert c.complete("s", [{"role": "user", "content": "x"}], "v1").error is None
    assert sleeps == [40.0] and cl.retry_after_s(Boom(500)) is None


@pytest.mark.parametrize("status", [400, 401, 403])
def test_loop_aborts_on_non_retryable_error(status, tmp_path):
    c, _ = flaky_client([status] * 50)
    log = tmp_path / "a.jsonl"
    res = run_loop(c, stub_engine, ["cold_snap", "heat_wave", "policy"], iterations=5, log_path=log)
    assert c.live_calls == 1 and res.calls == 1 and res.aborted and str(status) in res.aborted
    assert res.stop_reasons == {0: "aborted_fatal_error"}
    assert read_log(log)[-1]["aborted"] == res.aborted


def test_loop_aborts_on_missing_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = run_loop(cl.ClaudeClient(), stub_engine, ["cold_snap", "heat_wave"], iterations=5)
    assert res.calls == 1 and "MissingApiKeyError" in res.aborted and set(res.stop_reasons) == {0}
