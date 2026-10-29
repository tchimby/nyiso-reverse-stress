"""Offline end-to-end pipeline on the REAL NYISO panel (market=NYISO): risk fit -> engine -> agent loop -> baselines -> metrics.

Real here: the data panel (NYISO MIS WEST / N.Y.C. LBMP and NYCA load, EIA Henry Hub, NOAA), the P&L engine, the risk
fit (2019-01-01 to 2025-12-31) and the baselines (random, optimizer, conditional-Gaussian). The Claude arm is whatever
client is injected: by default FakeClient (canned scenarios, labelled 'FAKE CLIENT - not Claude results'). A live
ClaudeClient is only used when the caller passes one (run_nyiso_demo.py --live ... guards that). No network calls here.
Equal budget means equal numbers of engine evaluations: per seed the agent's engine-call count is the budget of each
baseline in that seed's season. Prices $/MWh, load MW, horizon days.
"""

from __future__ import annotations

import contextlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from . import config
from .agent import client as client_mod
from .agent import loop as loop_mod
from .agent import context as context_mod
from .agent import prompts, rules
from .baselines import cond_gaussian_search, optimizer_search, random_search
from .book import BookParams, fit_book_params
from .eval import diagnostics as dg
from .eval import metrics as metrics_mod
from .market import NYISO
from .pipeline import (
    HORIZON_DAYS,
    ScenarioEngine,
    build_context,
    mechanical_coherence,
    plausibility_kwargs,
    protocol_iterations,
    records_from_log,
    season_spec,
    _engine_evals_by_seed,
)
from .risk import RiskModel, fit_risk_model
from .shock import PassThrough

FIT_START: str = "2019-01-01"
FIT_END: str = "2025-12-31"
PANEL_FILE: str = "nyiso_panel.csv"
ARMS: tuple[str, ...] = ("claude", "random", "optimizer", "cond_gaussian")
FAKE_LABEL: str = client_mod.FAKE_CLIENT_LABEL
DATA_ROOT: Path = Path(__file__).resolve().parent.parent / "data"


@contextlib.contextmanager
def nyiso_market() -> Iterator[None]:
    """Set config.MARKET = 'NYISO' for the duration of the block and restore the previous market afterwards."""
    prev = config.MARKET
    config.MARKET = "NYISO"
    try:
        yield
    finally:
        config.MARKET = prev


