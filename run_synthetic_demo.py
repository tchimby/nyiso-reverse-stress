"""Offline demo on a SYNTHETIC panel: agent (FakeClient) vs random search vs optimizer at equal engine budget.

Usage (from this directory): python run_synthetic_demo.py --seed 0 --budget 144 [--dry-run] [--fallback-book] [--repeats 5] [--sigma-mult 1.0]
Makes no network or API calls. Every output is SYNTHETIC and is not a real result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from revstress import config
from revstress.agent import client as client_mod
from revstress.agent import prompts
from revstress.pipeline import PipelineResult, build_context, run_pipeline
from revstress.synthetic import SYNTHETIC_SOURCE_LABEL, SYNTHETIC_WARNING

OUT_DIR = Path(__file__).resolve().parent / "outputs"
DRY_RUN_BUDGET = 21
SUMMARY_COLUMNS = ("n_breaches_mean", "median_q_mean", "median_d2_mean", "driver_coverage_mean", "channel_coverage_mean", "rule_pass_share_mean", "coherence_mean", "engine_calls", "baseline_sigma_mult")


def write_outputs(res: PipelineResult, out_dir: Path, seed: int, fallback: bool) -> dict[str, Path]:
    """Write scenarios JSONL, comparison CSV, waterfall PNG and a SYNTHETIC notice; returns paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scenarios": out_dir / "synthetic_scenarios.jsonl",
        "comparison": out_dir / "synthetic_comparison.csv",
        "waterfall": out_dir / "synthetic_waterfall.png",
        "notice": out_dir / "SYNTHETIC_NOTICE.txt",
    }
    with paths["scenarios"].open("w", encoding="utf-8") as f:
        for reps in res.repeats.values():
            for recs in reps:
                for r in recs:
                    f.write(json.dumps({"data_label": SYNTHETIC_SOURCE_LABEL, **r}, default=str) + "\n")
    res.table.to_csv(paths["comparison"], float_format="%.6g")
    paths["notice"].write_text(
        f"{SYNTHETIC_WARNING}\nseed={seed} fallback_book={fallback}\nFakeClient scenarios are canned templates, not Claude output.\n",
        encoding="utf-8",
    )
    _waterfall(res, paths["waterfall"], seed, fallback)
    return paths


def _waterfall(res: PipelineResult, path: Path, seed: int, fallback: bool) -> None:
    """P&L by position (USD millions) for the top-ranked agent breach, else the largest-loss agent scenario."""
    if res.loop_result.breaches:
        b = res.loop_result.breaches[0]
        shock, season, label = b.scenario["shocks"], b.scenario["season"], f"{b.scenario['scenario_id']} (breach)"
    else:
        cand = [r for r in res.records["claude"] if r["engine"]]
        r = max(cand, key=lambda x: x["loss_usd"])
        shock, season, label = r["shocks"], r["season"], f"{r['scenario_id']} (largest loss, no breach)"
    _, pl = res.engine.path(shock, season)
    tot = pl.drop(columns="date").sum() / 1e6
    names = [p for p in ("P1", "P2", "P3", "P4", "P5", "P6") if p in config.FALLBACK_POSITIONS or not fallback]
    vals = [float(tot[p]) for p in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
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
    ax.set_title(f"SYNTHETIC: P&L waterfall, {label}, {season}")
    ax.text(0.5, 0.5, "SYNTHETIC", transform=ax.transAxes, ha="center", va="center", fontsize=60, color="grey", alpha=0.15, rotation=25)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline SYNTHETIC demo of the reverse stress pipeline (no network, no API).")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=int, default=config.N_SEEDS * config.ITERATIONS_PER_SEED * config.SCENARIOS_PER_CALL, help="cap on agent engine evaluations per repeat (4 seeds x 12 iterations x 3 scenarios by default); baselines match it per seed")
    ap.add_argument("--repeats", type=int, default=config.N_REPEATS, help="independent repeats per arm (plan: at least 5)")
    ap.add_argument("--sigma-mult", type=float, default=1.0, help="baseline sampling law N(mu, sigma_mult^2 Sigma); 1.0 is the plan, larger is a labelled sensitivity run")
    ap.add_argument("--dry-run", action="store_true", help=f"tiny wiring check: budget capped at {DRY_RUN_BUDGET}, outputs in outputs/dry_run, prints a seed prompt")
    ap.add_argument("--fallback-book", action="store_true", help="reduced book P1, P4, P6")
    ap.add_argument("--loss-target-usd", type=float, default=config.LOSS_TARGET_USD, help="breach threshold, USD (default config.LOSS_TARGET_USD, 5e6 = the plan's 25% of capital)")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)

    print(SYNTHETIC_WARNING)
    budget = min(a.budget, DRY_RUN_BUDGET) if a.dry_run else a.budget
    out_dir = Path(a.out_dir) if a.out_dir else (OUT_DIR / "dry_run" if a.dry_run else OUT_DIR)
    client = client_mod.FakeClient(scenarios_per_call=config.SCENARIOS_PER_CALL)
    log_path = out_dir / "synthetic_audit_log.jsonl"
    res = run_pipeline(a.seed, budget, fallback=a.fallback_book, client=client, log_path=log_path, loss_target_usd=a.loss_target_usd, n_repeats=a.repeats, sigma_mult=a.sigma_mult)
    if a.dry_run:
        system, messages = prompts.build_seed_prompt(prompts.PROMPT_V3, build_context(res.params, res.model, a.fallback_book, res.panel), "cold_snap", "winter")
        print(client_mod.dry_run_report(system, messages, prompts.PROMPT_V3, config.DEFAULT_MODEL).splitlines()[0])
    paths = write_outputs(res, out_dir, a.seed, a.fallback_book)

    lr = res.loop_result
    print(f"[SYNTHETIC] seed={a.seed} budget={budget} repeats={a.repeats} sigma_mult={a.sigma_mult} fallback_book={a.fallback_book} loss_target_usd={a.loss_target_usd:,.0f} dry_run={a.dry_run}")
    print(f"agent: calls={lr.calls} accepted={lr.accepted} rejected={lr.rejected} loop_breaches={len(lr.breaches)} fake_live_calls={client.live_calls} network_calls=0")
    print(f"engine calls per arm: {res.engine_calls}")
    cols = [c for c in SUMMARY_COLUMNS if c in res.table.columns]
    print(res.table[cols].to_string(float_format=lambda x: f"{x:.3f}"))
    for k, p in paths.items():
        print(f"wrote {k}: {p}")
    print("audit_log:", log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
