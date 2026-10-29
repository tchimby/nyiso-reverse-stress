"""End-to-end pipeline on a SYNTHETIC panel: risk model -> engine -> agent loop (FakeClient) and baselines -> metrics.

SYNTHETIC ONLY: every output is computed from revstress.synthetic data and is not a real result.
Equal budget means equal numbers of engine evaluations: the agent arm runs first, and its per-seed engine-call
count becomes the budget of the random-search and optimizer arms for that seed (in the seed's season).
No network and no API calls: the Claude arm uses an injected client (FakeClient by default).
"""

from __future__ import annotations

import json
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from . import config
from .agent import client as client_mod
from .agent import loop as loop_mod
from .agent import prompts
from .baselines import FactorSpec, optimizer_search, random_search
from .book import BookParams, active_positions, fit_book_params, pnl, pnl_totals
from .eval import metrics as metrics_mod
from .eval import rubric
from .panel import panel_window
from .risk import RiskModel, fit_risk_model, score_scenario, standardize_core
from .risk.factors import FACTOR_COLUMNS, load_normal_mw
from .shock import DegreeDaySlopes, PassThrough, apply_shock, fit_degree_day_slopes
from .synthetic import SYNTHETIC_SOURCE_LABEL, SYNTHETIC_WARNING, generate_synthetic_panel

HORIZON_DAYS: int = 30
BASE_WINDOW_START: dict[str, tuple[int, int]] = {"winter": (1, 5), "summer": (7, 1), "shoulder": (4, 1)}  # (month, day)
ARMS: tuple[str, ...] = ("claude", "random", "optimizer")