def load_real_panel(data_root: str | Path = DATA_ROOT) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(full processed panel, fit panel FIT_START..FIT_END); the fit panel never sees data after FIT_END."""
    panel = pd.read_csv(Path(data_root) / "processed" / PANEL_FILE, parse_dates=["date"])
    fit = panel[(panel["date"] >= FIT_START) & (panel["date"] <= FIT_END)].reset_index(drop=True)
    return panel, fit


def real_data_label(panel: pd.DataFrame) -> str:
    """Provenance label for real-data outputs: market and data date range."""
    return (
        f"REAL DATA - NYISO (reference WEST, pocket N.Y.C.), fit window {FIT_START} to {FIT_END}, "
        f"panel {panel['date'].min().date()} to {panel['date'].max().date()}"
    )


def is_fake(client: client_mod.ClaudeClient) -> bool:
    return getattr(client, "cache_kind", "live") == "fake"


def run_label(panel: pd.DataFrame, fake: bool) -> str:
    """Stamp for every output: FAKE CLIENT label (if the Claude arm is scripted) plus the real-data range."""
    return f"{FAKE_LABEL} | {real_data_label(panel)}" if fake else f"LIVE CLAUDE | {real_data_label(panel)}"


def build_real_context(
    params: BookParams, model: RiskModel, fallback: bool | None, fit_panel: pd.DataFrame, include_capital: bool = True
) -> dict[str, Any]:
    """Book and factor context shown to Claude (units in keys), real-data labelled. include_capital=False drops the
    capital figure (the target is 25% of it) for the severity-anchoring ablation."""
    ctx = build_context(params, model, fallback, fit_panel)
    ctx.pop("warning", None)
    ctx["data_label"] = real_data_label(fit_panel)
    ctx["market"] = NYISO.name
    ctx["reference_zone"] = NYISO.reference_zone
    ctx["pocket_zone"] = NYISO.pocket_zone
    if not include_capital:
        ctx.pop("allocated_capital_usd", None)
    # Book table, shock glossary, plausibility ceilings and sensitivities: what Claude needs to design scenarios that hurt the book.
    # The sensitivities use a separate engine instance so the arms' engine-call counts are unchanged.
    pt, _ = dg.estimate_passthrough(fit_panel, model.price_model, params.l_normal_mw)
    sens_engine = ScenarioEngine(fit_panel, params, model, fallback=fallback, seed=0, passthrough=pt)
    seasons = tuple(dict.fromkeys(s["season"] for s in seed_list()))
    return context_mod.enrich_context(
        ctx, params, model, fit_panel, NYISO, fallback,
        pnl_fn=lambda shock, season: sens_engine(shock, season)["pnl_by_position"], seasons=seasons,
    )


def baseline_budgets(per_seed_agent: Sequence[int], minimum: int | None = None) -> list[int]:
    """Per-seed baseline budget: max(agent engine calls, nominal minimum); 0 stays 0 (seed never reached the engine).

    minimum defaults to the nominal protocol, ITERATIONS_PER_SEED * SCENARIOS_PER_CALL (36), so a stalled agent does
    not starve the baselines (cond_gaussian needs 1 + n_factors + max_newton evaluations to reach its analytic point).
    """
    m = config.ITERATIONS_PER_SEED * config.SCENARIOS_PER_CALL if minimum is None else minimum
    return [max(int(b), m) if b > 0 else 0 for b in per_seed_agent]


def seed_list() -> list[dict[str, str]]:
    return [{"driver_class": d, "season": s} for d, s in NYISO.seed_families[: config.N_SEEDS]]


def _engine_key_view(rec: Mapping[str, Any]) -> dict[str, Any]:
    """Record copy whose shocks use the engine keys (the coherence rubric reads engine keys)."""
    out = dict(rec)
    sh = rec.get("shocks") or {}
    out["shocks"] = rules.to_engine_shocks(sh) if "ref_onpeak_pct" in sh else dict(sh)
    return out


def coherence_mechanical(records: Sequence[Mapping[str, Any]]) -> float:
    """Mechanical rubric mean (0/1 items the code can decide), NaN if none. NOT a human coherence score."""
    return mechanical_coherence([_engine_key_view(r) for r in records])


FORCE_PARALLEL_BASELINES = False  # tests: use worker processes even with the fake client
MAX_PARALLEL_REPEATS = 5  # live API: concurrent repeats (each is a sequential chain of calls)


@dataclass
class RealPipelineResult:
    """Everything the demo writes. label stamps every output; fake says whether the Claude arm is scripted.

    records / loop_result / engine describe repeat 0; repeats[arm] holds all repeats.
    """

    label: str
    fake: bool
    panel: pd.DataFrame
    fit_panel: pd.DataFrame
    params: BookParams
    model: RiskModel
    passthrough: PassThrough
    engine: ScenarioEngine
    loop_result: loop_mod.LoopResult
    records: dict[str, list[dict[str, Any]]]
    repeats: dict[str, list[list[dict[str, Any]]]]
    loop_results: list[loop_mod.LoopResult]
    table: pd.DataFrame
    dispersion: dict[str, pd.DataFrame]
    engine_calls: dict[str, int]
    gate: dict[str, dict[str, Any]] = field(default_factory=dict)
    stated_vs_implied: pd.DataFrame | None = None
    anchoring: pd.DataFrame | None = None
    prompt_versions: pd.DataFrame | None = None
    ablation_runs: dict[str, loop_mod.LoopResult] = field(default_factory=dict)
    sensitivity: pd.DataFrame | None = None
    seed_prompt: tuple[str, list[dict[str, str]]] | None = None
    audit_logs: list[Path] = field(default_factory=list)


def _rep_log(log_dir: Path, rep: int) -> Path:
    return log_dir / ("audit_log.jsonl" if rep == 0 else f"audit_log_rep{rep}.jsonl")


def run_ablations(
    client_factory: Callable[[], client_mod.ClaudeClient],
    engine: ScenarioEngine,
    params: BookParams,
    model: RiskModel,
    fit_panel: pd.DataFrame,
    fallback: bool | None,
    *,
    iterations: int,
    loss_target_usd: float,
    log_dir: Path | None,
) -> tuple[dict[str, loop_mod.LoopResult], pd.DataFrame, pd.DataFrame]:
    """Anchoring arms (with / without the dollar target) and prompt versions v1/v2/v3, same seeds and engine.

    With a FakeClient the arms cannot differ in substance (the canned client ignores the prompt text): this is
    plumbing only. Returns (runs keyed 'anchor_with_target', 'anchor_without_target', 'prompt_v1'..'prompt_v3',
    anchoring report, prompt-version table).
    """
    seeds = seed_list()
    runs: dict[str, loop_mod.LoopResult] = {}
    if log_dir is not None:
        for name in ("anchoring_with_target", "anchoring_without_target", *(f"prompt_{v}" for v in prompts.PROMPT_VERSIONS)):
            (log_dir / f"{name}.jsonl").unlink(missing_ok=True)
    ctx_no_cap = build_real_context(params, model, fallback, fit_panel, include_capital=False)
    anc = loop_mod.run_target_ablation(
        client_factory, engine, seeds, log_dir=log_dir, run_id="anchoring", loss_target_usd=loss_target_usd,
        iterations=iterations, context=ctx_no_cap,
    )
    runs["anchor_with_target"], runs["anchor_without_target"] = anc["with_target"], anc["without_target"]
    anchoring = metrics_mod.target_anchoring_report(
        {"with_target": anc["with_target"].scenario_records, "without_target": anc["without_target"].scenario_records},
        loss_target_usd,
    )
    ctx = build_real_context(params, model, fallback, fit_panel)
    rows = []
    for v in prompts.PROMPT_VERSIONS:
        path = None if log_dir is None else log_dir / f"prompt_{v}.jsonl"
        res = loop_mod.run_loop(
            client_factory(), engine, seeds, iterations=iterations, prompt_version=v, context=ctx, log_path=path,
            run_id=f"prompt_{v}", loss_target_usd=loss_target_usd,
        )
        runs[f"prompt_{v}"] = res
        recs = metrics_mod.records_from_loop(res.scenario_records)
        m = metrics_mod.run_metrics(recs, target_usd=loss_target_usd)
        sv = metrics_mod.stated_vs_implied(res.scenario_records)
        gs = res.gate_stats()
        rows.append(
            {
                "prompt_version": v,
                "n_scenarios": gs["n_scenarios"],
                "n_accepted": gs["n_accepted"],
                "rejection_rate": gs["rejection_rate"],
                "fabricated_analogues": res.fabricated_analogues,
                "n_distinct_breaches": m["n_breaches"],
                "median_q": m["median_q"],
                "driver_coverage": m["driver_coverage"],
                "channel_coverage": m["channel_coverage"],
                "stated_rel_abs_median": float(sv["rel_abs_median"].iloc[0]) if len(sv) else float("nan"),
            }
        )
    return runs, anchoring, pd.DataFrame(rows).set_index("prompt_version")


def _init_worker(market: str, persistence: bool, fallback_book: bool) -> None:
    """Worker-process initializer: the module-level config flags are not inherited by spawned processes."""
    config.MARKET, config.DAILY_PERSISTENCE, config.FALLBACK_BOOK = market, persistence, fallback_book


def _baseline_rep(job: tuple) -> dict[str, list[dict[str, Any]]]:
    """Random / optimizer / conditional-Gaussian searches of one repeat at the per-seed budgets of the agent (offline)."""
    rep, engine, model, seeds, budgets, seed, loss_target_usd = job
    out: dict[str, list[dict[str, Any]]] = {"random": [], "optimizer": [], "cond_gaussian": []}
    for si, sd in enumerate(seeds):
        if budgets[si] <= 0:
            continue
        eng_s, season = engine.for_season(sd["season"]), sd["season"]
        spec = season_spec(model, season)
        kw = dict(budget=budgets[si], seed=seed + 1000 * si + 100_000 * rep, season=season,
                  horizon_days=HORIZON_DAYS, target_usd=loss_target_usd)
        out["random"] += random_search(eng_s, spec, **kw)
        out["optimizer"] += optimizer_search(eng_s, spec, **kw, **plausibility_kwargs(model, season))
        out["cond_gaussian"] += cond_gaussian_search(eng_s, spec, **kw)
    return out


def run_real_pipeline(
    seed: int = 0,
    budget: int = config.N_SEEDS * config.ITERATIONS_PER_SEED * config.SCENARIOS_PER_CALL,
    *,
    repeats: int = config.N_REPEATS,
    fallback: bool | None = None,
    client_factory: Callable[[], client_mod.ClaudeClient] | None = None,
    log_dir: str | Path | None = None,
    panel: pd.DataFrame | None = None,
    fit_panel: pd.DataFrame | None = None,
    prompt_version: str = prompts.PROMPT_V3,
    loss_target_usd: float = config.LOSS_TARGET_USD,
    n_boot: int = 50,
    ablations: bool = True,
    min_baseline_budget: int | None = None,
) -> RealPipelineResult:
    """Full offline comparison on the real NYISO panel; deterministic given seed and a deterministic client.

    Protocol as pipeline.run_pipeline (4 seeds from NYISO.seed_families, iterations capped by budget, `repeats`
    repeats, per-seed equal engine budget for random / optimizer / cond_gaussian). Fit window FIT_START..FIT_END;
    pass-through coefficients are the regression estimates (diagnostics.estimate_passthrough). Sets
    config.MARKET = 'NYISO' for the duration of the call. ablations=True also runs the anchoring arms and the prompt
    versions v1-v3 once (repeat-0 engine). Each baseline gets max(agent engine calls, min_baseline_budget) per seed
    (default the nominal 36, see baseline_budgets); the table reports the agent's actual calls (engine_calls_agent)
    and the baseline per-seed budgets (baseline_budget_per_seed) next to the realised engine_calls. Log files go to log_dir (a temp dir that is removed if None).
    """
    with nyiso_market():
        if panel is None or fit_panel is None:
            panel, fit_panel = load_real_panel()
        params = fit_book_params(fit_panel)
        model = fit_risk_model(fit_panel, as_of=FIT_END, seed=seed, n_boot=n_boot)
        pt, _ = dg.estimate_passthrough(fit_panel, model.price_model, params.l_normal_mw)
        factory = client_factory or (lambda: client_mod.FakeClient(scenarios_per_call=config.SCENARIOS_PER_CALL, market="NYISO"))
        client = factory()
        fake = is_fake(client)
        label = run_label(panel, fake)
        seeds = seed_list()
        iterations = protocol_iterations(budget)
        own_dir = None
        if log_dir is None:
            own_dir = tempfile.TemporaryDirectory()
            log_dir = own_dir.name
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        reps: dict[str, list[list[dict[str, Any]]]] = {a: [] for a in ARMS}
        loop_results: list[loop_mod.LoopResult] = []
        engines: list[ScenarioEngine] = []
        n_evals: list[int] = []
        logs: list[Path] = []
        budget_log: list[list[int]] = []
        seed_prompt = None
        def agent_rep(rep: int):
            engine = ScenarioEngine(fit_panel, params, model, fallback=fallback, seed=seed + rep, passthrough=pt)
            path = _rep_log(log_dir, rep)
            path.unlink(missing_ok=True)
            context = {**build_real_context(params, model, fallback, fit_panel), "repeat_index": rep}
            res = loop_mod.run_loop(
                client, engine, seeds, iterations=iterations, prompt_version=prompt_version, context=context,
                log_path=path, run_id=f"nyiso-seed{seed}-rep{rep}", loss_target_usd=loss_target_usd,
            )
            return engine, path, context, res

        # Repeats are independent (own engine, context and log), so their Claude calls run in parallel threads: wall time
        # is one repeat, not `repeats` of them. Results are consumed in repeat order, so outputs do not depend on timing.
        if repeats > 1 and not fake:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(repeats, MAX_PARALLEL_REPEATS)) as ex:
                agent_runs = list(ex.map(agent_rep, range(repeats)))
        else:
            agent_runs = [agent_rep(rep) for rep in range(repeats)]
        baseline_jobs: list[tuple] = []
        arm_recs: list[dict[str, list[dict[str, Any]]]] = []
        for rep, (engine, path, context, res) in enumerate(agent_runs):
            if seed_prompt is None:
                seed_prompt = prompts.build_seed_prompt(
                    prompt_version, context, seeds[0]["driver_class"], seeds[0]["season"], config.SCENARIOS_PER_CALL,
                    None, loss_target_usd, NYISO,
                )
            claude = records_from_log(path)
            per_seed = _engine_evals_by_seed(claude, len(seeds))
            budgets = baseline_budgets(per_seed, min_baseline_budget)
            budget_log.append(budgets)
            n_evals.append(engine.n_calls)
            arm_rec: dict[str, list[dict[str, Any]]] = {a: [] for a in ARMS}
            arm_rec["claude"] = claude
            baseline_jobs.append((rep, engine, model, seeds, budgets, seed, loss_target_usd))
            arm_recs.append(arm_rec)
            loop_results.append(res)
            engines.append(engine)
            logs.append(path)

        # Baselines are offline and independent per repeat: run them in worker processes for live runs (deterministic: every
        # search has an explicit seed), sequentially otherwise (fake client / tests).
        if repeats > 1 and (not fake or FORCE_PARALLEL_BASELINES):
            from concurrent.futures import ProcessPoolExecutor

            flags = (config.MARKET, config.DAILY_PERSISTENCE, config.FALLBACK_BOOK)
            with ProcessPoolExecutor(max_workers=min(repeats, MAX_PARALLEL_REPEATS), initializer=_init_worker, initargs=flags) as ex:
                base_out = list(ex.map(_baseline_rep, baseline_jobs))
        else:
            base_out = [_baseline_rep(j) for j in baseline_jobs]
        for (rep, *_), arm_rec, extra in zip(baseline_jobs, arm_recs, base_out):
            for a in ("random", "optimizer", "cond_gaussian"):
                arm_rec[a] = extra[a]
            for a in ARMS:
                for r in arm_rec[a]:
                    r["repeat"] = rep
                reps[a].append(arm_rec[a])

        coherence = {a: [coherence_mechanical(r) for r in reps[a]] for a in ARMS}
        table = metrics_mod.compare_arms(reps, target_usd=loss_target_usd, coherence=coherence)
        table.insert(0, "label", label)
        table["engine_calls"] = [n_evals[0] if a == "claude" else len(reps[a][0]) for a in table.index]
        table["engine_calls_agent"] = n_evals[0]
        table["baseline_budget_per_seed"] = [
            float("nan") if a == "claude" else "/".join(str(b) for b in budget_log[0]) for a in table.index
        ]
        dispersion = {a: metrics_mod.repeat_dispersion(reps[a], target_usd=loss_target_usd) for a in ARMS}
        sensitivity = metrics_mod.sensitivity_table(reps, dg.window_d2_by_length(model), target_usd=loss_target_usd)
        gate = {f"claude_rep{i}": r.gate_stats() for i, r in enumerate(loop_results)}
        sv = metrics_mod.stated_vs_implied([s for r in loop_results for s in r.scenario_records])

        runs: dict[str, loop_mod.LoopResult] = {}
        anchoring = pvt = None
        if ablations:
            runs, anchoring, pvt = run_ablations(
                factory, ScenarioEngine(fit_panel, params, model, fallback=fallback, seed=seed, passthrough=pt),
                params, model, fit_panel, fallback, iterations=iterations, loss_target_usd=loss_target_usd,
                log_dir=log_dir if own_dir is None else None,
            )
            for k, r in runs.items():
                gate[k] = r.gate_stats()
        result = RealPipelineResult(
            label=label, fake=fake, panel=panel, fit_panel=fit_panel, params=params, model=model, passthrough=pt,
            engine=engines[0], loop_result=loop_results[0], records={a: reps[a][0] for a in ARMS}, repeats=reps,
            loop_results=loop_results, table=table, dispersion=dispersion,
            engine_calls={a: (n_evals[0] if a == "claude" else len(reps[a][0])) for a in ARMS}, gate=gate,
            stated_vs_implied=sv, anchoring=anchoring, prompt_versions=pvt, ablation_runs=runs, sensitivity=sensitivity,
            seed_prompt=seed_prompt, audit_logs=[] if own_dir is not None else logs,
        )
        if own_dir is not None:
            own_dir.cleanup()
        return result


def gate_table(gate: Mapping[str, Mapping[str, Any]], label: str) -> pd.DataFrame:
    """Flatten gate_rejection_stats dicts to rows (run, kind, rule, count, rate, penalty_sum); overall rows first."""
    rows = []
    for run, g in gate.items():
        rows.append({"label": label, "run": run, "kind": "overall", "rule": "rejected", "count": g["n_rejected"],
                     "rate": g["rejection_rate"], "penalty_sum": np.nan, "n_scenarios": g["n_scenarios"]})
        for rule_name, v in g["hard"].items():
            rows.append({"label": label, "run": run, "kind": "hard", "rule": rule_name, "count": v["count"],
                         "rate": v["rate"], "penalty_sum": np.nan, "n_scenarios": g["n_scenarios"]})
        for rule_name, v in g["soft"].items():
            rows.append({"label": label, "run": run, "kind": "soft", "rule": rule_name, "count": v["count"],
                         "rate": v["rate"], "penalty_sum": v["penalty_sum"], "n_scenarios": g["n_scenarios"]})
    return pd.DataFrame(rows)
