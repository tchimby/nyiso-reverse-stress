"""Project constants. Prices in $/MWh, power in MW, time in days or hours (plan sections 3-6)."""

from __future__ import annotations

from . import market as _market

# Active market (read at call time so tests can monkeypatch). PJM is the default; NYISO is selected explicitly.
MARKET: str = "PJM"


def active_market() -> _market.Market:
    """The Market selected by config.MARKET."""
    return _market.get_market(MARKET)


def energy_cap_usd() -> float:
    """Price cap of the active market, $/MWh (NYISO: 5,000 scenario cap, a stated assumption)."""
    return active_market().energy_cap_usd

# Hours per day
ON_PEAK_HOURS: int = 16
OFF_PEAK_HOURS: int = 8
DAY_HOURS: int = ON_PEAK_HOURS + OFF_PEAK_HOURS

# Capital and target loss (USD)
ALLOCATED_CAPITAL_USD: float = 20e6
# Loss target (USD): the plan's 25% of capital. The book sizes below were re-set (see BOOK-SIZE SELECTION RULE) so that this
# target is a tail event of the NYISO book. History of this constant: with the plan's starting sizes the target was reached
# by 'ordinary' worlds (conditional-Gaussian rank q about 0.075 > Q_ADVERSE_MAX), so no arm could breach; an earlier
# build raised the target to 7M (35%), which was fragile (6M: 2 breaches, 8M: 3) instead of fixing the book. The target is
# back at 5M and the sizes moved.
LOSS_TARGET_USD: float = 5e6  # 25% of ALLOCATED_CAPITAL_USD

# PJM maximum shortage ENERGY component of LMP, $/MWh (2000 offer cap + 2 x 850). Not a cap on total LMP.
# Kept for the PJM default; code that must follow the active market calls energy_cap_usd().
ENERGY_COMPONENT_CAP_USD: float = _market.PJM.energy_cap_usd

