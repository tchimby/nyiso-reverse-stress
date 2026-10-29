"""Hard constraints and soft penalties for proposed scenarios (plan section 5).

Hard rules reject a scenario; soft penalties only rank it down.

Agent boundary (plan section 12): the agent-facing shock keys of a market (Market.agent_shock_keys) are translated to
the engine's internal keys by to_engine_shocks. Documented mapping for NYISO: ref_onpeak_pct == wh_onpeak_pct,
pocket_minus_ref_usd == dom_minus_wh_usd, large_load_shock_mw == dc_load_shock_mw (PJM keys are unchanged).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from revstress import config
from revstress.eval.analogues import analogue_table, normalise_event
from revstress.market import Market, get_market

ANALOGUE_TOLERANCE: float = 0.30
Q_SOFT_MIN: float = 0.001
NARRATIVE_MIN_WORDS: int = 40
CLASS_USE_LIMIT: int = 3

AnalogueTable = Mapping[str, Mapping[str, "float | None"]]

# Single source of truth: eval.analogues.ANALOGUES (plan sections 6 and 8; None rows are omitted).
# This constant is the PJM table (default market); default_analogue_table(market) gives the table of any market.
DEFAULT_ANALOGUE_TABLE: dict[str, dict[str, float | None]] = {k: dict(v) for k, v in analogue_table("PJM").items()}

SHOCK_MAPPING_LINE = (
    "Shock key mapping (agent key = internal key): ref_onpeak_pct = wh_onpeak_pct (WEST on-peak move), "
    "pocket_minus_ref_usd = dom_minus_wh_usd (N.Y.C. minus WEST, $/MWh), large_load_shock_mw = dc_load_shock_mw."
)


def resolve_market(market: "str | Market | None" = None) -> Market:
    """Market argument, else the active market (config.MARKET)."""
    return get_market(config.MARKET if market is None else market)


def default_analogue_table(market: "str | Market | None" = None) -> dict[str, dict[str, float | None]]:
    """Analogue table of the market (rows with no verified number are omitted)."""
    return {k: dict(v) for k, v in analogue_table(resolve_market(market)).items()}


def to_engine_shocks(shocks: Mapping[str, Any], market: "str | Market | None" = None) -> dict[str, Any]:
    """Agent shock keys to the engine's internal keys; keys unknown to the market pass through unchanged."""
    amap = resolve_market(market).agent_to_engine
    return {amap.get(k, k): v for k, v in shocks.items()}


def to_agent_shocks(shocks: Mapping[str, Any], market: "str | Market | None" = None) -> dict[str, Any]:
    """Engine shock keys to the agent-facing keys of the market (inverse of to_engine_shocks)."""
    emap = resolve_market(market).engine_to_agent
    return {emap.get(k, k): v for k, v in shocks.items()}


@dataclass(frozen=True)
class Verdict:
    """Outcome of one rule. `hard` rules reject; soft rules carry a penalty (0 when passed)."""

    rule: str
    passed: bool
    hard: bool
    detail: str = ""
    penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def _get(d: Any, key: str) -> Any:
    return d.get(key) if isinstance(d, Mapping) else None


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def lookup_event(table: AnalogueTable, event: str, market: "str | Market | None" = None) -> str | None:
    """Return the table key matching `event`, else None.

    Matches by case-insensitive equality or containment of the table key, or by the shared alias map
    (eval.analogues.normalise_event), so 'Elliott', 'Dec 2022' or 'Jan 2014' resolve like the full names.
    """
    e = _norm(event)
    if not e:
        return None
    for key in table:
        k = _norm(key)
        if e == k or k in e:
            return key
    canon = normalise_event(event, market)
    for key in table:
        if normalise_event(key, market) == canon:
            return key
    return None


def _rule_enums(s: Mapping[str, Any], m: Market) -> Verdict:
    bad = []
    if s.get("season") not in config.SEASONS:
        bad.append("season")
    if s.get("driver_class") not in m.driver_classes:
        bad.append("driver_class")
    if s.get("confidence") not in ("low", "medium", "high"):
        bad.append("confidence")
    return Verdict("valid_enums", not bad, True, ",".join(bad))


