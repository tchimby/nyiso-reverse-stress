"""Severity-anchoring ablation on live Claude: same seeds, engine and context, with vs without the dollar target in the prompt.

Usage (from pjm_revstress): python -E -P scripts/run_anchoring_live.py --i-understand-cost [--model claude-haiku-5-5] [--out DIR]
The two arms run in parallel threads (independent clients and engines). Reads the key in-process via envfile (never printed).
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from revstress import config, envfile  # noqa: E402
from revstress.agent import client as client_mod, loop as loop_mod  # noqa: E402
from revstress.eval import metrics as metrics_mod  # noqa: E402
from revstress import pipeline_real as pr  # noqa: E402
from revstress.pipeline import ScenarioEngine  # noqa: E402
from revstress.book import fit_book_params  # noqa: E402
from revstress.risk import fit_risk_model  # noqa: E402
from revstress.eval import diagnostics as dg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--budget", type=int, default=144)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "live_anchoring")
    ap.add_argument("--env-file", default=str(ROOT.parent / ".env"))
    ap.add_argument("--i-understand-cost", action="store_true")
    a = ap.parse_args()
    if not a.i_understand_cost:
        print("REFUSED: pass --i-understand-cost (about 2 x 200k input tokens)", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        envfile.load_api_key(a.env_file)
    config.DEFAULT_MODEL = a.model
    a.out.mkdir(parents=True, exist_ok=True)
    iters = pr.protocol_iterations(a.budget)
    seeds = pr.seed_list()
    with pr.nyiso_market():
        panel, fit = pr.load_real_panel()
        params = fit_book_params(fit)
        model = fit_risk_model(fit, as_of=pr.FIT_END, seed=a.seed, n_boot=200)
        pt, _ = dg.estimate_passthrough(fit, model.price_model, params.l_normal_mw)
        ctx = pr.build_real_context(params, model, False, fit, include_capital=False)

        def arm(name: str, flag: bool):
            eng = ScenarioEngine(fit, params, model, fallback=False, seed=a.seed, passthrough=pt)
            cl = client_mod.ClaudeClient(model=a.model, cache_dir=a.out / f"cache_{name}", max_total_calls=4 * iters + 6)
            return loop_mod.run_loop(cl, eng, seeds, iterations=iters, context=ctx, log_path=a.out / f"{name}.jsonl",
                                     run_id=f"anchoring_{name}", loss_target_usd=config.LOSS_TARGET_USD, include_loss_target=flag)

        with ThreadPoolExecutor(2) as ex:
            f1, f2 = ex.submit(arm, "with_target", True), ex.submit(arm, "without_target", False)
            r1, r2 = f1.result(), f2.result()
    rep = metrics_mod.target_anchoring_report({"with_target": r1.scenario_records, "without_target": r2.scenario_records},
                                              config.LOSS_TARGET_USD)
    rep.to_csv(a.out / "ablation_anchoring.csv")
    print(rep.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
