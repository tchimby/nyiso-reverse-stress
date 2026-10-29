"""Agent loop (plan section 5): propose with Claude, evaluate with an injected engine, give numeric feedback.

engine_fn(shock_dict) -> dict (or engine_fn(shock_dict, season=...) if it has attribute takes_season=True) with pnl_total, pnl_by_position, pnl_by_channel, d2, q, marginals,
nearest_date, severity, spike_exceedance (optional: headroom, nn_distance, nn_distance_max).
Loss = -pnl_total (USD). Stop rules apply per seed: early_stop_breaches distinct breaches, or
stall_limit consecutive iterations adding none, or the iteration budget.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from revstress import config
from revstress.agent import client as client_mod
from revstress.agent import prompts, rules, schema
from revstress.eval import metrics as eval_metrics
from revstress.factorspace import z_vector
from revstress.market import Market

EngineFn = Callable[[dict[str, float]], dict[str, Any]]
DistanceFn = Callable[[Mapping[str, Any], Mapping[str, Any]], float]

_NYISO_DRIVERS: tuple[str, ...] = rules.resolve_market("NYISO").driver_classes
DEFAULT_TAU: float = config.DISTINCT_TAU_Z
DEFAULT_STALL_LIMIT: int = 2


@dataclass
class Breach:
    """A distinct breaching scenario that passed all hard rules."""

    scenario: dict[str, Any]
    engine: dict[str, Any]
    loss_usd: float
    penalty: float
    seed_index: int
    iteration: int


@dataclass
class LoopResult:
    breaches: list[Breach] = field(default_factory=list)  # ranked: lowest penalty, then largest loss
    accepted: int = 0
    rejected: int = 0
    fabricated_analogues: int = 0
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reasons: dict[int, str] = field(default_factory=dict)
    aborted: str | None = None  # error text of a non-retryable failure that stopped the whole run
    log_path: str | None = None
    scenario_records: list[dict[str, Any]] = field(default_factory=list)  # one per proposed scenario (the log's scenario dicts)
    include_loss_target: bool = True

    def gate_stats(self) -> dict[str, Any]:
        """Per-rule rejection counts and rates (eval.metrics.gate_rejection_stats) over this run's scenarios."""
        return eval_metrics.gate_rejection_stats(self.scenario_records)


def factor_vector(engine_out: Mapping[str, Any], shocks: Mapping[str, Any]) -> list[float]:
    """Point in factor space: the engine's standardized core factors z (same as eval.metrics), else the shock vector.

    The shock-vector fallback is only for engines that report no 'z' (mixed units; tests and stubs).
    """
    z = z_vector(engine_out)
    if z is not None:
        return [float(v) for v in z]
    return [float(shocks[k]) for k in config.SHOCK_KEYS]


def euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _jsonable(o: Any) -> Any:
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "tolist"):
        return o.tolist()
    return str(o)


class _Log:
    def __init__(self, path: str | Path | None) -> None:
        self.path = None if path is None else Path(path)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, rec: Mapping[str, Any]) -> None:
        if self.path is None:
            return
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=_jsonable) + "\n")


def _seed_fields(seed: str | Mapping[str, Any]) -> tuple[str, str | None]:
    if isinstance(seed, str):
        return seed, None
    return str(seed["driver_class"]), seed.get("season")


