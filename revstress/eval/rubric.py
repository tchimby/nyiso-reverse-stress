"""Pre-registered five-item coherence rubric (plan section 8B) and inter-rater agreement.

Each item scores 0 or 1. Mechanical checks run first and return 0 (fail), 1 (pass) or None (cannot be
decided by code, a human must judge). A mechanical 0 caps the item at 0; otherwise a human score, if
given, is used; otherwise a mechanical 1 stands; otherwise the item is unscored (None).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .. import config
from .analogues import score_analogue

ITEMS: tuple[str, ...] = (
    "causal_chain",
    "shocks_explained",
    "duration_matches",
    "analogue_correct_relevant",
    "no_contradiction",
)
MIN_NARRATIVE_WORDS = 40  # plan section 5 soft penalty

SHOCK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gas_hh_pct": ("gas", "henry"),
    "load_peak_ratio": ("load", "demand", "consumption"),
    "dc_load_shock_mw": ("data center", "data-center", "datacenter", "large load", "large-load"),
    "wh_onpeak_pct": ("price", "western hub", "west", "on-peak", "offer"),
    "dom_minus_wh_usd": ("dominion", "n.y.c.", "new york city", "congestion", "spread"),
    "dart_pct": ("real-time", "real time", "day-ahead", "day ahead", "da-rt", "dart"),
    "spike_days": ("spike", "scarcity", "shortage"),
}
_WORDS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty".split()
    )
}
_DAYS = re.compile(r"(\d+|" + "|".join(_WORDS) + r")[\s-]*(?:consecutive\s+)?days?\b", re.IGNORECASE)


@dataclass(frozen=True)
class RubricResult:
    """Rubric outcome for one scenario. items/mechanical map item name -> 0, 1 or None (unscored)."""

    items: dict[str, int | None]
    mechanical: dict[str, int | None]

    @property
    def complete(self) -> bool:
        """True when all five items are scored."""
        return all(v is not None for v in self.items.values())

    @property
    def total(self) -> float | None:
        """Mean of the five items in [0, 1]; None until all are scored."""
        return float(np.mean(list(self.items.values()))) if self.complete else None


def _nonzero(shock: Mapping[str, float], key: str) -> bool:
    return float(shock.get(key, config.NEUTRAL_SHOCK[key])) != float(config.NEUTRAL_SHOCK[key])


def _check_causal(scn: Mapping) -> int | None:
    words = len(str(scn.get("narrative", "")).split())
    return 0 if words < MIN_NARRATIVE_WORDS else None


def _check_explained(scn: Mapping) -> int | None:
    text = str(scn.get("narrative", "")).lower()
    shock = scn.get("shocks", {})
    for key, words in SHOCK_KEYWORDS.items():
        if _nonzero(shock, key) and not any(w in text for w in words):
            return 0
    return 1


def _check_duration(scn: Mapping) -> int | None:
    shock = scn.get("shocks", {})
    duration = shock.get("duration_days", 0)
    if shock.get("spike_days", 0) > duration or duration > scn.get("horizon_days", duration):
        return 0
    mentioned = {int(m) if m.isdigit() else _WORDS[m.lower()] for m in _DAYS.findall(str(scn.get("narrative", "")))}
    if not mentioned:
        return None
    return 1 if duration in mentioned else 0


def _check_analogue(scn: Mapping) -> int | None:
    analogue = scn.get("analogue") or {}
    if not analogue.get("event"):
        return None
    scores = score_analogue(analogue)
    if any(s in ("wrong", "not_in_table") for s in scores.values()):
        return 0
    return None


def _check_contradiction(scn: Mapping) -> int | None:
    shock, driver = scn.get("shocks", {}), scn.get("driver_class", "")
    text = str(scn.get("narrative", "")).lower()
    load, gas = shock.get("load_peak_ratio", 1.0), shock.get("gas_hh_pct", 0.0)
    bad = (
        (driver in ("cold_snap", "heat_wave") and load < 1.0)
        or (driver == "cold_snap" and gas < 0.0)
        or (driver == "gas_supply" and gas <= 0.0)
        or (driver == "demand_shock_datacenter" and shock.get("dc_load_shock_mw", 0.0) <= 0.0)
        or ("cold" in text and load < 1.0)
        or ("heat wave" in text and load < 1.0)
        or (shock.get("spike_days", 0) > 0 and shock.get("spike_daily_avg_usd", 0.0) <= 0.0)
    )
    return 0 if bad else None


MECHANICAL_CHECKS = {
    "causal_chain": _check_causal,
    "shocks_explained": _check_explained,
    "duration_matches": _check_duration,
    "analogue_correct_relevant": _check_analogue,
    "no_contradiction": _check_contradiction,
}


def mechanical_checks(scenario: Mapping) -> dict[str, int | None]:
    """Automated part of the rubric for a scenario dict (narrative, shocks, driver_class, analogue, horizon_days)."""
    return {item: fn(scenario) for item, fn in MECHANICAL_CHECKS.items()}


def score_scenario(scenario: Mapping, human: Mapping[str, int | None] | None = None) -> RubricResult:
    """Combine mechanical checks with one rater's human scores (item -> 0/1/None)."""
    mech = mechanical_checks(scenario)
    human = human or {}
    items: dict[str, int | None] = {}
    for item in ITEMS:
        if mech[item] == 0:
            items[item] = 0
        elif human.get(item) is not None:
            items[item] = int(human[item])
        else:
            items[item] = mech[item]
    return RubricResult(items=items, mechanical=mech)