# BOOK-SIZE SELECTION RULE (written BEFORE the size scan was run; plan section 3 says the starting sizes are to be
# re-set so that the target loss is a meaningful tail event at NYISO price scale). Keep the six positions and the
# formulas; only the sizes (MW) change; the target stays 5,000,000 USD (25% of capital). Candidates are size vectors on
# a grid. For each candidate, on the real panel with fit window 2019-2025 and the same ScenarioEngine as pipeline_real,
# run the conditional-Gaussian arm at rng seeds 0, 1, 2 with budget 144 engine calls per season (winter, summer,
# shoulder) and tau = DISTINCT_TAU_Z. A breach is the plan's definition (loss >= target AND q < 5% AND hard rules passed
# AND severity not implausible). Per seed the three seasons are pooled. A candidate is ADMISSIBLE if
#   (a) the conditional-Gaussian arm finds >= 5 distinct breaches in EVERY seed;
#   (b) the largest single position's loss, as a share of the net scenario loss, averaged over the 5 distinct breaches
#       with the largest loss in each seed (then over seeds), is <= 0.60;
#   (c) the distinct breaches (pooled over seeds) have >= 2 different largest-loss channels and lie in >= 2 seasons;
#   (d) the worst historical rolling-30-day book loss over the 2019-2025 fit window is between 50% and 100% of the
#       target (the existing sizing_check rule).
# Among admissible candidates take the one with the highest minimum over seeds of the number of distinct breaches
# (ties: lower (b) share, then smaller gross MW). If none is admissible, relax (c) first and then (b), in that order,
# and say so. The target is NOT moved away from 5M unless no candidate reaches (a) even with (b)-(d) dropped; in that case
# this is reported loudly with the smallest alternative target.
# RESULT of that scan (93 candidates: P5 120-180 with P2 25-75, P1 50-150, P4 50-100, plus P3/P6 variants and the old book; the
# 'ordinary world' cliff is on both sides: below about 120 MW of P5 the 5M loss is not reached plausibly, above it the minimum-D^2 world is
# ordinary by rank). No candidate met (b) or (c); the largest-position share was 1.0 to 1.6 for every candidate with any breach, and every
# breach was a winter zone_volume world. Relaxing (c) then (b) as stated left 11 candidates meeting (a) and (d); the winner had 6, 7, 6
# distinct breaches in seeds 0, 1, 2, share 1.10, worst historical 30-day loss 3.22M (64% of target). Sizes: P1 100, P2 25, P3 50, P4 50,
# P5 140, P6 25 (gross 390 MW; hedge ratio P2/P5 = 0.18; the old book was 50, 50, 25, 100, 200, 25 and had 0 breaches in all seeds at 5M).
# The target stayed at 5M. See README 'Book sizes and loss target' for what this does not achieve.
# RECALIBRATION RULE v3 (written 2026-10-28 BEFORE the v3 scan was run). Reason: the daily-model engine (seasonal harmonics in the price model
# and a persistence tail after the shock, DAILY_PERSISTENCE) raises the loss of a given shock by about 15-20%, so the 5M target became reachable
# by ordinary worlds (cond-Gaussian 0.2 breaches per repeat vs 4.4 before). Rule v1 above is re-applied UNCHANGED (conditions a-d, relax c then
# b, same tie-breaks, target kept at 5M) on the new engine over a grid of smaller sizes: P1 {50,100,150}, P2 {25,50}, P3 {50}, P4 {50,100},
# P5 {80,100,120,140}, P6 {25} (48 candidates, scripts/scan_book_v3.py, outputs/book_scan_v3/scan_v3.json). The new sizes replace POSITION_SIZES_MW
# only if the rule selects a candidate; the result is recorded below the table of sizes.
# RESULT v3 (scan run 2026-10-29, outputs/book_scan_v3/scan_v3.json, 48 candidates x 3 seeds): NO candidate is admissible under rule v1, even with (c) and
# (b) relaxed: the best candidates reach only 4 distinct breaches in their weakest seed (condition a needs 5), 30 of 48 also fail (d) (worst 30-day loss
# below 50% of the target), and all 48 fail (b) and (c) (one season, one channel). The rule says to report this loudly. DECISION (user, 2026-10-29): keep
# the sizes below and the 5M target, run with persistence ON, and report that rule v1 is NOT met on the daily-model engine (4 of 5 required).
# MULTI-CHANNEL BOOK RULE v2 (written 2026-10-28 BEFORE the v2 scan was run; the scan code is scripts/scan_book_v2.py and the
# conditions as code are in eval/sizing.py, functions failed_conditions_v2 / select_candidate_v2). Why: the v1 book above has
# one story (winter N.Y.C.-WEST spread, P5 = 110% of the loss). v2 asks for a book in which several channels can carry the loss.
# Levers allowed (the six positions and the formulas stay; target stays 5M, capital 20M):
#   - sizes on the grid P1 in {-100,-50,50,100} (negative = SHORT swap, loses when WEST on-peak rises), P2 in {25,50},
#     P3 in {50,100,150}, P4 in {50,100}, P5 in {100,120,140}, P6 in {25,50,100} MW (432 candidates);
#   - option premiums are NOT scanned: fixed by rule at the fair value on the fit sample, p4_premium = mean P4 payoff per
#     on-peak MWh, p6_premium = mean P6 call payoff per on-peak MWh (book.fit_book_params). NOTE: the scenario engine reports the
#     SHOCK-ATTRIBUTABLE P&L (shocked path minus zero-shock path of the same window), so a constant premium cancels there; premiums
#     only change absolute P&L (replay, historical rolling-30d check).
# Procedure: as v1 (conditional-Gaussian arm, rng seeds 0, 1, 2, winter / summer / shoulder pooled, budget 144 per season, tau =
# DISTINCT_TAU_Z, breach = loss >= target AND q < 5% AND hard rules passed AND severity not implausible).
# A candidate is ADMISSIBLE if ALL of:
#   (a) >= 5 distinct breaches in EVERY seed;
#   (b) mean over seeds of the mean largest-single-position share of the net loss, over the 5 largest-loss distinct breaches, <= 0.60;
#   (c2) pooled over seeds: at least 2 dominant (largest-loss) channels that each carry >= 3 distinct breaches, at least 2 seasons that
#        each hold >= 3 distinct breaches, and no channel carries more than 75% of all distinct breaches;
#   (d) worst historical rolling-30d book loss over the 2019-2025 fit window within 50%-100% of the target.
# Selection: highest minimum-over-seeds breach count, ties lower share, then smaller gross MW. NO relaxation: if no candidate is
# admissible the failure is reported, and the book adopted is the candidate that fails the fewest conditions (ties: more channels
# with >= 3 breaches, then higher min breaches) only if it fails strictly fewer than the v1 book, else the v1 book is kept.
# Verification (out of sample for the selection rng): the offline demo (seed 0, budget 144, 5 repeats) must show, for the
# optimizer and the conditional-Gaussian arm each, distinct breaches in >= 2 channels and >= 2 seasons. Plausibility thresholds
# (q < 0.05, hard rules, severity) are NOT changed to make breaches pass.
# RESULT v2 (scan run 2026-10-28, outputs/book_scan_v2/scan_v2.json, 432 candidates x 3 seeds): NO candidate is admissible. 18 candidates pass (a) and (d)
# and all 432 fail (c2): every one of the 468 pooled distinct breaches is a winter zone_volume (P5) world. Short-P1 candidates (-100, -50) reach 5M only in worlds
# classed 'implausible' (loss 54-167M at the cond-Gaussian point; summer/shoulder marginal limits hit), so they have 0 breaches. Per the rule, no relaxation: the
# v1 book (P1 100, P2 25, P3 50, P4 50, P5 140, P6 25) is kept (it fails b and c2, like the best candidates), now with fair-value premiums. Failed condition: c2 (and b).
# Position sizes in MW (plan section 3). P5 is the base volume, scaled by L_d / L_normal.
POSITION_SIZES_MW: dict[str, float] = {
    "P1": 100.0,
    "P2": 25.0,
    "P3": 50.0,
    "P4": 50.0,
    "P5": 140.0,
    "P6": 25.0,
}
# Daily-model persistence (2026-10-28): after a shock ends, the price-level and spread effects decay geometrically with the AR(1)
# coefficients of s and c (about 0.55 and 0.59) instead of vanishing. False reproduces the earlier snap-back engine.
DAILY_PERSISTENCE: bool = True

