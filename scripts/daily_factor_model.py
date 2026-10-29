"""Daily factor model of NYISO prices: each target explained by daily factors, scored walk-forward out of sample.

Targets: lw = log WEST on-peak, c = N.Y.C.-WEST on-peak spread ($), d = log(RT/DA) WEST on-peak.
Factor blocks (all daily, from data/processed/nyiso_panel.csv): gas g, load l (log peak), season harmonics (2) with
load x season, weather hdd/cdd, persistence (previous day's target). Expanding-window OLS, refit each year 2022-2025;
score = pooled out-of-sample R2 and RMSE. Offline, no network. Usage (from pjm_revstress): python -E -P scripts/daily_factor_model.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def build() -> pd.DataFrame:
    p = pd.read_csv(ROOT / "data/processed/nyiso_panel.csv", parse_dates=["date"])
    p = p[(p.date >= "2019-01-01") & (p.date <= "2025-12-31")].reset_index(drop=True)
    p["c"] = p.dom_on - p.wh_on
    p["lw"] = np.log(p.wh_on.clip(lower=1))
    p["d"] = np.log(p.rt_wh_on.clip(lower=1) / p.da_wh_on.clip(lower=1))
    p["g"] = np.log(p.hh_usd.clip(lower=0.5))
    p["l"] = np.log(p.load_peak_mw)
    doy = 2 * np.pi * p.date.dt.dayofyear / 365.25
    for j in (1, 2):
        p[f"sin{j}"], p[f"cos{j}"] = np.sin(j * doy), np.cos(j * doy)
    ls = p.l - p.l.mean()
    for h in ("sin1", "cos1"):
        p[f"l_{h}"] = ls * p[h]
    fm = ROOT / "data/processed/nyiso_fuelmix_daily.csv"
    if fm.exists():  # on-peak mean MW by fuel (scripts/ downloads: data/raw/nyiso_fuelmix, rtfuelmix)
        p = p.merge(pd.read_csv(fm, parse_dates=["date"]), on="date", how="left")
        p["net_load"] = np.log((p.load_peak_mw - p.fm_wind).clip(lower=1000))
    for t in ("lw", "c", "d"):
        p[f"lag_{t}"] = p[t].shift(1)
    return p.dropna().reset_index(drop=True)


BLOCKS = {
    "M0 gas+load": ["g", "l"],
    "M1 +season": ["g", "l", "sin1", "cos1", "sin2", "cos2", "l_sin1", "l_cos1"],
    "M2 +weather": ["g", "l", "sin1", "cos1", "sin2", "cos2", "l_sin1", "l_cos1", "hdd", "cdd"],
    "M3 +persistence": ["g", "l", "sin1", "cos1", "sin2", "cos2", "l_sin1", "l_cos1", "hdd", "cdd", "LAG"],
}
M2 = BLOCKS["M2 +weather"]
EXO = ["fm_wind", "fm_nuclear", "fm_hydro"]  # weather / outage driven, not set by the price
ENDO = ["fm_dual_fuel", "fm_natural_gas"]  # dispatch outcomes: simultaneous with price, diagnostic only
FUEL_BLOCKS = {
    "M4 M2+wind,nuclear,hydro": M2 + EXO,
    "M5 M2+net load": M2 + ["net_load"],
    "M6 M2+exo+dual/gas (endogenous)": M2 + EXO + ENDO,
    "M7 persistence+exo": BLOCKS["M3 +persistence"] + EXO,
}


def walk_forward(p: pd.DataFrame, target: str, cols: list[str], first_test_year: int = 2022) -> tuple[float, float, float]:
    cols = [f"lag_{target}" if c == "LAG" else c for c in cols]
    err, y_all, naive = [], [], []
    for yr in range(first_test_year, 2026):
        tr, te = p[p.date.dt.year < yr], p[p.date.dt.year == yr]
        X = np.column_stack([tr[cols].to_numpy(), np.ones(len(tr))])
        b = np.linalg.lstsq(X, tr[target].to_numpy(), rcond=None)[0]
        pred = np.column_stack([te[cols].to_numpy(), np.ones(len(te))]) @ b
        err.append(te[target].to_numpy() - pred)
        y_all.append(te[target].to_numpy())
        naive.append(te[target].to_numpy() - tr[target].mean())
    e, y, nv = map(np.concatenate, (err, y_all, naive))
    return 1 - (e ** 2).sum() / (nv ** 2).sum(), float(np.sqrt((e ** 2).mean())), float(np.corrcoef(e[1:], e[:-1])[0, 1])


def main() -> None:
    p = build()
    rows = []
    blocks = {**BLOCKS, **(FUEL_BLOCKS if "fm_wind" in p else {})}
    p = p.dropna().reset_index(drop=True)
    for t in ("lw", "c", "d"):
        for name, cols in blocks.items():
            r2, rmse, ac = walk_forward(p, t, cols)
            rows.append({"target": t, "model": name, "oos_r2": round(r2, 3), "oos_rmse": round(rmse, 3), "resid_autocorr": round(ac, 2)})
    out = pd.DataFrame(rows)
    d = ROOT / "outputs" / "daily_model"
    d.mkdir(parents=True, exist_ok=True)
    out.to_csv(d / "walk_forward.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
