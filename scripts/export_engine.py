"""Export the scenario engine's parameters and reference cases for the browser sandbox (ui/data/engine.json).

The sandbox (ui/engine.js) re-implements apply_shock + book P&L + factor scoring in JavaScript from these numbers, so a reader can set
their own shock vector and see the loss, P&L, price paths and plausibility without Python. Reference cases are computed here by the
Python engine so the port can be checked: node ui/check_engine.js compares both.
Usage (repo root): python -E -P scripts/export_engine.py [--out ui/data/engine.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from revstress import config, pipeline_real as pr  # noqa: E402
from revstress.book import fit_book_params  # noqa: E402
from revstress.eval import diagnostics as dg  # noqa: E402
from revstress.pipeline import ScenarioEngine  # noqa: E402
from revstress.risk import fit_risk_model  # noqa: E402

KEYS = ("gas_hh_pct", "ny_gas_basis_usd", "load_peak_ratio", "dc_load_shock_mw", "wh_onpeak_pct", "dom_minus_wh_usd", "dart_pct", "duration_days")
CORE = ("g", "l", "s", "c", "d")
COLS = ("wh_on", "wh_off", "dom_on", "dom_off", "da_wh_on", "da_wh_off", "rt_wh_on", "rt_wh_off", "load_peak_mw", "hh_usd", "hdd", "cdd")
CASES = [
    {"duration_days": 7, "gas_hh_pct": 40, "dom_minus_wh_usd": 150, "load_peak_ratio": 1.05},
    {"duration_days": 10, "gas_hh_pct": 100, "ny_gas_basis_usd": 10, "dom_minus_wh_usd": 250, "wh_onpeak_pct": -15},
    {"duration_days": 5, "load_peak_ratio": 1.12, "dart_pct": 80, "wh_onpeak_pct": 30},
    {"duration_days": 14, "gas_hh_pct": -30, "dart_pct": -60, "wh_onpeak_pct": -40, "load_peak_ratio": 1.02, "dom_minus_wh_usd": 32},
    {"duration_days": 3, "dom_minus_wh_usd": 300, "dc_load_shock_mw": -500},
    {"duration_days": 0},
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "ui" / "data" / "engine.json")
    a = ap.parse_args()
    with pr.nyiso_market():
        _, fit = pr.load_real_panel()
        params = fit_book_params(fit)
        model = fit_risk_model(fit, as_of=pr.FIT_END, seed=0, n_boot=50)
        pt, _ = dg.estimate_passthrough(fit, model.price_model, params.l_normal_mw)
        eng = ScenarioEngine(fit, params, model, seed=0, passthrough=pt)
        pm = model.price_model
        seasons = {}
        for s in config.SEASONS:
            w = eng.base[s]
            rows = []
            for i in range(len(w)):
                r = {"date": str(w["date"].iloc[i].date()), "onpeak_day": bool(w["is_onpeak_day"].iloc[i]) if "is_onpeak_day" in w else None,
                     "load_normal_mw": float(w["load_normal_mw"].iloc[i])}
                r.update({c: float(w[c].iloc[i]) for c in COLS})
                rows.append(r)
            sc = model.season_cov[s]
            seasons[s] = {"rows": rows, "mu": [float(x) for x in sc.mu], "precision": np.asarray(sc.precision).tolist(),
                          "limits": {f: [float(model.limits[s][f][0]), float(model.limits[s][f][1])] for f in CORE + ("T",)},
                          "base_pnl": {k: float(v) for k, v in eng.base_pnl[s].items()}}
        cases = []
        for c in CASES:
            for s in config.SEASONS:
                o = eng(dict(c), season=s)
                cases.append({"season": s, "shock": c, "loss_usd": -o["pnl_total"], "pnl_by_position": o["pnl_by_position"], "pnl_by_channel": o["pnl_by_channel"],
                              "d2": o["d2"], "q": o["q"], "severity": o["severity"], "marginals_exceeded": o["marginals_exceeded"]})
        out = {
            "horizon_days": len(eng.base["winter"]), "target_usd": config.LOSS_TARGET_USD, "cap_usd": config.energy_cap_usd(),
            "month_to_season": {str(k): v for k, v in config.MONTH_TO_SEASON.items()},
            "passthrough": {k: getattr(pt, k) for k in ("gas_beta", "load_beta1", "load_beta2", "offpeak_scale", "phi_level", "phi_spread")},
            "book": {"sizes": params.sizes_mw, "k1": params.k1_usd, "c0": params.c0_usd, "k6": params.k6_usd, "r": params.r_usd, "h": params.h_usd,
                     "heat_rate": params.heat_rate, "vom": params.vom_usd, "p4_prem": params.p4_premium_usd, "p6_prem": params.p6_premium_usd,
                     "basis": params.basis_usd, "positions": list(config.POSITIONS), "channel": config.POSITION_CHANNEL},
            "price_model": {"intercepts": pm.intercepts, "b_gas": pm.b_gas, "b_load": pm.b_load, "b_load2": pm.b_load2, "harm": list(pm.harm),
                            "load_normal_by_month": {str(k): v for k, v in pm.load_normal_mw_by_month.items()}},
            "q": {"window_d2": [float(x) for x in model.window_d2], "adverse_max": config.Q_ADVERSE_MAX, "severe_max": config.Q_SEVERE_MAX},
            "weather_slopes": {"hdd": eng.weather.hdd, "cdd": eng.weather.cdd}, "t_extreme": {k: float(v) for k, v in model.t_extreme_threshold.items()},
            "seasons": seasons, "keys": KEYS, "reference_cases": cases,
        }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, default=float), encoding="utf-8")
    print(f"wrote {a.out} ({a.out.stat().st_size // 1024} KB), {len(cases)} reference cases")


if __name__ == "__main__":
    main()
