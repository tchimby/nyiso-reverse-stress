"""Factor diagnostics for the report: correlations of the five core factors by season, PCA shares, worst D^2 days.

Usage (repo root): python -E -P scripts/factor_report.py     -> outputs/factors/{corr_by_season.csv, pca_shares.csv, worst_d2_days.csv, corr_by_season.png}
Reads data/processed/nyiso_panel.csv only; no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from revstress import pipeline_real as pr  # noqa: E402
from revstress.risk import fit_risk_model  # noqa: E402

CORE = ["g", "l", "s", "c", "d"]


def main() -> None:
    out = ROOT / "outputs" / "factors"
    out.mkdir(parents=True, exist_ok=True)
    with pr.nyiso_market():
        _, fit = pr.load_real_panel()
        h = fit_risk_model(fit, as_of=pr.FIT_END, seed=0, n_boot=50).history
    rows, mats = [], {}
    for s, g in h.groupby("season"):
        x = g[CORE] - g[CORE].mean()
        c = x.corr()
        mats[s] = c
        for i, a in enumerate(CORE):
            for b in CORE[i + 1:]:
                rows.append({"season": s, "pair": f"{a}-{b}", "corr": round(float(c.loc[a, b]), 3), "n_days": len(g)})
    pd.DataFrame(rows).to_csv(out / "corr_by_season.csv", index=False)
    z = (h[CORE] - h[CORE].mean()) / h[CORE].std()
    ev = np.linalg.eigvalsh(np.cov(z.T))[::-1]
    pd.DataFrame({"component": range(1, 6), "variance_share": np.round(ev / ev.sum(), 3), "cumulative": np.round(np.cumsum(ev) / ev.sum(), 3)}).to_csv(out / "pca_shares.csv", index=False)
    h.nlargest(10, "d2")[["date", "season"] + CORE + ["d2"]].round(3).to_csv(out / "worst_d2_days.csv", index=False)
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.8))
    for ax, s in zip(axs, ["winter", "summer", "shoulder"]):
        c = mats[s].to_numpy()
        im = ax.imshow(c, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(5), CORE)
        ax.set_yticks(range(5), CORE)
        ax.set_title(f"{s} ({int((h.season == s).sum())} days)")
        for i in range(5):
            for j in range(5):
                ax.text(j, i, f"{c[i, j]:.2f}", ha="center", va="center", fontsize=8, color="white" if abs(c[i, j]) > 0.6 else "black")
    fig.colorbar(im, ax=axs, shrink=0.8, label="correlation")
    fig.suptitle("Correlation of the five core factors by season (2019-2025, deviations from the season mean)")
    fig.savefig(out / "corr_by_season.png", dpi=130, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main()
