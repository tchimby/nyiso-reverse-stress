"""Baselines for the equal-budget comparison (plan section 8D)."""

from .common import FactorSpec, SpikeOverlay, classify_driver, default_hard_rules, factors_to_shock, template_narrative
from .cond_gaussian import cond_gaussian_search
from .optimizer import optimizer_search
from .random_search import random_search

__all__ = [
    "FactorSpec",
    "SpikeOverlay",
    "classify_driver",
    "default_hard_rules",
    "factors_to_shock",
    "template_narrative",
    "cond_gaussian_search",
    "optimizer_search",
    "random_search",
]
