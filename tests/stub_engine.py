"""Stub engine for tests: a made-up analytic loss and plausibility model. Not a risk model, not data."""

from __future__ import annotations

import numpy as np
from scipy.stats import chi2, norm

from revstress.baselines.common import FACTOR_ORDER, FactorSpec

STUB_CORR = np.array(
    [
        [1.0, 0.3, 0.2, 0.0, 0.0],
        [0.3, 1.0, 0.4, 0.2, 0.0],
        [0.2, 0.4, 1.0, 0.3, 0.1],
        [0.0, 0.2, 0.3, 1.0, 0.0],
        [0.0, 0.0, 0.1, 0.0, 1.0],
    ]
)
STUB_SD = np.array([0.05, 0.04, 0.10, 8.0, 0.08])


def stub_spec() -> FactorSpec:
    """Factor spec with made-up mean 0 and covariance."""
    return FactorSpec(mu=np.zeros(5), cov=STUB_CORR * np.outer(STUB_SD, STUB_SD))


def stub_engine_fn(spec: FactorSpec | None = None):
    """Return engine_fn(shock) -> engine result dict with the documented keys."""
    spec = spec or stub_spec()
    sd = spec.sd

    def engine(shock: dict) -> dict:
        if shock["duration_days"] < 0 or shock["load_peak_ratio"] <= 0:
            raise ValueError("bad shock")
        x = np.array(
            [
                np.log1p(shock["gas_hh_pct"] / 100.0),
                np.log(shock["load_peak_ratio"]),
                np.log1p(shock["wh_onpeak_pct"] / 100.0),
                shock["dom_minus_wh_usd"],
                np.log1p(shock["dart_pct"] / 100.0),
            ]
        )
        dur = shock["duration_days"]
        system = -dur * 1e4 * (shock["load_peak_ratio"] - 1.0) * 100.0
        congestion = -dur * 3e3 * max(shock["dom_minus_wh_usd"], 0.0)
        tail = -shock["spike_days"] * 400.0 * max(shock["spike_daily_avg_usd"] - 250.0, 0.0)
        z = x / sd
        d2 = spec.d2(x)
        marginals = {f: float(norm.cdf(v)) for f, v in zip(FACTOR_ORDER, z)}
        q = float(chi2.sf(d2, 5))
        severity = "implausible" if np.abs(z).max() > 6 else ("severe" if q < 0.01 else "adverse" if q <= 0.05 else "normal")
        by_channel = {"system": system, "congestion": congestion, "dart": 0.0, "gas": 0.0, "zone_volume": 0.0, "tail": tail}
        return {
            "pnl_total": float(sum(by_channel.values())),
            "pnl_by_position": {},
            "pnl_by_channel": by_channel,
            "d2": d2,
            "q": q,
            "marginals": marginals,
            "z": dict(zip(FACTOR_ORDER, map(float, z))),
            "nearest_date": "2022-12-23",
            "severity": severity,
            "spike_exceedance": 0.0,
        }

    return engine
