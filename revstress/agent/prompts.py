"""Prompt construction (plan section 5) with the seven-part anatomy.

Parts: role (system message), task, inputs, constraints, method, output format, quality criteria.
v1 = no schema; v2 = schema + enums; v3 = schema + analogue table + engine feedback.
Functions take market=None (the active market, config.MARKET; PJM by default, so PJM prompts are unchanged).
For NYISO the role, cap line, shock keys, mapping line, large-load ranges and analogue table follow plan sections 5, 6, 8.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from revstress import config
from revstress.agent.rules import DEFAULT_ANALOGUE_TABLE, SHOCK_MAPPING_LINE, AnalogueTable, default_analogue_table, resolve_market
from revstress.agent.schema import RESPONSE_SCHEMA, response_schema
from revstress.market import Market

PROMPT_V1 = "v1"
PROMPT_V2 = "v2"
PROMPT_V3 = "v3"
PROMPT_VERSIONS: tuple[str, ...] = (PROMPT_V1, PROMPT_V2, PROMPT_V3)

ROLE = (
    "You are a risk analyst designing reverse stress tests for a PJM power book. "
    "You propose coherent, physically consistent market scenarios that cause large losses to the book. "
    "You report only numbers you can support and say so when you are unsure."
)

NYISO_ROLE = (
    "You are a risk analyst designing reverse stress tests for a NYISO power book. The reference zone is WEST "
    "(upstate) and the load pocket is N.Y.C. (Zone J); the NYCA system peaks at about 30 GW. "
    "You propose coherent, physically consistent market scenarios that cause large losses to the book. "
    "You report only numbers you can support and say so when you are unsure."
)


def role_text(market: "str | Market | None" = None) -> str:
    """System-message role text of the market (PJM: ROLE)."""
    return ROLE if resolve_market(market).name == "PJM" else NYISO_ROLE


DRIVER_FAMILY_LINE = "Driver family:"


def json_dumps(obj: Any) -> str:
    """Stable JSON text (sorted keys) used in prompts."""
    return json.dumps(obj, sort_keys=True, indent=1, default=str)


def prompt_hash(system: str, messages: Sequence[Mapping[str, str]]) -> str:
    """sha256 hex digest of the exact prompt text."""
    return hashlib.sha256(json.dumps([system, list(messages)], sort_keys=True).encode()).hexdigest()


def _task(version: str, driver_class: str, season: str | None, n: int, target_usd: float, include_target: bool = True) -> str:
    season_txt = f"Season: {season}\n" if season else ""
    loss_txt = f"at least ${target_usd:,.0f}" if include_target else "a large loss, as severe as you can justify"
    return (
        "TASK\n"
        f"Propose {n} distinct stress scenarios over a horizon of at most 30 days in which the book below loses "
        f"{loss_txt} (a loss means negative total P&L).\n"
        f"{DRIVER_FAMILY_LINE} {driver_class}\n{season_txt}"
    )


def _inputs(version: str, context: Mapping[str, Any], analogue_table: AnalogueTable | None, m: Market | None = None) -> str:
    m = resolve_market(m)
    parts = ["INPUTS", "Context (units: prices $/MWh, gas $/MMBtu, power MW, time days):", json_dumps(dict(context))]
    if m.large_load_ranges:
        parts += [
            "Large-load shock ranges, MW (stated scenario ranges around the Gold Book, not forecasts):",
            json_dumps(m.large_load_ranges),
        ]
    if version == PROMPT_V3:
        table = default_analogue_table(m) if analogue_table is None else analogue_table
        parts += [
            "Analogue table (the only analogue numbers you may cite; a metric that is not listed is not available; cite event and metric names exactly):",
            json_dumps(dict(table)),
        ]
    return "\n".join(parts)


def _constraints(version: str, m: Market | None = None) -> str:
    m = resolve_market(m)
    if m.cap_is_assumption:
        cap_line = (
            f"Hourly prices are clipped at a scenario cap of ${m.energy_cap_usd:,.0f}/MWh (a stated assumption of this "
            "exercise, not a NYISO rule); spike_daily_avg_usd is a daily on-peak average, so it also cannot exceed this."
        )
    else:
        cap_line = (
            f"The energy component of price cannot exceed ${m.energy_cap_usd:,.0f}/MWh; "
            "spike_daily_avg_usd is a daily on-peak average, so it also cannot exceed this."
        )
    base = [
        cap_line,
        "duration_days cannot exceed horizon_days; spike_days cannot exceed duration_days.",
        "spike_daily_avg_usd must be 0 when spike_days is 0 and positive otherwise.",
        "Shocks must be directionally consistent with the driver class (a cold snap raises load and gas, "
        "a heat wave raises load).",
    ]
    if m.name != "PJM":
        base.append(SHOCK_MAPPING_LINE)
        base.append(
            "Set stated_loss_usd to your own estimate of the book loss in USD (a number); it is compared with the "
            "engine's loss."
        )
    if version == PROMPT_V1:
        base.append("Give numbers, not ranges.")
    else:
        base.append("Use numbers only (no ranges, no strings) for every shock. Use only the allowed enum values.")
    if version == PROMPT_V3:
        base.append(
            "If you cite an analogue, every claimed number must come from the analogue table and be within 30% "
            "of it. If no table entry fits, leave the analogue event empty and set confidence to low."
        )
    return "CONSTRAINTS\n" + "\n".join(f"- {c}" for c in base)


def _method(version: str, include_target: bool = True) -> str:
    steps = [
        "State the causal chain from the physical driver to prices to the book's P&L.",
        "Choose shock sizes that are extreme but plausible, and keep them mutually consistent.",
        "Use different channels (system level, congestion, day-ahead vs real-time, gas, zone volume, tail) "
        "across your scenarios.",
    ]
    if version != PROMPT_V1:
        steps.append(
            "If the context has a 'book' table, read it with 'book_summary' and 'shock_glossary': pick shocks that hurt the "
            "positions that lose money (not shocks that only raise prices and gas, which make long positions gain), use "
            "'shock_sensitivities' (if present) to see which shock moves which position and by how much, and stay inside "
            "'shock_ceilings_by_season' (beyond implausible_above or below implausible_below a scenario is classed implausible)."
        )
        steps.append("Use the given driver family as driver_class and the given season as season in every scenario.")
        steps.append(
            "Signs must match the driver family (hard rule sign_consistent): for large_load_shortfall, large_load_shock_mw must be "
            "zero or negative and load_peak_ratio at most 1.0; for cold_snap and heat_wave, load_peak_ratio at least 1.0; for "
            "cold_snap and gas_supply, gas_hh_pct at least 0."
        )
    if version == PROMPT_V3:
        goal = "scenarios that breach the loss target" if include_target else "scenarios with a large loss"
        steps.append(
            "After each round you will receive engine numbers and rule verdicts only. Move shocks toward "
            f"{goal} with the smallest historical implausibility (small D^2, q at "
            "least 0.1%) and change direction when a rule fails."
        )
    return "METHOD\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def _output_format(version: str, m: Market | None = None) -> str:
    m = resolve_market(m)
    if version == PROMPT_V1:
        return (
            "OUTPUT FORMAT\nReturn JSON only, with a list of scenarios under the key \"scenarios\". Each scenario "
            "has an id, a narrative, a horizon in days, a season, a driver class, numeric shocks "
            f"({', '.join(m.agent_shock_keys)}), an optional historical analogue, and a confidence level."
        )
    return (
        "OUTPUT FORMAT\nReturn JSON only (no prose, no code fence) matching this JSON Schema exactly. "
        f"Set prompt_version to \"{version}\".\n" + json_dumps(RESPONSE_SCHEMA if m.name == "PJM" else response_schema(m))
    )


def _quality(version: str) -> str:
    items = [
        "Every non-zero shock is explained in the narrative (at least 40 words).",
        "The duration matches the narrative.",
        "Scenarios differ in driver class mix, magnitude and channel, not only in scale.",
    ]
    if version == PROMPT_V3:
        items.append("Cited analogues are relevant and correctly quoted.")
    return "QUALITY CRITERIA\n" + "\n".join(f"- {i}" for i in items)


def build_seed_prompt(
    version: str,
    context: Mapping[str, Any],
    driver_class: str,
    season: str | None = None,
    scenarios_per_call: int = config.SCENARIOS_PER_CALL,
    analogue_table: AnalogueTable | None = None,
    target_loss_usd: float = config.LOSS_TARGET_USD,
    market: "str | Market | None" = None,
    include_loss_target: bool = True,
) -> tuple[str, list[dict[str, str]]]:
    """Return (system, messages) for the first call of a seed. Role is the system message.

    include_loss_target=False is the severity-anchoring ablation arm: the prompt never states the dollar target
    (target_loss_usd is then unused in the text); everything else is identical to the default arm.
    """
    if version not in PROMPT_VERSIONS:
        raise ValueError(f"unknown prompt version: {version}")
    m = resolve_market(market)
    user = "\n\n".join(
        [
            _task(version, driver_class, season, scenarios_per_call, target_loss_usd, include_loss_target),
            _inputs(version, context, analogue_table, m),
            _constraints(version, m),
            _method(version, include_loss_target),
            _output_format(version, m),
            _quality(version),
        ]
    )
    return role_text(m), [{"role": "user", "content": user}]


def _fmt(x: Any) -> str:
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, float):
        return f"{x:.6g}"
    if isinstance(x, Mapping):
        return "{" + ", ".join(f"{k}: {_fmt(v)}" for k, v in x.items()) + "}"
    if isinstance(x, (list, tuple)):
        return "[" + ", ".join(_fmt(v) for v in x) + "]"
    return str(x)


ENGINE_FIELDS: tuple[str, ...] = (
    "pnl_total",
    "pnl_by_position",
    "pnl_by_channel",
    "d2",
    "q",
    "marginals",
    "nearest_date",
    "severity",
    "spike_exceedance",
    "headroom",
)


def build_feedback_message(
    results: Sequence[Mapping[str, Any]],
    scenarios_per_call: int = config.SCENARIOS_PER_CALL,
    include_engine: bool = True,
    breaches_so_far: int = 0,
    target_loss_usd: float = config.LOSS_TARGET_USD,
    include_loss_target: bool = True,
) -> str:
    """Feedback for the next turn: numbers and rule verdicts only, no engine narrative.

    include_loss_target=False (ablation arm) omits the dollar target and the breach counter, which would reveal it.

    Each result is {scenario_id, verdicts: [verdict dicts], engine: dict | None, loss_usd: float | None}.
    With include_engine=False (v1, v2) only the instruction to propose new scenarios is sent.
    """
    lines = ["RESULTS"]
    if include_engine:
        for r in results:
            lines.append(f"scenario {r.get('scenario_id')}:")
            lines.append(f"  loss_usd: {_fmt(r.get('loss_usd'))}")
            eng = r.get("engine") or {}
            for k in ENGINE_FIELDS:
                if k in eng:
                    lines.append(f"  {k}: {_fmt(eng[k])}")
            for v in r.get("verdicts", []):
                if v.get("hard"):
                    lines.append(f"  rule {v['rule']}: {'PASS' if v['passed'] else 'FAIL'} {v.get('detail', '')}".rstrip())
            if not eng:
                lines.append("  engine: not run (scenario rejected)")
        if include_loss_target:
            lines.append(f"breaching scenarios found so far: {breaches_so_far}")
    else:
        lines.append("Previous scenario ids: " + ", ".join(str(r.get("scenario_id")) for r in results))
    loss_txt = f"loss of at least ${target_loss_usd:,.0f}" if include_loss_target else "a large loss"
    lines.append(
        f"Propose {scenarios_per_call} new scenarios with {loss_txt} that differ from "
        "all previous ones. Return JSON only, in the same format as before."
    )
    return "\n".join(lines)
