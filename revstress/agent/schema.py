"""JSON Schema for the scenario object (plan section 5) and a validator with machine-readable errors.

SCENARIO_SCHEMA / RESPONSE_SCHEMA are the PJM (default market) schemas. scenario_schema(market) and
response_schema(market) build the schema of any market: NYISO uses the shock keys of plan section 5 (gas_hh_pct,
ny_gas_basis_usd, load_peak_ratio, large_load_shock_mw, ref_onpeak_pct, pocket_minus_ref_usd, dart_pct, spike_days,
spike_daily_avg_usd, duration_days), its driver classes, and a required top-level stated_loss_usd. For PJM there is no
stated_loss_usd field (PJM prompts are unchanged).
"""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator

from revstress import config
from revstress.market import Market, get_market

SEASONS: tuple[str, ...] = config.SEASONS
DRIVER_CLASSES: tuple[str, ...] = config.DRIVER_CLASSES
CONFIDENCES: tuple[str, ...] = ("low", "medium", "high")
PROMPT_VERSIONS: tuple[str, ...] = ("v1", "v2", "v3")

_NUM = {"type": "number"}

_INTEGER_SHOCKS = ("spike_days", "duration_days")


def scenario_schema(market: "str | Market | None" = None) -> dict[str, Any]:
    """JSON Schema of one scenario for the market (None: the active market, config.MARKET)."""
    m = get_market(config.MARKET if market is None else market)
    shock_props = {
        k: ({"type": "integer", "minimum": 0} if k in _INTEGER_SHOCKS else _NUM) for k in m.agent_shock_keys
    }
    required = [
        "scenario_id",
        "prompt_version",
        "narrative",
        "horizon_days",
        "season",
        "driver_class",
        "shocks",
        "analogue",
        "confidence",
    ]
    if m.name != "PJM":
        required.append("stated_loss_usd")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": {
            "scenario_id": {"type": "string", "minLength": 1},
            "prompt_version": {"type": "string", "enum": list(PROMPT_VERSIONS)},
            "narrative": {"type": "string", "minLength": 1},
            "horizon_days": {"type": "integer", "minimum": 1},
            "season": {"type": "string", "enum": list(SEASONS)},
            "driver_class": {"type": "string", "enum": list(m.driver_classes)},
            "shocks": {
                "type": "object",
                "additionalProperties": False,
                "required": list(m.agent_shock_keys),
                "properties": shock_props,
            },
            "analogue": {
                "type": "object",
                "additionalProperties": False,
                "required": ["event", "dates", "claimed", "source"],
                "properties": {
                    "event": {"type": "string"},
                    "dates": {"type": "string"},
                    "claimed": {"type": "object", "additionalProperties": _NUM},
                    "source": {"type": "string"},
                },
            },
            "confidence": {"type": "string", "enum": list(CONFIDENCES)},
        },
    }
    if m.name != "PJM":
        schema["properties"]["stated_loss_usd"] = _NUM
    return schema


def response_schema(market: "str | Market | None" = None) -> dict[str, Any]:
    """JSON Schema of the model response {"scenarios": [...]} for the market."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["scenarios"],
        "properties": {"scenarios": {"type": "array", "minItems": 1, "items": scenario_schema(market)}},
    }


SCENARIO_SCHEMA: dict[str, Any] = scenario_schema("PJM")
RESPONSE_SCHEMA: dict[str, Any] = response_schema("PJM")

_VALIDATOR = Draft202012Validator(SCENARIO_SCHEMA)
_VALIDATORS: dict[str, Draft202012Validator] = {"PJM": _VALIDATOR}


def validate_scenario(obj: Any, market: "str | Market | None" = None) -> list[dict[str, str]]:
    """Return schema errors for one scenario as dicts {path, validator, message}; empty list = valid.

    market=None validates against the active market (config.MARKET; PJM by default).
    """
    m = get_market(config.MARKET if market is None else market)
    if m.name not in _VALIDATORS:
        _VALIDATORS[m.name] = Draft202012Validator(scenario_schema(m))
    errors = []
    for err in _VALIDATORS[m.name].iter_errors(obj):
        path = "/" + "/".join(str(p) for p in err.absolute_path)
        errors.append({"path": path, "validator": str(err.validator), "message": err.message})
    return sorted(errors, key=lambda e: (e["path"], e["validator"], e["message"]))


def extract_scenarios(text: str) -> tuple[list[Any], str | None]:
    """Parse model output into a list of scenario objects.

    Accepts {"scenarios": [...]}, a bare list, or a single object, optionally in a code fence.
    Returns (scenarios, error); error is None on success.
    """
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("scenarios"), list):
            return list(obj["scenarios"]), None
        if isinstance(obj, list):
            return list(obj), None
        if isinstance(obj, dict) and "shocks" in obj:
            return [obj], None
    return [], "no_json_scenarios_found"