def _rule_shock_values(shocks: Any, m: Market) -> Verdict:
    if not isinstance(shocks, Mapping):
        return Verdict("shock_values_valid", False, True, "shocks_missing")
    keys = m.agent_shock_keys
    bad = [k for k in keys if _num(shocks.get(k)) is None]
    bad += [k for k in shocks if k not in keys]
    if not bad:
        if shocks["load_peak_ratio"] <= 0:
            bad.append("load_peak_ratio<=0")
        for k in ("gas_hh_pct", m.engine_to_agent["wh_onpeak_pct"], "dart_pct"):
            if shocks[k] <= -100:
                bad.append(f"{k}<=-100")
        if shocks["spike_daily_avg_usd"] < 0:
            bad.append("spike_daily_avg_usd<0")
        if shocks["spike_days"] < 0 or shocks["duration_days"] < 0:
            bad.append("negative_days")
    return Verdict("shock_values_valid", not bad, True, ",".join(bad))


def _rule_energy_cap(shocks: Mapping[str, Any], m: Market) -> Verdict:
    v = _num(shocks.get("spike_daily_avg_usd")) or 0.0
    cap = m.energy_cap_usd
    return Verdict(m.cap_rule_name, v <= cap, True, f"spike_daily_avg_usd={v:g} cap={cap:g}")


def _rule_duration(s: Mapping[str, Any], shocks: Mapping[str, Any]) -> Verdict:
    d, h = _num(shocks.get("duration_days")), _num(s.get("horizon_days"))
    if d is None or h is None:
        return Verdict("duration_within_horizon", False, True, "missing")
    return Verdict("duration_within_horizon", d <= h, True, f"duration={d:g} horizon={h:g}")


def _rule_spike_consistency(shocks: Mapping[str, Any]) -> Verdict:
    n, avg, dur = (_num(shocks.get(k)) for k in ("spike_days", "spike_daily_avg_usd", "duration_days"))
    if n is None or avg is None or dur is None:
        return Verdict("spike_consistent", False, True, "missing")
    problems = []
    if n > dur:
        problems.append("spike_days>duration_days")
    if n > 0 and avg <= 0:
        problems.append("spike_days>0_but_avg<=0")
    if n == 0 and avg > 0:
        problems.append("avg>0_but_spike_days=0")
    return Verdict("spike_consistent", not problems, True, ",".join(problems))


def _rule_sign_consistency(s: Mapping[str, Any], shocks: Mapping[str, Any], m: Market) -> Verdict:
    cls = s.get("driver_class")
    ratio = _num(shocks.get("load_peak_ratio"))
    gas = _num(shocks.get("gas_hh_pct"))
    problems = []
    if cls in ("cold_snap", "heat_wave") and ratio is not None and ratio < 1.0:
        problems.append(f"{cls}_with_load_down")
    if cls in ("cold_snap", "gas_supply") and gas is not None and gas < 0:
        problems.append(f"{cls}_with_gas_down")
    ll = _num(shocks.get(m.engine_to_agent["dc_load_shock_mw"]))
    if cls == "large_load_shortfall" and ll is not None and ll > 0:
        problems.append("large_load_shortfall_with_load_up")
    if cls == "cold_snap" and s.get("season") == "summer":
        problems.append("cold_snap_in_summer")
    if cls == "heat_wave" and s.get("season") == "winter":
        problems.append("heat_wave_in_winter")
    return Verdict("sign_consistent", not problems, True, ",".join(problems))