def run_loop(
    client: client_mod.ClaudeClient,
    engine_fn: EngineFn,
    seeds: Sequence[str | Mapping[str, Any]],
    iterations: int = config.ITERATIONS_PER_SEED,
    scenarios_per_call: int = config.SCENARIOS_PER_CALL,
    *,
    prompt_version: str = prompts.PROMPT_V3,
    context: Mapping[str, Any] | None = None,
    analogue_table: rules.AnalogueTable | None = None,
    log_path: str | Path | None = None,
    run_id: str = "run",
    loss_target_usd: float = config.LOSS_TARGET_USD,
    q_max: float = config.Q_ADVERSE_MAX,
    early_stop_breaches: int = config.EARLY_STOP_BREACHES,
    stall_limit: int = DEFAULT_STALL_LIMIT,
    tau: float = DEFAULT_TAU,
    distance_fn: DistanceFn | None = None,
    market: "str | Market | None" = None,
    include_loss_target: bool = True,
) -> LoopResult:
    """Run the loop for each seed (driver family, optionally with a season) and return ranked breaches.

    A breach has loss >= loss_target_usd, q < q_max, passes all hard rules, and lies farther than tau
    (distance_fn, default Euclidean in factor_vector space) from every earlier breach in the run.
    Rejected scenarios (schema or hard-rule failures) are not sent to the engine; their verdicts are fed back.
    A non-retryable client failure (400/401/403, missing key, open circuit breaker, call cap; see
    client.is_fatal) aborts the whole run: res.aborted holds the error and later seeds are not started.
    include_loss_target=False is the severity-anchoring ablation arm: the prompts never state the dollar target
    (loss_target_usd still defines a breach); see run_target_ablation. market=None means the active market
    (config.MARKET). Scenario shocks use the market's agent keys and are translated
    to the engine's internal keys (rules.to_engine_shocks) before engine_fn is called.
    """
    log = _Log(log_path)
    client_kind = getattr(client, "cache_kind", "live")
    label = client_mod.FAKE_CLIENT_LABEL if client_kind == "fake" else "LIVE CLAUDE"
    mkt = rules.resolve_market(market)
    res = LoopResult(log_path=None if log_path is None else str(log_path), include_loss_target=include_loss_target)
    ctx = dict(context or {})
    vectors: list[list[float]] = []
    class_counts: dict[str, int] = {}
    use_engine_feedback = prompt_version == prompts.PROMPT_V3
    dist = distance_fn or (lambda a, b: euclidean(a["vec"], b["vec"]))

    for si, seed in enumerate(seeds):
        driver, season = _seed_fields(seed)
        system, messages = prompts.build_seed_prompt(
            prompt_version, ctx, driver, season, scenarios_per_call, analogue_table, loss_target_usd, mkt,
            include_loss_target,
        )
        seed_breaches = 0
        stall = 0
        reason = "iteration_budget"
        for it in range(iterations):
            resp = client.complete(system, messages, prompt_version)
            res.calls += 1
            res.cache_hits += int(resp.cache_hit)
            if not resp.cache_hit:
                res.input_tokens += resp.input_tokens
                res.output_tokens += resp.output_tokens
            rec: dict[str, Any] = {
                "event": "call",
                "run_id": run_id,
                "seed_index": si,
                "driver_class": driver,
                "iteration": it,
                "prompt_version": prompt_version,
                "prompt_hash": prompts.prompt_hash(system, messages),
                "include_loss_target": include_loss_target,
                "cache_key": resp.cache_key,
                "model": resp.model,
                "client_kind": client_kind,
                "label": label,
                "messages_in": list(messages),
                "system": system,
                "response_text": resp.text,
                "cache_hit": resp.cache_hit,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "attempts": resp.attempts,
                "stop_reason": resp.stop_reason,
                "error": resp.error,
                "scenarios": [],
            }
            added = 0
            fb: list[dict[str, Any]] = []
            if resp.error is None:
                parsed, perr = schema.extract_scenarios(resp.text)
                rec["parse_error"] = perr
                for sc in parsed[:scenarios_per_call]:
                    srec, fbrec, breach = _evaluate(
                        sc, engine_fn, analogue_table, class_counts, vectors, dist, tau,
                        loss_target_usd, q_max, si, it, mkt,
                    )
                    srec["prompt_version"] = prompt_version
                    srec["seed_index"] = si
                    srec["iteration"] = it
                    srec["stated_loss_usd"] = sc.get("stated_loss_usd") if isinstance(sc, Mapping) else None
                    rec["scenarios"].append(srec)
                    res.scenario_records.append(srec)
                    fb.append(fbrec)
                    if srec["accepted"]:
                        res.accepted += 1
                        class_counts[srec["driver_class"]] = class_counts.get(srec["driver_class"], 0) + 1
                    else:
                        res.rejected += 1
                    res.fabricated_analogues += int(srec["fabricated_analogue"])
                    if breach is not None:
                        res.breaches.append(breach)
                        vectors.append(srec["_vec"])
                        added += 1
                        seed_breaches += 1
                    srec.pop("_vec", None)
                rec["extra_scenarios_ignored"] = max(0, len(parsed) - scenarios_per_call)
            rec["new_breaches"] = added
            stall = 0 if added else stall + 1
            fatal = client_mod.is_fatal(resp)
            if fatal:
                reason = "aborted_fatal_error"
                res.aborted = resp.error
            elif seed_breaches >= early_stop_breaches:
                reason = "early_stop_breaches"
            elif stall >= stall_limit:
                reason = "stalled"
            else:
                reason = "iteration_budget"
            rec["stop"] = reason if reason != "iteration_budget" or it == iterations - 1 else None
            log.write(rec)
            if reason != "iteration_budget":
                break
            if resp.error is None:
                messages = list(messages) + [
                    {"role": "assistant", "content": resp.text},
                    {
                        "role": "user",
                        "content": prompts.build_feedback_message(
                            fb, scenarios_per_call, use_engine_feedback, seed_breaches, loss_target_usd,
                            include_loss_target,
                        ),
                    },
                ]
        res.stop_reasons[si] = reason
        if res.aborted is not None:
            break

    res.breaches.sort(key=lambda b: (b.penalty, -b.loss_usd))
    log.write(
        {
            "event": "summary",
            "run_id": run_id,
            "client_kind": client_kind,
            "label": label,
            "prompt_version": prompt_version,
            "breaches": len(res.breaches),
            "accepted": res.accepted,
            "rejected": res.rejected,
            "fabricated_analogues": res.fabricated_analogues,
            "calls": res.calls,
            "cache_hits": res.cache_hits,
            "input_tokens": res.input_tokens,
            "output_tokens": res.output_tokens,
            "stop_reasons": {str(k): v for k, v in res.stop_reasons.items()},
            "aborted": res.aborted,
            "include_loss_target": include_loss_target,
            "gate_stats": res.gate_stats(),
        }
    )
    return res