POSITIONS: tuple[str, ...] = ("P1", "P2", "P3", "P4", "P5", "P6")
FALLBACK_POSITIONS: tuple[str, ...] = ("P1", "P4", "P6")

# When True, the book contains only FALLBACK_POSITIONS (EIA/ICE fallback, plan section 10).
FALLBACK_BOOK: bool = False

POSITION_CHANNEL: dict[str, str] = {
    "P1": "system",
    "P2": "congestion",
    "P3": "dart",
    "P4": "gas",
    "P5": "zone_volume",
    "P6": "tail",
}
CHANNELS: tuple[str, ...] = ("system", "congestion", "dart", "gas", "zone_volume", "tail")

# Contract terms (plan section 3)
HEAT_RATE_MMBTU_PER_MWH: float = 8.0
VOM_USD_PER_MWH: float = 3.0
SPIKE_STRIKE_QUANTILE: float = 0.99  # K6 = this quantile of daily on-peak WH average in the fit sample
RETAIL_ZONE: str = "DOM"  # zone for P5 (decision of the student's delegate)

# Stated gas basis assumptions, $/MMBtu added to Henry Hub. These are ASSUMPTIONS, not fitted.
# Winter and summer values are the plan's examples; the shoulder value is their midpoint.
GAS_BASIS_USD: dict[str, float] = _market.PJM.gas_basis_by_season  # PJM default


def gas_basis_by_season() -> dict[str, float]:
    """Stated seasonal gas basis of the active market, $/MMBtu (ASSUMPTIONS; NYISO values are placeholders, no daily
    New York gas history exists in the keyless data set, plan section 4)."""
    return active_market().gas_basis_by_season

