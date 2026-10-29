"""Multi-channel book scan (config.py, MULTI-CHANNEL BOOK RULE v2; conditions as code in revstress/eval/sizing.py).

Run from pjm_revstress:  python -E -P scripts/scan_book_v2.py [--workers 16] [--out outputs/book_scan_v2]
Conditional-Gaussian arm, rng seeds 0,1,2, winter/summer/shoulder pooled, budget 144 per season, on the real NYISO panel.
Writes scan_v2.json (statistics per candidate and the selection). No network, no Claude calls.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GRID = {
    "P1": (-100.0, -50.0, 50.0, 100.0),
    "P2": (25.0, 50.0),
    "P3": (50.0, 100.0, 150.0),
    "P4": (50.0, 100.0),
    "P5": (100.0, 120.0, 140.0),
    "P6": (25.0, 50.0, 100.0),
}
SEEDS = (0, 1, 2)
SEASONS = ("winter", "summer", "shoulder")
BUDGET = 144
_G = {}


def candidates():
    return [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]


def _init():
    from revstress import pipeline_real as pr
    from revstress.book import fit_book_params
    from revstress.eval import diagnostics as dg
    from revstress.risk import fit_risk_model

    pr.config.MARKET = "NYISO"
    panel, fit = pr.load_real_panel()
    params = fit_book_params(fit)
    model = fit_risk_model(fit, as_of=pr.FIT_END, seed=0, n_boot=50)
    pt, _ = dg.estimate_passthrough(fit, model.price_model, params.l_normal_mw)
    _G.update(fit=fit, params=params, model=model, pt=pt)


def work(args):
    idx, sizes, seed = args
    from revstress import config
    from revstress.baselines import cond_gaussian_search
    from revstress.pipeline import HORIZON_DAYS, ScenarioEngine, season_spec

    p = replace(_G["params"], sizes_mw=dict(sizes))
    eng = ScenarioEngine(_G["fit"], p, _G["model"], seed=0, passthrough=_G["pt"])
    recs = []
    for s in SEASONS:
        recs += cond_gaussian_search(eng.for_season(s), season_spec(_G["model"], s), budget=BUDGET, seed=seed, season=s,
                                     horizon_days=HORIZON_DAYS, target_usd=config.LOSS_TARGET_USD)
    return idx, seed, recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", default="outputs/book_scan_v2")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    _init()
    from revstress.eval import diagnostics as dg
    from revstress.eval import sizing

    cands = candidates()
    if a.limit:
        cands = cands[: a.limit]
    t0 = time.time()
    by = {i: {} for i in range(len(cands))}
    jobs = [(i, c, s) for i, c in enumerate(cands) for s in SEEDS]
    with ProcessPoolExecutor(a.workers, initializer=_init) as ex:
        for k, (i, s, recs) in enumerate(ex.map(work, jobs, chunksize=1)):
            by[i][s] = recs
            if k % 30 == 0:
                print(k, len(jobs), round(time.time() - t0), flush=True)
    out = []
    for i, c in enumerate(cands):
        p = replace(_G["params"], sizes_mw=dict(c))
        w = dg.sizing_check(_G["fit"], p)["worst_30d_loss_usd"]
        st = sizing.candidate_stats(by[i], w)
        mix = sizing.breach_mix(by[i])
        out.append({"sizes": c, "stats": st, "mix": mix, "failed_v2": sizing.failed_conditions_v2(st, mix)})
    idx, failed = sizing.select_candidate_v2(out)
    res = {"grid": GRID, "seeds": SEEDS, "budget": BUDGET, "n_candidates": len(out), "selected_index": idx,
           "selected_failed_conditions": failed, "n_admissible": sum(1 for o in out if not o["failed_v2"]),
           "candidates": out}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    Path(a.out, "scan_v2.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print("selected", idx, out[idx]["sizes"] if idx is not None else None, failed, "admissible", res["n_admissible"])


if __name__ == "__main__":
    main()