def percent_agreement(a: Sequence, b: Sequence) -> float:
    """Share of positions where two raters give the same label."""
    if len(a) != len(b) or not len(a):
        raise ValueError("ratings must be non-empty and of equal length")
    return float(np.mean([x == y for x, y in zip(a, b)]))


def cohen_kappa(a: Sequence, b: Sequence) -> float:
    """Cohen's kappa for two raters on categorical labels: (po - pe)/(1 - pe).

    If pe = 1 (both raters use one identical label throughout) returns 1.0.
    """
    if len(a) != len(b) or not len(a):
        raise ValueError("ratings must be non-empty and of equal length")
    labels = sorted(set(a) | set(b), key=str)
    n = len(a)
    po = percent_agreement(a, b)
    pe = sum((sum(x == lab for x in a) / n) * (sum(y == lab for y in b) / n) for lab in labels)
    return 1.0 if pe >= 1.0 else float((po - pe) / (1.0 - pe))


def rater_agreement(r1: Sequence[RubricResult], r2: Sequence[RubricResult]) -> dict[str, dict[str, float]]:
    """Per-item and pooled percent agreement and kappa over scenarios scored (complete) by both raters."""
    pairs = [(x, y) for x, y in zip(r1, r2) if x.complete and y.complete]
    if not pairs:
        raise ValueError("no scenarios scored by both raters")
    out: dict[str, dict[str, float]] = {}
    for item in ITEMS:
        a, b = [x.items[item] for x, _ in pairs], [y.items[item] for _, y in pairs]
        out[item] = {"agreement": percent_agreement(a, b), "kappa": cohen_kappa(a, b)}
    pa = [x.items[i] for x, _ in pairs for i in ITEMS]
    pb = [y.items[i] for _, y in pairs for i in ITEMS]
    out["pooled"] = {"agreement": percent_agreement(pa, pb), "kappa": cohen_kappa(pa, pb), "n_scenarios": float(len(pairs))}
    return out


def blind_order(records: Sequence[Mapping], seed: int) -> tuple[list[dict], dict[str, str]]:
    """Shuffle records for blind grading: returns (rater view without arm, key blind_id -> scenario_id)."""
    order = np.random.default_rng(seed).permutation(len(records))
    view, key = [], {}
    for rank, idx in enumerate(order):
        r = records[int(idx)]
        bid = f"B-{rank + 1:03d}"
        key[bid] = str(r.get("scenario_id", idx))
        view.append({k: r.get(k) for k in ("narrative", "shocks", "driver_class", "horizon_days", "analogue")} | {"blind_id": bid})
    return view, key
