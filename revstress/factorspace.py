"""Factor-space position of a scenario, shared by the agent loop and the evaluation metrics.

Position = engine_out['z']: standardized core factors z_f = (x_worst_f - season median_f) / robust_sd_f in the
order config.GAUSSIAN_CORE_FACTORS. Unlike marginal percentiles it does not saturate beyond the historical
range, so extreme scenarios stay distinguishable. Distance is Euclidean in these z units; the threshold is
config.DISTINCT_TAU_Z.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from . import config


def z_vector(engine_out: Mapping[str, Any] | None) -> np.ndarray | None:
    """z-vector (config.GAUSSIAN_CORE_FACTORS order) from engine output, or None if 'z' is missing or incomplete."""
    z = (engine_out or {}).get("z")
    if not isinstance(z, Mapping) or any(f not in z for f in config.GAUSSIAN_CORE_FACTORS):
        return None
    return np.array([float(z[f]) for f in config.GAUSSIAN_CORE_FACTORS])