def run_target_ablation(
    client_factory: Callable[[], client_mod.ClaudeClient],
    engine_fn: EngineFn,
    seeds: Sequence[str | Mapping[str, Any]],
    *,
    log_dir: str | Path | None = None,
    run_id: str = "ablation",
    loss_target_usd: float = config.LOSS_TARGET_USD,
    **kwargs: Any,
) -> dict[str, LoopResult]:
    """Severity-anchoring ablation: run_loop with and without the dollar target in the prompt, identical seeds.

    client_factory() is called once per arm so both arms start from a fresh client (same model, seed, cache
    policy). Returns {'with_target': LoopResult, 'without_target': LoopResult}; all other run_loop arguments
    (kwargs) are identical in both arms. Summarise with eval.metrics.target_anchoring_report on the arms'
    scenario_records. Logs go to <log_dir>/<run_id>_<arm>.jsonl.
    """
    out: dict[str, LoopResult] = {}
    for arm, flag in (("with_target", True), ("without_target", False)):
        path = None if log_dir is None else Path(log_dir) / f"{run_id}_{arm}.jsonl"
        out[arm] = run_loop(
            client_factory(), engine_fn, seeds, log_path=path, run_id=f"{run_id}_{arm}",
            loss_target_usd=loss_target_usd, include_loss_target=flag, **kwargs,
        )
    return out


