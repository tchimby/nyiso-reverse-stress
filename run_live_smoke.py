"""Small LIVE Claude smoke test on the real NYISO engine: one seed, a few calls, hard caps on calls.

Usage (from this directory): python -E -P run_live_smoke.py --model claude-haiku-5-5 --i-understand-cost
Loads ANTHROPIC_API_KEY from the environment or from the .env file (never printed). Writes outputs/live_smoke_<model>/.
Purpose: check that the schema, hard rules, engine feedback, cache and audit log work with a real model before any full run.
Outputs are labelled 'LIVE CLAUDE (smoke test)': a handful of scenarios, not a result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from revstress import config, envfile
from revstress.agent import client as client_mod
from revstress.agent import loop as loop_mod
from revstress.agent import prompts
from revstress.book import fit_book_params
from revstress.eval import diagnostics as dg
from revstress.pipeline import ScenarioEngine
from revstress.pipeline_real import FIT_END, build_real_context, load_real_panel, nyiso_market, run_label, seed_list
from revstress.risk import fit_risk_model

ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_FILE = ROOT.parent / ".env"
SMOKE_LABEL = "LIVE CLAUDE (smoke test: a few scenarios, not a result)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Small live Claude smoke test on the real NYISO engine.")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    ap.add_argument("--seed-index", type=int, default=0, help="which NYISO seed family to use (0 = cold_snap/winter)")
    ap.add_argument("--iterations", type=int, default=2)
    ap.add_argument("--scenarios", type=int, default=config.SCENARIOS_PER_CALL)
    ap.add_argument("--max-calls", type=int, default=6, help="hard cap on live API attempts")
    ap.add_argument("--loss-target-usd", type=float, default=config.LOSS_TARGET_USD)
    ap.add_argument("--prompt-version", default=prompts.PROMPT_V3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--i-understand-cost", action="store_true")
    a = ap.parse_args(argv)

    if not a.i_understand_cost:
        print("REFUSED: pass --i-understand-cost (a live smoke test spends a small number of API tokens)", file=sys.stderr)
        return 2
    if not envfile.load_api_key(a.env_file):
        print("REFUSED: ANTHROPIC_API_KEY is not set in the environment or the .env file", file=sys.stderr)
        return 2
    print("key status (masked):", envfile.key_status())

    out_dir = Path(a.out) if a.out else ROOT / "outputs" / f"live_smoke_{a.model}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "audit_log.jsonl"
    log_path.unlink(missing_ok=True)

    with nyiso_market():
        panel, fit_panel = load_real_panel()
        params = fit_book_params(fit_panel)
        model = fit_risk_model(fit_panel, as_of=FIT_END, seed=0, n_boot=50)
        pt, _ = dg.estimate_passthrough(fit_panel, model.price_model, params.l_normal_mw)
        engine = ScenarioEngine(fit_panel, params, model, fallback=None, seed=0, passthrough=pt)
        context = {**build_real_context(params, model, None, fit_panel), "repeat_index": 0}
        seeds = seed_list()[a.seed_index : a.seed_index + 1]
        client = client_mod.ClaudeClient(model=a.model, cache_dir=out_dir / "live_cache", max_total_calls=a.max_calls)
        print(f"{SMOKE_LABEL}: model {a.model}, seed {seeds[0]}, up to {a.iterations} iterations, {a.scenarios} scenarios per call, "
              f"cap {a.max_calls} calls, loss target {a.loss_target_usd:,.0f} USD")
        res = loop_mod.run_loop(
            client, engine, seeds, iterations=a.iterations, scenarios_per_call=a.scenarios,
            prompt_version=a.prompt_version, context=context, log_path=log_path,
            run_id=f"live-smoke-{a.model}", loss_target_usd=a.loss_target_usd,
        )
        label = f"{SMOKE_LABEL} | {run_label(panel, fake=False).split(' | ', 1)[1]}"

    rows = []
    for r in res.scenario_records:
        sc = r.get("scenario") or {}
        eng = r.get("engine_output") or {}
        failed = [v.get("rule") if isinstance(v, dict) else v for v in (r.get("hard_verdicts") or []) if not (isinstance(v, dict) and v.get("passed", False))]
        rows.append({
            "scenario_id": r.get("scenario_id"), "driver_class": r.get("driver_class"), "season": sc.get("season"),
            "iteration": r.get("iteration"), "loss_usd": r.get("loss_usd"), "stated_loss_usd": r.get("stated_loss_usd"),
            "q": eng.get("q"), "severity": eng.get("severity"), "schema_errors": len(r.get("schema_errors") or []),
            "hard_rules_failed": failed, "engine_error": r.get("engine_error"), "breach": r.get("breach"),
            "narrative_words": len(str(sc.get("narrative", "")).split()),
            "analogue_event": (sc.get("analogue") or {}).get("event"), "fabricated_analogue": r.get("fabricated_analogue"),
        })
    summary = {
        "label": label, "model": a.model, "prompt_version": a.prompt_version, "seed": seeds[0],
        "calls": res.calls, "cache_hits": res.cache_hits, "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
        "accepted": res.accepted, "rejected": res.rejected, "breaches": len(res.breaches),
        "fabricated_analogues": res.fabricated_analogues, "aborted": res.aborted, "stop_reasons": {str(k): v for k, v in res.stop_reasons.items()},
        "key_status": envfile.key_status(), "scenarios": rows,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(label)
    print(f"calls={res.calls} cache_hits={res.cache_hits} tokens in/out={res.input_tokens}/{res.output_tokens} "
          f"accepted={res.accepted} rejected={res.rejected} breaches={len(res.breaches)} fabricated_analogues={res.fabricated_analogues} aborted={res.aborted}")
    for row in rows:
        loss = row["loss_usd"]
        q = row["q"]
        print(f"  {row['scenario_id']} [{row['driver_class']}/{row['season']}] loss={'n/a' if loss is None else f'{loss:,.0f}'} "
              f"stated={row['stated_loss_usd']} q={'n/a' if q is None else f'{q:.3f}'} severity={row['severity']} "
              f"schema_errors={row['schema_errors']} hard_failed={row['hard_rules_failed']} words={row['narrative_words']} "
              f"analogue={row['analogue_event']!r} fabricated={row['fabricated_analogue']} breach={row['breach']}")
    print(f"wrote {out_dir / 'summary.json'} and {log_path}")
    return 0 if res.aborted is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
