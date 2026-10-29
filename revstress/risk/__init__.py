"""Risk engine (plan sec 4): factors, robust covariance, spike model, plausibility scoring."""

from .covariance import SeasonCov, fit_all_seasons, fit_season_cov, mahalanobis_sq
from .factors import PriceModel, compute_factors, fit_price_model
from .plausibility import RiskModel, fit_risk_model, score_scenario, severity_class, standardize_core
from .spike import SpikeModel, fit_spike_model, spike_exceedance, spike_probability

__all__ = [
    "PriceModel",
    "RiskModel",
    "SeasonCov",
    "SpikeModel",
    "compute_factors",
    "fit_all_seasons",
    "fit_price_model",
    "fit_risk_model",
    "fit_season_cov",
    "fit_spike_model",
    "mahalanobis_sq",
    "score_scenario",
    "severity_class",
    "standardize_core",
    "spike_exceedance",
    "spike_probability",
]