def _evaluate(
    sc: Any,
    engine_fn: EngineFn,
    table: rules.AnalogueTable | None,
    class_counts: Mapping[str, int],
    vectors: list[list[float]],
    dist: DistanceFn,
    tau: float,
    target: float,
    q_max: float,
    si: int,
    it: int,
    market: "str | Market | None" = None,
) -> tuple[dict[str, Any], dict[str, Any], Breach | None]:
    """Validate one scenario, run the engine if accepted, and classify it. Returns (log, feedback, breach)."""
    serrs = schema.validate_scenario(sc, market)
    hard = rules.check_hard_rules(sc, table, market=market)
    ok = not serrs and rules.hard_pass(hard)
    srec: dict[str, Any] = {
        "scenario_id": sc.get("scenario_id") if isinstance(sc, Mapping) else None,
        "driver_class": sc.get("driver_class") if isinstance(sc, Mapping) else None,
        "scenario": sc,
        "schema_errors": serrs,
        "hard_verdicts": [v.to_dict() for v in hard],
        "fabricated_analogue": rules.is_fabricated(hard),
        "engine_output": None,
        "engine_error": None,
        "loss_usd": None,
        "soft_verdicts": [],
        "penalty": 0.0,
        "breach": False,
        "distinct": None,
    }
    eng: dict[str, Any] | None = None
    if ok:
        try:
            eshocks = rules.to_engine_shocks(sc["shocks"], market)
            if getattr(engine_fn, "takes_season", False):
                eng = engine_fn(eshocks, season=sc["season"])
            else:
                eng = engine_fn(eshocks)
            srec["engine_output"] = eng
            srec["loss_usd"] = -float(eng["pnl_total"])
        except Exception as exc:  # engine failure rejects the scenario
            srec["engine_error"] = f"{type(exc).__name__}: {exc}"
            eng, ok = None, False
    srec["accepted"] = ok
    breach = None
    if ok and eng is not None:
        soft = rules.soft_penalties(sc, eng, class_counts)
        srec["soft_verdicts"] = [v.to_dict() for v in soft]
        srec["penalty"] = rules.total_penalty(soft)
        loss = srec["loss_usd"]
        q = eng.get("q")
        if eval_metrics.engine_implausible(eng):
            srec["distinct"] = None
        elif loss >= target and isinstance(q, (int, float)) and q < q_max:
            vec = factor_vector(eng, eshocks)
            cand = {"vec": vec}
            distinct = all(dist(cand, {"vec": v}) > tau for v in vectors)
            srec["distinct"] = distinct
            srec["_vec"] = vec
            if distinct:
                srec["breach"] = True
                breach = Breach(dict(sc), dict(eng), loss, srec["penalty"], si, it)
    fbrec = {
        "scenario_id": srec["scenario_id"],
        "verdicts": srec["hard_verdicts"]
        + [{"rule": "schema", "passed": not serrs, "hard": True, "detail": f"{len(serrs)} errors"}],
        "engine": eng,
        "loss_usd": srec["loss_usd"],
    }
    return srec, fbrec, breach


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: print the exact seed prompt and cache key without any API call (--dry-run is required)."""
    ap = argparse.ArgumentParser(description="Show the seed prompt and cache key; makes no API call.")
    ap.add_argument("--dry-run", action="store_true", required=True)
    ap.add_argument("--version", default=prompts.PROMPT_V3, choices=prompts.PROMPT_VERSIONS)
    ap.add_argument("--driver", default="cold_snap", choices=sorted(set(config.DRIVER_CLASSES) | set(_NYISO_DRIVERS)))
    ap.add_argument("--season", default=None, choices=config.SEASONS)
    ap.add_argument("--context", default=None, help="path to a JSON file with the book/factor context")
    ap.add_argument("--model", default=config.DEFAULT_MODEL)
    ap.add_argument("--market", default=None, choices=("PJM", "NYISO"), help="default: config.MARKET (PJM)")
    a = ap.parse_args(argv)
    ctx = json.loads(Path(a.context).read_text(encoding="utf-8")) if a.context else {"note": "no context supplied"}
    system, messages = prompts.build_seed_prompt(a.version, ctx, a.driver, a.season, market=a.market)
    print(client_mod.dry_run_report(system, messages, a.version, a.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
