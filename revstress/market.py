"""Market definitions (plan section 12): one frozen Market per power market, selected by name.

PJM is the default so the PJM-era code and tests are unchanged; NYISO is selected explicitly
(config.MARKET = "NYISO", or a market= argument where a function takes one).

Internal panel/shock column names keep the PJM-era prefixes (plan section 12, decision already made):
wh_* = the market's reference zone (PJM Western Hub, NYISO WEST), dom_* = its load pocket (PJM Dominion,
NYISO N.Y.C.). The agent-facing shock keys differ for NYISO (see Market.shock_key_map); the mapping is applied at the
agent boundary by agent.rules.to_engine_shocks.

NYISO prices have no visible hard cap on LBMP (plan section 4). The 5,000 $/MWh figure is a SCENARIO CAP, a stated
ASSUMPTION of this exercise sitting above the verified 4,522 $/MWh hourly maximum; it is not a NYISO number.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

_PJM_SHOCK_KEYS: tuple[str, ...] = (
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

# (agent key, engine key). NYISO: ref_onpeak_pct == wh_onpeak_pct, pocket_minus_ref_usd == dom_minus_wh_usd,
# large_load_shock_mw == dc_load_shock_mw; ny_gas_basis_usd is an optional engine key (config.OPTIONAL_SHOCK_KEYS).
_NYISO_KEY_MAP: tuple[tuple[str, str], ...] = (
    ("gas_hh_pct", "gas_hh_pct"),
    ("ny_gas_basis_usd", "ny_gas_basis_usd"),
    ("load_peak_ratio", "load_peak_ratio"),
    ("large_load_shock_mw", "dc_load_shock_mw"),
    ("ref_onpeak_pct", "wh_onpeak_pct"),
    ("pocket_minus_ref_usd", "dom_minus_wh_usd"),
    ("dart_pct", "dart_pct"),
    ("spike_days", "spike_days"),
    ("spike_daily_avg_usd", "spike_daily_avg_usd"),
    ("duration_days", "duration_days"),
)


@dataclass(frozen=True)
class Market:
    """Constants of one power market. Prices $/MWh, load MW, gas $/MMBtu, dates ISO strings (month precision allowed)."""

    name: str
    reference_zone: str  # label of the reference zone (internal columns wh_*)
    pocket_zone: str  # label of the load pocket (internal columns dom_*)
    reference_label: str  # prose label used in prompts and narratives
    pocket_label: str
    energy_cap_usd: float  # cap applied to scenario prices ($/MWh)
    cap_is_assumption: bool  # True: the cap is a stated assumption, not a market rule
    cap_note: str
    cap_failure_label: str  # plausibility hard-rule failure string
    cap_rule_name: str  # agent hard-rule name
    onpeak_hours: int  # hours per on-peak weekday
    onpeak_definition: str
    nerc_holidays: bool  # on-peak excludes NERC holidays
    structural_breaks: tuple[tuple[str, "str | tuple[str, str] | None"], ...]
    primary_break_key: str  # the break used when include_pre_break=False
    analogue_key: str  # eval.analogues table name
    weather_stations: tuple[tuple[str, str], ...]  # (label, GHCN id)
    typical_peak_mw: tuple[tuple[str, float], ...]  # seasonal-normal peak load by season
    large_load_ranges_mw: tuple[tuple[str, float], ...]  # scenario shock ranges for the large-load driver
    large_load_driver_class: str
    gas_basis_usd: tuple[tuple[str, float], ...]  # stated seasonal basis added to Henry Hub, $/MMBtu (ASSUMPTIONS)
    driver_classes: tuple[str, ...]
    default_driver_class: str  # fallback label for baseline scenarios with no distinguishing shock
    seed_families: tuple[tuple[str, str], ...]  # (driver class, season) of the four seeds (build assumption)
    shock_key_map: tuple[tuple[str, str], ...]
    loader_module: str
    synthetic_label: str  # market name used in SYNTHETIC warnings

    @property
    def agent_shock_keys(self) -> tuple[str, ...]:
        return tuple(a for a, _ in self.shock_key_map)

    @property
    def engine_shock_keys(self) -> tuple[str, ...]:
        return tuple(e for _, e in self.shock_key_map)

    @property
    def agent_to_engine(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.shock_key_map))

    @property
    def engine_to_agent(self) -> Mapping[str, str]:
        return MappingProxyType({e: a for a, e in self.shock_key_map})

    @property
    def structural_break_dates(self) -> dict[str, "str | tuple[str, str] | None"]:
        return dict(self.structural_breaks)

    @property
    def primary_break_cutoff(self) -> str:
        """ISO date before which data is dropped when pre-break data is excluded."""
        v = self.structural_break_dates[self.primary_break_key]
        if not isinstance(v, str):
            raise ValueError(f"{self.name}: primary break {self.primary_break_key} has no verified date")
        return v

    @property
    def typical_peak_by_season(self) -> dict[str, float]:
        return dict(self.typical_peak_mw)

    @property
    def gas_basis_by_season(self) -> dict[str, float]:
        return dict(self.gas_basis_usd)

    @property
    def large_load_ranges(self) -> dict[str, float]:
        return dict(self.large_load_ranges_mw)

    @property
    def weather_station_ids(self) -> dict[str, str]:
        return dict(self.weather_stations)


PJM = Market(
    name="PJM",
    reference_zone="Western Hub",
    pocket_zone="Dominion",
    reference_label="Western Hub",
    pocket_label="Dominion",
    energy_cap_usd=3700.0,
    cap_is_assumption=False,
    cap_note="Maximum shortage ENERGY component of LMP (2000 offer cap + 2 x 850); not a cap on total LMP.",
    cap_failure_label="energy_component_above_3700",
    cap_rule_name="energy_component_cap",
    onpeak_hours=16,
    onpeak_definition="weekdays HE8-23, NERC holidays off-peak",
    nerc_holidays=True,
    structural_breaks=(
        ("reserve_market_redesign", "2022-10-01"),
        ("gas_level_shift", ("2021-01-01", "2022-12-31")),
        ("data_center_era_start", "2023-01-01"),
        ("offer_cap_structure_start", None),
    ),
    primary_break_key="reserve_market_redesign",
    analogue_key="pjm",
    weather_stations=(
        ("PHL", "USW00013739"),
        ("PIT", "USW00094823"),
        ("DCA", "USW00013743"),
        ("ORD", "USW00094846"),
        ("CMH", "USW00014821"),
        ("CLE", "USW00014820"),
    ),
    typical_peak_mw=(("winter", 140_000.0), ("summer", 150_000.0)),  # approximate scale only
    large_load_ranges_mw=(),
    large_load_driver_class="demand_shock_datacenter",
    gas_basis_usd=(("winter", 1.50), ("summer", 0.30), ("shoulder", 0.90)),
    driver_classes=(
        "cold_snap",
        "heat_wave",
        "gas_supply",
        "transmission",
        "demand_shock_datacenter",
        "generator_outage",
        "policy",
    ),
    default_driver_class="policy",
    seed_families=(
        ("cold_snap", "winter"),
        ("heat_wave", "summer"),
        ("gas_supply", "winter"),
        ("demand_shock_datacenter", "shoulder"),
    ),
    shock_key_map=tuple((k, k) for k in _PJM_SHOCK_KEYS),
    loader_module="revstress.data.loaders",
    synthetic_label="PJM",
)

NYISO = Market(
    name="NYISO",
    reference_zone="WEST",
    pocket_zone="N.Y.C.",
    reference_label="WEST",
    pocket_label="N.Y.C.",
    energy_cap_usd=5000.0,
    cap_is_assumption=True,
    cap_note=(
        "STATED ASSUMPTION, not a NYISO number: NYISO shows no visible hard cap on LBMP. The scenario cap sits above "
        "the verified 4,522 $/MWh hourly maximum (Long Island, 24 Jun 2025); prices exceed the 2,000 $/MWh offer cap "
        "because shortage adders stack (plan sections 4 and 12)."
    ),
    cap_failure_label="scenario_cap_above_5000",
    cap_rule_name="scenario_price_cap",
    onpeak_hours=16,
    onpeak_definition="weekdays hour-beginning 7-22 (HE8-23), NERC holidays off-peak",
    nerc_holidays=True,
    structural_breaks=(
        ("scarcity_pricing", "2016-06-22"),
        ("indian_point_2_retirement", "2020-04"),
        ("indian_point_3_retirement", "2021-04"),
        ("transmission_shortage_pricing", "2023-11-14"),
        ("reserve_curve_revision_2021", None),
        ("chpe_in_service", None),
    ),
    primary_break_key="scarcity_pricing",
    analogue_key="nyiso",
    weather_stations=(
        ("NYC_CentralPark", "USW00094728"),
        ("LGA", "USW00014732"),
        ("JFK", "USW00094789"),
        ("ALB", "USW00014735"),
        ("BUF", "USW00014733"),
        ("SYR", "USW00014771"),
    ),
    typical_peak_mw=(("summer", 31_600.0), ("winter", 24_600.0)),
    large_load_ranges_mw=(
        ("shortfall_near_low_mw", -1500.0),
        ("shortfall_near_high_mw", -500.0),
        ("shortfall_2030_mw", -900.0),
        ("shortfall_2035_mw", -1400.0),
        ("overshoot_2030_mw", 800.0),
        ("overshoot_2035_mw", 1400.0),
        ("tail_low_mw", 3000.0),
        ("tail_high_mw", 4000.0),
    ),
    large_load_driver_class="large_load_shortfall",
    gas_basis_usd=(("winter", 2.00), ("summer", 0.50), ("shoulder", 1.00)),
    driver_classes=(
        "cold_snap",
        "heat_wave",
        "gas_supply",
        "transmission",
        "large_load_shortfall",
        "generator_outage",
        "reserve_shortage",
    ),
    default_driver_class="reserve_shortage",
    seed_families=(
        ("cold_snap", "winter"),
        ("heat_wave", "summer"),
        ("gas_supply", "winter"),
        ("large_load_shortfall", "summer"),
    ),
    shock_key_map=_NYISO_KEY_MAP,
    loader_module="revstress.data.nyiso",
    synthetic_label="NYISO",
)

MARKETS: Mapping[str, Market] = MappingProxyType({"PJM": PJM, "NYISO": NYISO})
DEFAULT_MARKET_NAME = "PJM"


def get_market(name: "str | Market | None" = None) -> Market:
    """Market by case-insensitive name; a Market passes through; None gives the default (PJM)."""
    if isinstance(name, Market):
        return name
    key = DEFAULT_MARKET_NAME if name is None else str(name).strip().upper()
    if key not in MARKETS:
        raise ValueError(f"unknown market {name!r}; choose from {sorted(MARKETS)}")
    return MARKETS[key]