def _rule_analogue(s: Mapping[str, Any], table: AnalogueTable, tol: float, m: Market | None = None) -> Verdict:
    an = s.get("analogue")
    event = _get(an, "event")
    claimed = _get(an, "claimed")
    if not isinstance(an, Mapping) or not isinstance(claimed, Mapping):
        return Verdict("analogue_matches_table", False, True, "analogue_missing")
    if not (isinstance(event, str) and event.strip()):
        if claimed:
            return Verdict("analogue_matches_table", False, True, "fabricated_analogue: claimed numbers without an event")
        return Verdict("analogue_matches_table", True, True, "no_analogue")
    key = lookup_event(table, event, m)
    if key is None:
        return Verdict("analogue_matches_table", False, True, f"fabricated_analogue: event not in table: {event}")
    bad = []
    for metric, val in claimed.items():
        c, t = _num(val), table[key].get(metric)
        if c is None:
            bad.append(f"{metric}:non_numeric")
        elif t is None:
            bad.append(f"{metric}:not_in_table")
        elif abs(c - t) > tol * abs(t):
            bad.append(f"{metric}:claimed={c:g} table={t:g}")
    if bad:
        return Verdict("analogue_matches_table", False, True, "fabricated_analogue: " + ";".join(bad))
    return Verdict("analogue_matches_table", True, True, key)


def check_hard_rules(
    scenario: Any,
    analogue_table: AnalogueTable | None = None,
    tol: float = ANALOGUE_TOLERANCE,
    market: "str | Market | None" = None,
) -> list[Verdict]:
    """Evaluate all hard constraints; the scenario is accepted only if every hard verdict passed.

    market=None means the active market (config.MARKET; PJM by default). Shock keys are the market's agent keys.
    """
    m = resolve_market(market)
    table = default_analogue_table(m) if analogue_table is None else analogue_table
    if not isinstance(scenario, Mapping):
        return [Verdict("scenario_is_object", False, True, "not_an_object")]
    out = [_rule_enums(scenario, m), _rule_shock_values(scenario.get("shocks"), m)]
    if out[1].passed:
        sh = scenario["shocks"]
        out += [
            _rule_energy_cap(sh, m),
            _rule_duration(scenario, sh),
            _rule_spike_consistency(sh),
            _rule_sign_consistency(scenario, sh, m),
        ]
    out.append(_rule_analogue(scenario, table, tol, m))
    return out


def hard_pass(verdicts: Sequence[Verdict]) -> bool:
    return all(v.passed for v in verdicts if v.hard)


def is_fabricated(verdicts: Sequence[Verdict]) -> bool:
    """True when the analogue rule failed (logged as a fabricated-analogue event)."""
    return any(v.rule == "analogue_matches_table" and not v.passed for v in verdicts)


def soft_penalties(
    scenario: Mapping[str, Any],
    engine_out: Mapping[str, Any] | None,
    accepted_class_counts: Mapping[str, int] | None = None,
) -> list[Verdict]:
    """Soft rules; a failed one carries penalty 1.0. Engine rules are skipped when the field is absent.

    Uses engine_out['q'] and optionally engine_out['nn_distance'] and ['nn_distance_max'].
    """
    out: list[Verdict] = []
    eng = engine_out or {}
    q = _num(eng.get("q"))
    if q is not None:
        ok = q >= Q_SOFT_MIN
        out.append(Verdict("q_not_too_small", ok, False, f"q={q:g}", 0.0 if ok else 1.0))
    d, dmax = _num(eng.get("nn_distance")), _num(eng.get("nn_distance_max"))
    if d is not None and dmax is not None:
        ok = d <= dmax
        out.append(Verdict("nn_distance_within_history", ok, False, f"d={d:g} max={dmax:g}", 0.0 if ok else 1.0))
    words = len(str(scenario.get("narrative", "")).split())
    ok = words >= NARRATIVE_MIN_WORDS
    out.append(Verdict("narrative_length", ok, False, f"words={words}", 0.0 if ok else 1.0))
    used = (accepted_class_counts or {}).get(str(scenario.get("driver_class")), 0)
    ok = used < CLASS_USE_LIMIT
    out.append(Verdict("driver_class_not_overused", ok, False, f"accepted_so_far={used}", 0.0 if ok else 1.0))
    return out


def total_penalty(verdicts: Sequence[Verdict]) -> float:
    return float(sum(v.penalty for v in verdicts))