class ScenarioEngine:
    """engine_fn for the agent loop and baselines: apply_shock -> book P&L -> plausibility score.

    Called as engine(shock) (uses default_season) or engine(shock, season=...). Counts calls in n_calls.
    The base windows are real days, so the unshocked book P&L is not zero: pnl_total, pnl_by_position and
    pnl_by_channel are shock-attributable (shocked path minus the zero-shock path of the same window); the raw
    shocked-path totals are reported as pnl_total_raw / pnl_base_total (USD). Base windows carry the seasonal-normal
    peak load (risk-model month-of-year mean) as load_normal_mw, which P5 volume and the pass-through use.
    """

    takes_season = True

    def __init__(
        self,
        panel: pd.DataFrame,
        params: BookParams,
        model: RiskModel,
        *,
        default_season: str = "winter",
        fallback: bool | None = None,
        seed: int = 0,
        horizon_days: int = HORIZON_DAYS,
        passthrough: PassThrough | None = None,
    ) -> None:
        self.params, self.model, self.fallback, self.seed = params, model, fallback, seed
        self.default_season = default_season
        self.passthrough = PassThrough(l_normal_mw=params.l_normal_mw) if passthrough is None else passthrough
        self.weather: DegreeDaySlopes = fit_degree_day_slopes(panel)
        last = panel["date"].max()
        year = int(last.year) if last >= pd.Timestamp(last.year, 12, 31) else int(last.year) - 1  # last full year
        self.base = {
            s: panel_window(panel, pd.Timestamp(year, *BASE_WINDOW_START[s]), horizon_days) for s in config.SEASONS
        }
        for w in self.base.values():
            w["load_normal_mw"] = load_normal_mw(w["date"], model.price_model)
        self.base_pnl = {s: pnl_totals(pnl(w, params, fallback)) for s, w in self.base.items()}
        self.n_calls = 0

    def for_season(self, season: str) -> "ScenarioEngine":
        """Shallow copy bound to another default season; shares the call counter owner (copy has its own)."""
        other = object.__new__(ScenarioEngine)
        other.__dict__.update(self.__dict__)
        other.default_season = season
        other.n_calls = 0
        return other

    def _shock_seed(self, shock: Mapping[str, float]) -> int:
        key = json.dumps({k: round(float(shock[k]), 9) for k in sorted(shock)})
        return (zlib.crc32(key.encode()) ^ self.seed) % (2**31)

    def path(self, shock: Mapping[str, float], season: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Shocked path and its daily P&L (USD)."""
        path = apply_shock(self.base[season or self.default_season], shock, self._shock_seed(shock), self.passthrough, self.weather)
        return path, pnl(path, self.params, self.fallback)

    def __call__(self, shock: Mapping[str, float], season: str | None = None) -> dict[str, Any]:
        self.n_calls += 1
        path, pl = self.path(shock, season)
        raw = pnl_totals(pl)
        base = self.base_pnl[season or self.default_season]
        tot = raw - base
        sc = score_scenario(path, self.model)
        spk = sc["spike"] or {}
        exceed = spk.get("empirical_size_exceedance")
        return {
            "pnl_total": float(tot["total"]),
            "pnl_total_raw": float(raw["total"]),
            "pnl_base_total": float(base["total"]),
            "pnl_by_position": {p: float(tot[p]) for p in ("P1", "P2", "P3", "P4", "P5", "P6")},
            "pnl_by_channel": {c: float(tot[c]) for c in config.CHANNELS},
            "d2": float(sc["d2"]),
            "q": float(sc["q"]),
            "marginals": {f: float(sc["marginal_percentiles"][f]) / 100.0 for f in config.GAUSSIAN_CORE_FACTORS},
            "z": standardize_core(self.model, sc["season"], sc["factors_worst"]),
            "nearest_date": sc["nearest_date"],
            "nn_distance": float(sc["nearest_distance"]),
            "severity": sc["severity"],
            "spike_exceedance": 1.0 if exceed is None else float(exceed),
            "hard_rule_failures": list(sc["hard_rule_failures"]),
            "marginals_exceeded": [e["factor"] for e in sc["marginals_exceeded"]],
        }


def season_spec(model: RiskModel, season: str) -> FactorSpec:
    """Baseline factor spec: zero-mean deviations with the season's robust covariance (order g, l, s, c, d)."""
    return FactorSpec(mu=np.zeros(len(config.GAUSSIAN_CORE_FACTORS)), cov=model.season_cov[season].cov)


def plausibility_kwargs(model: RiskModel, season: str, q_max: float = config.Q_ADVERSE_MAX) -> dict[str, Any]:
    """Plausibility inputs of the optimizer baseline for one season, from the fitted risk model.

    tail_d2: the engine D^2 a path must exceed for rank q < q_max against the fitted historical 10-day windows
    (q = share of windows with D^2 >= the path's D^2, so the path needs D^2 above the ceil(q_max * N)-th largest window D^2).
    z_limits: the season's marginal limits (model.limits) of the five core factors in robust-z units, the same units as the
    engine output 'z' ((value - season median) / robust sd), so 'inside the limits' is 'not implausible by marginal'.
    """
    w = np.sort(np.asarray(model.window_d2, dtype=float))[::-1]
    idx = max(int(np.ceil(q_max * len(w))) - 1, 0)
    hist = model.history[model.history["season"] == season]
    z_limits: dict[str, tuple[float, float]] = {}
    for f in config.GAUSSIAN_CORE_FACTORS:
        j = FACTOR_COLUMNS.index(f)
        med, rs = float(hist[f].median()), float(model.robust_sd[j])
        lo, hi = model.limits[season][f]
        z_limits[f] = ((lo - med) / rs, (hi - med) / rs)
    return {"tail_d2": float(w[idx]), "z_limits": z_limits}


def build_context(params: BookParams, model: RiskModel, fallback: bool | None, panel: pd.DataFrame) -> dict[str, Any]:
    """Book and factor context shown to Claude (units in keys). Contains SYNTHETIC label."""
    return {
        "data_label": SYNTHETIC_SOURCE_LABEL,
        "warning": SYNTHETIC_WARNING,
        "active_positions": list(active_positions(fallback)),
        "position_sizes_mw": {p: params.sizes_mw[p] for p in active_positions(fallback)},
        "strikes_usd_mwh": {"K1": round(params.k1_usd, 2), "K6": round(params.k6_usd, 2), "c0": round(params.c0_usd, 2)},
        "horizon_days": HORIZON_DAYS,
        "allocated_capital_usd": config.ALLOCATED_CAPITAL_USD,
        "factor_sd_by_season": {
            s: {f: round(float(np.sqrt(v)), 4) for f, v in zip(config.GAUSSIAN_CORE_FACTORS, np.diag(model.season_cov[s].cov))}
            for s in model.season_cov
        },
        "panel_first_date": str(panel["date"].min().date()),
        "panel_last_date": str(panel["date"].max().date()),
    }


def _failed_rules(srec: Mapping[str, Any]) -> list[str]:
    failed = [v["rule"] for v in srec["hard_verdicts"] if not v["passed"]]
    if srec["schema_errors"]:
        failed.append("schema")
    if srec["engine_error"]:
        failed.append("engine_error")
    eng = srec.get("engine_output") or {}
    if eng.get("severity") == "implausible":
        failed.append("implausible_severity")
    return sorted(set(failed))


def records_from_log(path: str | Path, arm: str = "claude") -> list[dict[str, Any]]:
    """Scenario records (same fields as the baselines) for every scenario in an agent audit log."""
    out: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("event") != "call":
            continue
        for s in rec["scenarios"]:
            sc = s["scenario"] if isinstance(s["scenario"], dict) else {}
            failed = _failed_rules(s)
            out.append(
                {
                    "scenario_id": s["scenario_id"],
                    "arm": arm,
                    "seed": rec["seed_index"],
                    "iteration": rec["iteration"],
                    "driver_class": s["driver_class"],
                    "season": sc.get("season"),
                    "horizon_days": sc.get("horizon_days"),
                    "narrative": sc.get("narrative", ""),
                    "shocks": sc.get("shocks", {}),
                    "analogue": sc.get("analogue", {}),
                    "confidence": sc.get("confidence"),
                    "engine": s["engine_output"],
                    "loss_usd": s["loss_usd"],
                    "rules_failed": failed,
                    "rules_passed": not failed,
                    "breach": bool(s["breach"]),
                }
            )
    return out


def mechanical_coherence(records: Sequence[Mapping[str, Any]]) -> float:
    """Mean over decided rubric items (0/1) of the automated checks only; NaN if none decided. NOT a human score."""
    vals = [v for r in records if r.get("narrative") for v in rubric.mechanical_checks(r).values() if v is not None]
    return float(np.mean(vals)) if vals else float("nan")


@dataclass
class PipelineResult:
    """Everything the demo writes. All fields derive from a SYNTHETIC panel.

    records, loop_result, engine and engine_calls describe repeat 0; repeats[arm] holds the records of every
    repeat (the table is computed over all of them).
    """

    panel: pd.DataFrame
    params: BookParams
    model: RiskModel
    engine: ScenarioEngine
    loop_result: loop_mod.LoopResult
    records: dict[str, list[dict[str, Any]]]
    table: pd.DataFrame
    engine_calls: dict[str, int]
    repeats: dict[str, list[list[dict[str, Any]]]] = field(default_factory=dict)
    loop_results: list[loop_mod.LoopResult] = field(default_factory=list)


def protocol_iterations(budget: int) -> int:
    """Iterations per seed: config.ITERATIONS_PER_SEED, reduced when the agent budget (engine evaluations) is smaller."""
    return max(1, min(config.ITERATIONS_PER_SEED, budget // (config.N_SEEDS * config.SCENARIOS_PER_CALL)))


def _repeat_log_path(log_path: Path, rep: int) -> Path:
    return log_path if rep == 0 else log_path.with_name(f"{log_path.stem}_rep{rep}{log_path.suffix}")


def _engine_evals_by_seed(records: Sequence[Mapping[str, Any]], n_seeds: int) -> list[int]:
    """Engine evaluations per seed index in a Claude record list (scenarios that reached the engine)."""
    counts = [0] * n_seeds
    for r in records:
        if r["engine"] is not None or "engine_error" in r["rules_failed"]:
            counts[r["seed"]] += 1
    return counts


def run_pipeline(
    seed: int = 0,
    budget: int = config.N_SEEDS * config.ITERATIONS_PER_SEED * config.SCENARIOS_PER_CALL,
    *,
    fallback: bool | None = None,
    client: client_mod.ClaudeClient | None = None,
    log_path: str | Path | None = None,
    panel: pd.DataFrame | None = None,
    prompt_version: str = prompts.PROMPT_V3,
    n_boot: int = 50,
    loss_target_usd: float = config.LOSS_TARGET_USD,
    n_repeats: int = config.N_REPEATS,
    sigma_mult: float = 1.0,
) -> PipelineResult:
    """Run the full comparison on a SYNTHETIC panel; deterministic given seed and client.

    Protocol (plan sections 5 and 8D): config.N_SEEDS seeds, one per driver family in config.SEED_FAMILIES, each
    with up to config.ITERATIONS_PER_SEED iterations of config.SCENARIOS_PER_CALL scenarios. `budget` caps the
    iterations: min(ITERATIONS_PER_SEED, budget // (seeds * scenarios per call)), at least 1. Per repeat, each
    baseline gets, for every seed, exactly the number of engine evaluations the agent used on that seed, in
    the seed's season. The whole comparison is repeated n_repeats times (different engine and baseline
    seeds, repeat index in the Claude context) and compare_arms runs over all repeats.
    sigma_mult scales the baselines' sampling law N(mu, sigma_mult^2 Sigma): 1.0 is the plan; larger values
    are a widened sensitivity run (recorded in the table column baseline_sigma_mult).
    """
    panel = generate_synthetic_panel(seed, warn=False) if panel is None else panel
    params = fit_book_params(panel)
    model = fit_risk_model(panel, seed=seed, n_boot=n_boot)
    client = client or client_mod.FakeClient(scenarios_per_call=config.SCENARIOS_PER_CALL)
    families = config.SEED_FAMILIES[: config.N_SEEDS]
    seeds = [{"driver_class": d, "season": s} for d, s in families]
    iterations = protocol_iterations(budget)

    own_dir = None
    if log_path is None:
        own_dir = tempfile.TemporaryDirectory()
        log_path = Path(own_dir.name) / "audit_log.jsonl"
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    repeats: dict[str, list[list[dict[str, Any]]]] = {arm: [] for arm in ARMS}
    loop_results: list[loop_mod.LoopResult] = []
    engines: list[ScenarioEngine] = []
    n_evals: list[int] = []
    for rep in range(n_repeats):
        engine = ScenarioEngine(panel, params, model, fallback=fallback, seed=seed + rep)
        rep_log = _repeat_log_path(log_path, rep)
        rep_log.write_text(
            json.dumps(
                {"event": "header", "data_label": SYNTHETIC_SOURCE_LABEL, "warning": SYNTHETIC_WARNING, "seed": seed,
                 "repeat": rep, "budget": budget, "iterations_per_seed": iterations, "loss_target_usd": loss_target_usd}
            )
            + "\n",
            encoding="utf-8",
        )
        context = {**build_context(params, model, fallback, panel), "repeat_index": rep}
        res = loop_mod.run_loop(
            client,
            engine,
            seeds,
            iterations=iterations,
            prompt_version=prompt_version,
            context=context,
            log_path=rep_log,
            run_id=f"synthetic-seed{seed}-rep{rep}",
            loss_target_usd=loss_target_usd,
        )
        claude_records = records_from_log(rep_log)
        per_seed = _engine_evals_by_seed(claude_records, len(seeds))
        n_evals.append(engine.n_calls)
        arm_records: dict[str, list[dict[str, Any]]] = {"claude": claude_records, "random": [], "optimizer": []}
        for si, (_, season) in enumerate(families):
            if per_seed[si] <= 0:
                continue
            eng_s = engine.for_season(season)
            spec = season_spec(model, season)
            kw = dict(
                budget=per_seed[si], seed=seed + 1000 * si + 100_000 * rep, season=season,
                horizon_days=HORIZON_DAYS, target_usd=loss_target_usd, sigma_mult=sigma_mult,
            )
            arm_records["random"] += random_search(eng_s, spec, **kw)
            arm_records["optimizer"] += optimizer_search(eng_s, spec, **kw)
        for arm in ARMS:
            for r in arm_records[arm]:
                r["repeat"] = rep
            repeats[arm].append(arm_records[arm])
        loop_results.append(res)
        engines.append(engine)

    coherence = {arm: [mechanical_coherence(recs) for recs in repeats[arm]] for arm in ARMS}
    table = metrics_mod.compare_arms(repeats, target_usd=loss_target_usd, coherence=coherence)
    table.insert(0, "data_label", SYNTHETIC_SOURCE_LABEL)
    table["engine_calls"] = [len(repeats[a][0]) if a != "claude" else n_evals[0] for a in table.index]
    table["baseline_sigma_mult"] = [float("nan") if a == "claude" else sigma_mult for a in table.index]
    result = PipelineResult(
        panel=panel,
        params=params,
        model=model,
        engine=engines[0],
        loop_result=loop_results[0],
        records={arm: repeats[arm][0] for arm in ARMS},
        table=table,
        engine_calls={"claude": n_evals[0], "random": len(repeats["random"][0]), "optimizer": len(repeats["optimizer"][0])},
        repeats=repeats,
        loop_results=loop_results,
    )
    if own_dir is not None:
        own_dir.cleanup()
    return result
