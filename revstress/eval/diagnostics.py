"""Fit diagnostics for the risk model on a real panel (plan sec 4): regression table, residual checks,
covariance conditioning, spike summary, PCA variance check, pass-through estimates and book sizing check.

Units: prices $/MWh, load MW, gas $/MMBtu, P&L USD. Nothing here touches the network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .. import config
from ..book import BookParams, pnl
from ..panel import season_labels
from ..risk.factors import GAS_FLOOR_USD, PRICE_FLOOR_USD, PriceModel, _design, compute_factors, load_normal_mw
from ..risk.plausibility import RiskModel, _windows
from ..shock import PassThrough

REG_NAMES: tuple[str, ...] = ("a_winter", "a_summer", "a_shoulder", "b_gas", "b_load", "b_load2")
HAC_LAGS: int = 10
PCA_TARGET_SHARE: float = 0.85
PRICE_BLOCK: tuple[str, ...] = ("wh_on", "wh_off", "dom_on", "dom_off", "da_wh_on", "da_wh_off")


def _xy(df: pd.DataFrame, model: PriceModel, col: str = "wh_on") -> tuple[np.ndarray, np.ndarray]:
    g = np.log(np.maximum(df["hh_usd"].to_numpy(dtype=float), GAS_FLOOR_USD))
    l = np.log(df["load_peak_mw"].to_numpy(dtype=float) / load_normal_mw(df["date"], model))
    y = np.log(np.maximum(df[col].to_numpy(dtype=float), PRICE_FLOOR_USD))
    return _design(g, l, season_labels(df["date"])), y


def _newey_west(X: np.ndarray, u: np.ndarray, lags: int) -> np.ndarray:
    """Newey-West (Bartlett) covariance of the OLS coefficients."""
    n = len(u)
    xtx_inv = np.linalg.inv(X.T @ X)
    xu = X * u[:, None]
    S = xu.T @ xu
    for k in range(1, lags + 1):
        w = 1.0 - k / (lags + 1.0)
        G = xu[k:].T @ xu[:-k]
        S += w * (G + G.T)
    return xtx_inv @ S @ xtx_inv


def regression_table(df: pd.DataFrame, model: PriceModel, col: str = "wh_on") -> tuple[pd.DataFrame, dict]:
    """OLS of log(col) on season intercepts, g, l, l^2 with classical and Newey-West (10 lags) standard errors.

    Returns (table with coef, se_ols, se_hac, t_hac, p_hac; stats dict with n, r2, adj_r2, resid_sd).
    """
    X, y = _xy(df, model, col)
    n, k = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    s2 = float(u @ u) / (n - k)
    se_ols = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    se_hac = np.sqrt(np.diag(_newey_west(X, u, HAC_LAGS)))
    t = beta / se_hac
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(u @ u) / ss_tot
    tab = pd.DataFrame(
        {"coef": beta, "se_ols": se_ols, "se_hac": se_hac, "t_hac": t, "p_hac": 2 * stats.norm.sf(np.abs(t))},
        index=list(REG_NAMES),
    )
    return tab, {"n": int(n), "r2": r2, "adj_r2": 1.0 - (1.0 - r2) * (n - 1) / (n - k), "resid_sd": float(np.sqrt(s2))}


def residual_diagnostics(df: pd.DataFrame, model: PriceModel) -> dict:
    """Residual checks of the log WEST on-peak regression: shape, autocorrelation, tails, floor hits."""
    X, y = _xy(df, model)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    n = len(u)
    jb = stats.jarque_bera(u)
    ac = [float(np.corrcoef(u[k:], u[:-k])[0, 1]) for k in range(1, 11)]
    q = n * (n + 2) * sum(a * a / (n - k) for k, a in zip(range(1, 11), ac))
    seasons = season_labels(df["date"])
    sd = float(u.std(ddof=1))
    return {
        "n": int(n),
        "mean": float(u.mean()),
        "sd": sd,
        "skew": float(stats.skew(u)),
        "excess_kurtosis": float(stats.kurtosis(u)),
        "jarque_bera_p": float(jb.pvalue),
        "autocorr_lag1": ac[0],
        "ljung_box_10_stat": float(q),
        "ljung_box_10_p": float(stats.chi2.sf(q, 10)),
        "durbin_watson": float(np.sum(np.diff(u) ** 2) / np.sum(u**2)),
        "share_abs_gt_3sd": float(np.mean(np.abs(u) > 3 * sd)),
        "resid_sd_by_season": {s: float(u[seasons == s].std(ddof=1)) for s in config.SEASONS if (seasons == s).any()},
        "price_floor_hits": {c: int((df[c] < PRICE_FLOOR_USD).sum()) for c in ("wh_on", "rt_wh_on", "da_wh_on")},
    }


def covariance_conditioning(model: RiskModel) -> dict:
    """Per-season covariance of the Gaussian core: sample size, shrinkage and conditioning.

    cond_cov depends on the units of the factors (c is in $/MWh, the rest are logs); cond_corr is unit-free.
    """
    out: dict = {}
    for s, sc in model.season_cov.items():
        sd = np.sqrt(np.diag(sc.cov))
        corr = sc.cov / np.outer(sd, sd)
        ev = np.linalg.eigvalsh(sc.cov)
        evc = np.linalg.eigvalsh(corr)
        out[s] = {
            "n_obs": int(sc.n_obs),
            "window": [str(sc.start.date()), str(sc.end.date())],
            "method": sc.method,
            "shrinkage": sc.shrinkage,
            "cond_cov": float(ev[-1] / ev[0]),
            "cond_corr": float(evc[-1] / evc[0]),
            "min_eig_corr": float(evc[0]),
            "sd": {f: float(v) for f, v in zip(config.GAUSSIAN_CORE_FACTORS, sd)},
        }
    return out


def spike_summary(model: RiskModel) -> dict:
    """Spike model summary: thresholds ($/MWh), exceedance rate, GPD shape with bootstrap range, logistic terms."""
    sp = model.spike
    return {
        "percentile": config.SPIKE_SEASON_PERCENTILE,
        "thresholds_usd": dict(sp.thresholds_usd),
        "exceedance_share_by_season": dict(sp.hist_exceed_share),
        "exceedance_rate_overall": float(sp.n_exceed / sp.n_days),
        "n_exceed": int(sp.n_exceed),
        "n_days": int(sp.n_days),
        "gpd_shape": sp.gpd_shape,
        "gpd_scale": sp.gpd_scale,
        "gpd_shape_bootstrap_5_95": list(sp.gpd_shape_range) if sp.gpd_shape_range else None,
        "logistic_coef_l_T": list(sp.coef),
        "logistic_intercept": sp.intercept,
        "max_relative_excess": float(sp.relative_excesses.max()) if len(sp.relative_excesses) else None,
    }


def pca_check(df: pd.DataFrame, factors: pd.DataFrame, columns: tuple[str, ...] = PRICE_BLOCK) -> dict:
    """PCA diagnostic that the explicit factors [g, l, T, s, c, d] explain most of the price block.

    Block = standardized log of six daily price series (WEST and N.Y.C. on/off RT, WEST DA on/off).
    explained_share_by_factors = share of the block's total variance explained by OLS on [1, g, l, T, s, c, d]
    (linear projection on the factor span, no season terms). Also reports how many principal components of the
    block reach 85% and the factor R^2 of each of the first three components. By construction s, c and d are
    differences of the block members, so a high share partly reflects the factor definitions.
    """
    Y = np.log(np.maximum(df[list(columns)].to_numpy(dtype=float), PRICE_FLOOR_USD))
    Y = (Y - Y.mean(0)) / Y.std(0, ddof=1)
    F = factors[list(config.FACTOR_NAMES)].to_numpy(dtype=float)
    Xf = np.column_stack([np.ones(len(F)), F])
    B, *_ = np.linalg.lstsq(Xf, Y, rcond=None)
    R = Y - Xf @ B
    share = 1.0 - float((R**2).sum() / (Y**2).sum())
    per_col = {c: 1.0 - float((R[:, j] ** 2).sum() / (Y[:, j] ** 2).sum()) for j, c in enumerate(columns)}
    u, sv, vt = np.linalg.svd(Y, full_matrices=False)
    ev = sv**2 / (sv**2).sum()
    cum = np.cumsum(ev)
    pcs = Y @ vt.T
    pc_r2 = []
    for j in range(min(3, pcs.shape[1])):
        b, *_ = np.linalg.lstsq(Xf, pcs[:, j], rcond=None)
        r = pcs[:, j] - Xf @ b
        pc_r2.append(1.0 - float((r**2).sum() / ((pcs[:, j] - pcs[:, j].mean()) ** 2).sum()))
    core = factors[list(config.GAUSSIAN_CORE_FACTORS)].to_numpy(dtype=float)
    core = (core - core.mean(0)) / core.std(0, ddof=1)
    evf = np.linalg.svd(core, compute_uv=False) ** 2
    evf = evf / evf.sum()
    return {
        "block": list(columns),
        "explained_share_by_factors": share,
        "explained_share_per_series": per_col,
        "target": PCA_TARGET_SHARE,
        "meets_target": bool(share > PCA_TARGET_SHARE),
        "block_pc_cumulative_share": [float(x) for x in cum],
        "n_pcs_for_85pct": int(np.searchsorted(cum, PCA_TARGET_SHARE) + 1),
        "factor_r2_of_first_3_pcs": pc_r2,
        "core_factor_pc_share": [float(x) for x in evf],
    }


def estimate_passthrough(df: pd.DataFrame, model: PriceModel, l_normal_mw: float | None = None) -> tuple[PassThrough, dict]:
    """PassThrough from the real regression: gas_beta = b1, load_beta1 = b2, load_beta2 = b3 of the on-peak fit;
    offpeak_scale = (off-peak b2 / on-peak b2) clipped to [0, 1.5]. Returns (PassThrough, detail dict)."""
    on, _ = regression_table(df, model, "wh_on")
    off, _ = regression_table(df, model, "wh_off")
    scale = float(np.clip(off.loc["b_load", "coef"] / on.loc["b_load", "coef"], 0.0, 1.5))
    fac = compute_factors(df, model)
    phi_s, phi_c = (float(np.clip(np.corrcoef(fac[k].to_numpy()[1:], fac[k].to_numpy()[:-1])[0, 1], 0.0, 0.9)) for k in ("s", "c"))
    pt = PassThrough(
        phi_level=phi_s if config.DAILY_PERSISTENCE else 0.0,
        phi_spread=phi_c if config.DAILY_PERSISTENCE else 0.0,
        gas_beta=float(on.loc["b_gas", "coef"]),
        load_beta1=float(on.loc["b_load", "coef"]),
        load_beta2=float(on.loc["b_load2", "coef"]),
        offpeak_scale=scale,
        l_normal_mw=l_normal_mw,
    )
    detail = {
        "placeholder": {"gas_beta": 0.6, "load_beta1": 2.0, "load_beta2": 6.0, "offpeak_scale": 0.5},
        "estimated": {"phi_level": phi_s, "phi_spread": phi_c, "gas_beta": pt.gas_beta, "load_beta1": pt.load_beta1, "load_beta2": pt.load_beta2, "offpeak_scale": scale},
        "offpeak_b_load": float(off.loc["b_load", "coef"]),
    }
    return pt, detail


def sizing_check(panel: pd.DataFrame, params: BookParams, horizon_days: int = 30, target_usd: float = config.LOSS_TARGET_USD) -> dict:
    """Book scale check (plan sec 3): rolling horizon_days book loss distribution on the fit sample vs the target.

    Rule: sizes are kept if the worst historical rolling-horizon loss lies between 50% and 100% of the target
    (so the target needs a world at least as bad as the worst fitted month, and is attainable). Otherwise all
    sizes are multiplied by k = 0.75 * target / worst_loss. Returns the statistics and the verdict.
    """
    pl = pnl(panel, params)
    roll = pl[["total", "P5", "P4", "P1", "P2", "P3", "P6"]].rolling(horizon_days).sum().dropna()
    worst = float(-roll["total"].min())
    ratio = worst / target_usd
    keep = 0.5 <= ratio <= 1.0
    return {
        "horizon_days": horizon_days,
        "target_usd": target_usd,
        "capital_usd": config.ALLOCATED_CAPITAL_USD,
        "worst_1d_loss_usd": float(-pl["total"].min()),
        "worst_10d_loss_usd": float(-pl["total"].rolling(10).sum().min()),
        "worst_30d_loss_usd": worst,
        "p1_30d_loss_usd": float(-roll["total"].quantile(0.01)),
        "worst_30d_loss_over_target": ratio,
        "n_windows_ge_target": int((-roll["total"] >= target_usd).sum()),
        "worst_window_end": str(pd.Timestamp(pl["date"].iloc[roll["total"].to_numpy().argmin() + horizon_days - 1]).date()),
        "total_pnl_usd": float(pl["total"].sum()),
        "pnl_by_position_usd": {p: float(pl[p].sum()) for p in config.POSITIONS},
        "keep_sizes": bool(keep),
        "suggested_scale": 1.0 if keep else float(0.75 / ratio),
        "rule": (
            f"keep sizes if 0.5 <= worst rolling-{horizon_days}d loss / {target_usd / 1e6:g}M <= 1.0, "
            f"else scale all sizes by 0.75 * {target_usd / 1e6:g}M / worst loss"
        ),
    }


def window_d2_by_length(model: RiskModel, lengths: tuple[int, ...] = (5, 10, 14)) -> dict[int, np.ndarray]:
    """Max-daily-D^2 of the historical non-overlapping windows of each length (days), from the fitted model's daily D^2.

    The model's own rank q uses config.WINDOW_DAYS (10); this gives the same construction for other lengths, for the
    sensitivity table (eval.metrics.sensitivity_table). Blocks with a calendar gap are dropped, as in the model.
    """
    return {int(n): _windows(model.history, int(n))[0] for n in lengths}