# Seasons by calendar month
SEASON_MONTHS: dict[str, tuple[int, ...]] = {
    "winter": (12, 1, 2),
    "summer": (6, 7, 8),
    "shoulder": (3, 4, 5, 9, 10, 11),
}
MONTH_TO_SEASON: dict[int, str] = {m: s for s, ms in SEASON_MONTHS.items() for m in ms}
SEASONS: tuple[str, ...] = ("winter", "summer", "shoulder")

# Factors x_t = [g, l, T, s, c, d]; the Gaussian core excludes T (plan section 4)
FACTOR_NAMES: tuple[str, ...] = ("g", "l", "T", "s", "c", "d")
GAUSSIAN_CORE_FACTORS: tuple[str, ...] = ("g", "l", "s", "c", "d")

# Shock vector keys (plan section 5) with neutral values
SHOCK_KEYS: tuple[str, ...] = (
    "gas_hh_pct",
    "load_peak_ratio",
    "dc_load_shock_mw",
    "wh_onpeak_pct",
    "dom_minus_wh_usd",
    "dart_pct",
    "spike_days",
    "spike_daily_avg_usd",
    "duration_days",
)
# Engine shock keys outside SHOCK_KEYS: accepted by shock.validate_shock, default 0, not filled when absent.
OPTIONAL_SHOCK_KEYS: tuple[str, ...] = ("ny_gas_basis_usd",)
NEUTRAL_SHOCK: dict[str, float] = {
    "gas_hh_pct": 0.0,
    "load_peak_ratio": 1.0,
    "dc_load_shock_mw": 0.0,
    "wh_onpeak_pct": 0.0,
    "dom_minus_wh_usd": 0.0,
    "dart_pct": 0.0,
    "spike_days": 0,
    "spike_daily_avg_usd": 0.0,
    "duration_days": 0,
}

DRIVER_CLASSES: tuple[str, ...] = (
    "cold_snap",
    "heat_wave",
    "gas_supply",
    "transmission",
    "demand_shock_datacenter",
    "generator_outage",
    "policy",
)

# Structural-break dates (ISO). None = not verified (plan section 4).
# PJM breaks (default market); the active market's breaks come from structural_breaks().
STRUCTURAL_BREAKS: dict[str, str | tuple[str, str] | None] = _market.PJM.structural_break_dates


def structural_breaks() -> dict[str, str | tuple[str, str] | None]:
    """Structural-break dates of the active market (NYISO: 2016-06-22 scarcity pricing, Indian Point 2020-04 and 2021-04,
    2023-11-14 transmission shortage pricing)."""
    return active_market().structural_break_dates


def break_cutoff() -> str:
    """ISO date before which data is dropped when pre-break data is excluded (active market's primary break)."""
    return active_market().primary_break_cutoff

# Plausibility and agent-loop settings (plan sections 4-5)
SPIKE_SEASON_PERCENTILE: float = 97.5
Q_ADVERSE_MAX: float = 0.05
Q_SEVERE_MAX: float = 0.01
IMPLAUSIBLE_MARGINAL_MULT: float = 1.25
WINDOW_DAYS: int = 10
ITERATIONS_PER_SEED: int = 12
N_SEEDS: int = 4
SCENARIOS_PER_CALL: int = 3
EARLY_STOP_BREACHES: int = 5
N_REPEATS: int = 5  # independent repeats per arm (plan section 8D: at least 5)
# Seed driver families of the main protocol (plan section 5: 4 seeds, one per driver family) and the season each
# is run in. This choice of four of the seven classes is an ASSUMPTION of the build, not stated in the plan.
SEED_FAMILIES: tuple[tuple[str, str], ...] = (
    ("cold_snap", "winter"),
    ("heat_wave", "summer"),
    ("gas_supply", "winter"),
    ("demand_shock_datacenter", "shoulder"),
)
# Distinctness threshold between breaching scenarios: Euclidean distance in robust z units of the core
# factors (engine output 'z'). PLACEHOLDER until chosen on real data. Shared by the loop and the metrics.
DISTINCT_TAU_Z: float = 1.0

# Claude model; the API key is read from the ANTHROPIC_API_KEY environment variable only.
DEFAULT_MODEL: str = "claude-sonnet-5-5"
