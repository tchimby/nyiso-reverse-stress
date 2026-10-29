"""Offline NYISO demo on the REAL panel: agent (FakeClient) vs random vs optimizer vs conditional-Gaussian at equal budget.

Usage (from this directory, with pandas working): python -E -P run_nyiso_demo.py --seed 0 --budget 144 --repeats 5 [--dry-run] [--fallback-book] [--out DIR]
Real: NYISO data panel, engine, risk fit (2019-2025), baselines. Scripted: the Claude arm (FakeClient, 'FAKE CLIENT - not Claude results').
No network. --live is OFF by default; it refuses unless ANTHROPIC_API_KEY is set AND --i-understand-cost is passed
(the first live run is for the user to trigger; see README).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from revstress import config, envfile, manifest
from revstress.agent import client as client_mod
from revstress.agent import prompts, rules
from revstress.pipeline_real import (
    RealPipelineResult,
    gate_table,
    nyiso_market,
    run_real_pipeline,
)

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs" / "nyiso_demo"
DRY_RUN_BUDGET = 21
DRY_RUN_REPEATS = 2
LIVE_REFUSAL_KEY = "--live needs ANTHROPIC_API_KEY set in the environment"
LIVE_REFUSAL_COST = "--live needs --i-understand-cost (a full run is about 350k tokens per repeat; check live pricing)"
SUMMARY_COLUMNS = (
    "n_breaches_mean", "n_breaches_sd", "median_q_mean", "median_d2_mean", "driver_coverage_mean",
    "channel_coverage_mean", "rule_pass_share_mean", "coherence_mean", "engine_calls",
)


def check_live_guard(live: bool, understand_cost: bool, environ: dict | None = None) -> str | None:
    """Return a refusal message if --live must not run, else None. Reads ANTHROPIC_API_KEY presence only (never its value)."""
    if not live:
        return None
    env = os.environ if environ is None else environ
    if not env.get("ANTHROPIC_API_KEY"):
        return LIVE_REFUSAL_KEY
    if not understand_cost:
        return LIVE_REFUSAL_COST
    return None


def _write_jsonl(path: Path, res: RealPipelineResult) -> None:
    with path.open("w", encoding="utf-8") as f:
        for arm, reps in res.repeats.items():
            for recs in reps:
                for r in recs:
                    shock_keys = "agent" if arm == "claude" else "engine"
                    f.write(json.dumps({"label": res.label, "arm": arm, "shock_keys": shock_keys, **r}, default=str) + "\n")


def _write_csv(df: pd.DataFrame, path: Path, label: str, index: bool = True) -> None:
    out = df.copy()
    if "label" not in out.columns:
        out.insert(0, "label", label)
    out.to_csv(path, index=index, float_format="%.6g")


def _waterfall(res: RealPipelineResult, path: Path, fallback: bool) -> str:
    """P&L by position (USD millions) of the top agent breach, else the largest-loss agent scenario."""
    lr = res.loop_result
    if lr.breaches:
        b = lr.breaches[0]
        agent_shock, season, name = b.scenario["shocks"], b.scenario["season"], f"{b.scenario['scenario_id']} (breach)"
    else:
        cand = [r for r in res.records["claude"] if r["engine"]]
        r = max(cand, key=lambda x: x["loss_usd"])
        agent_shock, season, name = r["shocks"], r["season"], f"{r['scenario_id']} (largest loss, no breach)"
    with nyiso_market():
        _, pl = res.engine.path(rules.to_engine_shocks(agent_shock), season)
    tot = pl.drop(columns="date").sum() / 1e6
    names = [p for p in config.POSITIONS if p in config.FALLBACK_POSITIONS or not fallback]
    vals = [float(tot[p]) for p in names]
    fig, ax = plt.subplots(figsize=(9, 5))
    cum, levels = 0.0, [0.0]
    for i, v in enumerate(vals):
        ax.bar(i, v, bottom=cum, color="#2a7ab0" if v >= 0 else "#c0392b")
        cum += v
        levels.append(cum)
    pad = 0.1 * (max(levels) - min(levels) or 1.0)
    ax.set_ylim(min(levels) - pad, max(levels) + pad)
    ax.bar(len(vals), cum, color="#555555")
    ax.axhline(0.0, color="black", lw=0.8)
    ax.set_xticks(range(len(vals) + 1), names + ["Total"])
    ax.set_ylabel("P&L over scenario, USD millions")
    stamp = "FAKE CLIENT - not Claude results" if res.fake else "LIVE CLAUDE"
    ax.set_title(f"{stamp}: P&L waterfall, {name}, {season}\nNYISO real-data engine, panel {res.panel['date'].min().date()} to {res.panel['date'].max().date()}", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return name


def write_outputs(res: RealPipelineResult, out_dir: Path, args: argparse.Namespace, budget: int, repeats: int) -> dict[str, Path]:
    """Write every output file (all stamped with res.label) and the run manifest; returns the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = {
        "scenarios": out_dir / "scenarios.jsonl",
        "comparison": out_dir / "comparison_table.csv",
        "dispersion": out_dir / "repeat_dispersion.csv",
        "gate": out_dir / "gate_rejection.csv",
        "stated_vs_implied": out_dir / "stated_vs_implied.csv",
        "sensitivity": out_dir / "sensitivity.csv",
        "waterfall": out_dir / "pnl_waterfall.png",
        "notice": out_dir / "NOTICE.txt",
    }
    lab = res.label
    _write_jsonl(p["scenarios"], res)
    _write_csv(res.table, p["comparison"], lab)
    disp = pd.concat({a: d for a, d in res.dispersion.items()}, names=["arm", "metric"]).reset_index()
    _write_csv(disp, p["dispersion"], lab, index=False)
    _write_csv(gate_table(res.gate, lab), p["gate"], lab, index=False)
    if res.sensitivity is not None:
        _write_csv(res.sensitivity, p["sensitivity"], lab, index=False)
    if res.stated_vs_implied is not None:
        _write_csv(res.stated_vs_implied, p["stated_vs_implied"], lab)
    if res.anchoring is not None:
        p["anchoring"] = out_dir / "ablation_anchoring.csv"
        _write_csv(res.anchoring, p["anchoring"], lab + " | plumbing only: FakeClient ignores the prompt")
    if res.prompt_versions is not None:
        p["prompt_versions"] = out_dir / "ablation_prompt_versions.csv"
        _write_csv(res.prompt_versions, p["prompt_versions"], lab + " | plumbing only: FakeClient ignores the prompt")
    wf = _waterfall(res, p["waterfall"], args.fallback_book)
    p["notice"].write_text(
        f"{lab}\nseed={args.seed} budget={budget} repeats={repeats} fallback_book={args.fallback_book} dry_run={args.dry_run}\n"
        + ("The Claude arm is a FakeClient: canned scenario templates, NOT Claude output. Ablation tables are plumbing only.\n" if res.fake
           else "Claude arm: live API calls.\n")
        + "Baselines, engine, risk fit and data are real (NYISO MIS, EIA, NOAA). The scenario price cap of $5,000/MWh is a stated assumption.\n"
        + "Coherence column = automated rubric checks only, not a human score. tau, spike overlay and sizes are placeholders or assumptions.\n"
        + f"Waterfall shows: {wf}\n",
        encoding="utf-8",
    )
    system, messages = res.seed_prompt or (None, None)
    p["manifest"] = manifest.write_run_manifest(
        out_dir.name,
        model="fake-client" if res.fake else config.DEFAULT_MODEL,
        temperature=None,
        seed=args.seed,
        prompt_version=prompts.PROMPT_V3,
        system=system,
        messages=messages,
        market="NYISO",
        label=lab,
        outputs_root=out_dir.parent,
        extra={
            "budget": budget, "repeats": repeats, "fallback_book": args.fallback_book, "dry_run": args.dry_run,
            "fake_client": res.fake, "fit_window": ["2019-01-01", "2025-12-31"],
            "panel_range": [str(res.panel["date"].min().date()), str(res.panel["date"].max().date())],
            "engine_calls": res.engine_calls,
            "outputs_sha256": {k: manifest.sha256_file(v) for k, v in p.items() if v.exists()},
        },
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline NYISO demo on the real panel (FakeClient Claude arm; no network).")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=int, default=config.N_SEEDS * config.ITERATIONS_PER_SEED * config.SCENARIOS_PER_CALL,
                    help="cap on agent engine evaluations per repeat; baselines match it per seed")
    ap.add_argument("--repeats", type=int, default=config.N_REPEATS, help="independent repeats per arm (plan: at least 5)")
    ap.add_argument("--dry-run", action="store_true", help=f"tiny wiring check: budget <= {DRY_RUN_BUDGET}, repeats <= {DRY_RUN_REPEATS}, prints the seed prompt header, writes to outputs/nyiso_demo_dry_run")
    ap.add_argument("--fallback-book", action="store_true", help="reduced book P1, P4, P6")
    ap.add_argument("--loss-target-usd", type=float, default=config.LOSS_TARGET_USD)
    ap.add_argument("--out", default=None, help="output directory (default outputs/nyiso_demo)")
    ap.add_argument("--live", action="store_true", help="OFF by default. Live Claude arm: needs ANTHROPIC_API_KEY and --i-understand-cost")
    ap.add_argument("--i-understand-cost", action="store_true", help="confirms a live run spends API tokens (about 350k per repeat)")
    ap.add_argument("--model", default="claude-haiku-5-5", help="live model (default Haiku 5.5; use claude-sonnet-5-5 for the final arms)")
    ap.add_argument("--env-file", default=str(ROOT.parent / ".env"), help="file holding ANTHROPIC_API_KEY; loaded in-process, never printed")
    ap.add_argument("--no-persistence", action="store_true", help="daily-model persistence tail off (snap-back engine, the earlier behaviour)")
    ap.add_argument("--no-ablations", action="store_true", help="skip anchoring and prompt-version ablations (always skipped for --live)")
    a = ap.parse_args(argv)

    if a.live and not os.environ.get("ANTHROPIC_API_KEY"):
        envfile.load_api_key(a.env_file)
    if a.live:
        config.DEFAULT_MODEL = a.model
    refusal = check_live_guard(a.live, a.i_understand_cost)
    if refusal:
        print("REFUSED: " + refusal, file=sys.stderr)
        return 2
    budget = min(a.budget, DRY_RUN_BUDGET) if a.dry_run else a.budget
    repeats = min(a.repeats, DRY_RUN_REPEATS) if a.dry_run else a.repeats
    out_dir = Path(a.out) if a.out else (ROOT / "outputs" / "nyiso_demo_dry_run" if a.dry_run else OUT_DIR)
    config.FALLBACK_BOOK = bool(a.fallback_book)
    config.DAILY_PERSISTENCE = not a.no_persistence

    if a.live:
        n_calls = repeats * config.N_SEEDS * config.ITERATIONS_PER_SEED
        cache_dir = out_dir / "live_cache"

        def factory() -> client_mod.ClaudeClient:
            return client_mod.ClaudeClient(model=a.model, cache_dir=cache_dir, max_total_calls=n_calls + 10)

        print(f"LIVE CLAUDE run: up to {n_calls} calls, model {config.DEFAULT_MODEL}. Ctrl-C to stop.")
    else:
        def factory() -> client_mod.ClaudeClient:
            return client_mod.FakeClient(scenarios_per_call=config.SCENARIOS_PER_CALL, market="NYISO")

    res = run_real_pipeline(
        a.seed, budget, repeats=repeats, fallback=a.fallback_book, client_factory=factory, log_dir=out_dir,
        loss_target_usd=a.loss_target_usd, ablations=not (a.no_ablations or a.live),
    )
    print(res.label)
    if a.dry_run and res.seed_prompt:
        system, messages = res.seed_prompt
        print(client_mod.dry_run_report(system, messages, prompts.PROMPT_V3, config.DEFAULT_MODEL).splitlines()[0])
    paths = write_outputs(res, out_dir, a, budget, repeats)

    lr = res.loop_result
    print(f"seed={a.seed} budget={budget} repeats={repeats} fallback_book={a.fallback_book} loss_target_usd={a.loss_target_usd:,.0f} dry_run={a.dry_run} live={a.live}")
    print(f"agent (repeat 0): calls={lr.calls} accepted={lr.accepted} rejected={lr.rejected} loop_breaches={len(lr.breaches)} network_calls=0 (offline)" if res.fake
          else f"agent (repeat 0): calls={lr.calls} accepted={lr.accepted} rejected={lr.rejected} loop_breaches={len(lr.breaches)}")
    print(f"engine calls per arm (repeat 0): {res.engine_calls}")
    cols = [c for c in SUMMARY_COLUMNS if c in res.table.columns]
    print(res.table[cols].to_string(float_format=lambda x: f"{x:.3f}"))
    g = res.gate.get("claude_rep0")
    if g:
        print(f"gate (claude, repeat 0): rejected {g['n_rejected']} of {g['n_scenarios']} ({g['rejection_rate']:.1%}); hard rules fired: {sorted(g['hard']) or 'none'}")
    for k, pth in paths.items():
        print(f"wrote {k}: {pth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
