"""Verified analogue tables (plan section 8A and 6) as data, one per market, with claim scoring (plan section 8C).

Only numbers printed in the project plan appear here. A value of None means the number was looked for
and not found; it must not be cited. `approx` marks figures the plan states as "about" or "over".
ANALOGUES / EVENT_DISPLAY / EVENT_ALIASES are the PJM tables (default market); NYISO_* are the NYISO tables
(plan sections 6 and 8A). Functions take market=None, meaning the active market (config.MARKET).
"""

from __future__ import annotations

from dataclasses import dataclass

from revstress import config
from revstress.market import Market, get_market

CORRECT_TOL = 0.01  # relative error treated as an exact match (rounding)
WITHIN_TOL = 0.30  # plan section 5/8C tolerance


@dataclass(frozen=True)
class Analogue:
    """One row of the analogue table."""

    event: str
    metric: str
    value: float | None
    unit: str
    source: str
    vintage: str
    approx: bool = False
    note: str = ""


_PJM_ELLIOTT = "PJM Winter Storm Elliott report / Elliott deck"
_IMM_ELLIOTT = "IMM figure cited in PJM's Elliott report"
_JAN14 = "PJM / IMM January 2014 reports"
_JAN25 = "PJM January 2025 cold weather update"
_JUN25 = "PJM June 2025 heat update"
_LF26 = "PJM 2026 Load Forecast tables (XLSX) and accuracy report"

ANALOGUES: tuple[Analogue, ...] = (
    # Winter Storm Elliott, 23-24 Dec 2022
    Analogue("elliott", "forecast_peak_mw", 126968, "MW", _PJM_ELLIOTT, "verified, plan 2026-10-27"),
    Analogue("elliott", "actual_peak_mw_metered", 134700, "MW", _PJM_ELLIOTT, "verified, plan 2026-10-27", True, "metered incl. demand-response deployment"),
    Analogue("elliott", "peak_mw_dr_addback", 136010, "MW", _PJM_ELLIOTT, "verified, plan 2026-10-27", False, "demand response added back"),
    Analogue("elliott", "forced_outage_peak_mw", 46000, "MW", _PJM_ELLIOTT, "verified, plan 2026-10-27", True, "over 46,000 MW at 07:00 on 24 Dec"),
    Analogue("elliott", "forced_outage_pjm_figure_mw", 45952, "MW", _PJM_ELLIOTT, "verified, plan 2026-10-27", False, "PJM labels this 23.2% of fleet; 45,952/186 GW is about 24.7%"),
    Analogue("elliott", "forced_outage_share_pjm_pct", 23.2, "percent", _PJM_ELLIOTT, "verified, plan 2026-10-27", False, "PJM's figure; inconsistent with a 186 GW fleet"),
    Analogue("elliott", "unavailable_mw_24dec_morning", 57000, "MW", _PJM_ELLIOTT, "verified, plan 2026-10-27", True, "about 57 GW"),
    Analogue("elliott", "energy_component_usd_mwh", 3700, "$/MWh", "PJM Manual 11 rev 136", "verified, plan 2026-10-27", False, "in multiple intervals"),
    Analogue("elliott", "shortage_intervals_23dec", 71, "count", _PJM_ELLIOTT, "verified, plan 2026-10-27"),
    Analogue("elliott", "shortage_intervals_24dec", 134, "count", _PJM_ELLIOTT, "verified, plan 2026-10-27"),
    Analogue("elliott", "dec2022_lw_lmp_usd_mwh", 142.30, "$/MWh", _PJM_ELLIOTT + " (Jan 2023 report)", "Jan 2023", False, "restated 142.20 in Jan 2025"),
    Analogue("elliott", "dec2022_lw_lmp_restated_usd_mwh", 142.20, "$/MWh", _PJM_ELLIOTT, "Jan 2025 restatement"),
    Analogue("elliott", "dec2022_lw_lmp_imm_usd_mwh", 93.39, "$/MWh", _IMM_ELLIOTT, "verified, plan 2026-10-27", False, "reason for gap vs 142.30 unresolved"),
    Analogue("elliott", "dec2021_lw_lmp_usd_mwh", 38.90, "$/MWh", _PJM_ELLIOTT, "verified, plan 2026-10-27"),
    # January 2014
    Analogue("jan2014", "peak_mw", 141312, "MW", _JAN14, "verified, plan 2026-10-27", False, "7 Jan"),
    Analogue("jan2014", "imm_hourly_peak_mw", 140467, "MW", _JAN14, "verified, plan 2026-10-27"),
    Analogue("jan2014", "forced_outage_pct", 22, "percent", _JAN14, "verified, plan 2026-10-27", True, "as high as"),
    Analogue("jan2014", "forced_outage_mw", 40000, "MW", _JAN14, "verified, plan 2026-10-27", True, "about 40,000 MW"),
    Analogue("jan2014", "system_rt_lmp_he09_usd_mwh", 1840.54, "$/MWh", _JAN14, "verified, plan 2026-10-27", False, "HE09 on 7 Jan, system price"),
    Analogue("jan2014", "western_hub_price_usd_mwh", None, "$/MWh", "not found", "plan 2026-10-27", False, "Western Hub Jan 2014 price: not found, do not cite"),
    # January 2025
    Analogue("jan2025", "instantaneous_peak_mw", 145060, "MW", _JAN25, "preliminary, as of 27 Jan 2025", False, "22 Jan, 08:13"),
    Analogue("jan2025", "hourly_peak_mw", 143714, "MW", _JAN25, "preliminary, as of 27 Jan 2025"),
    Analogue("jan2025", "forced_outage_rate_pct", 9.24, "percent", _JAN25, "preliminary, as of 27 Jan 2025"),
    Analogue("jan2025", "forced_outage_mw", 16857, "MW", _JAN25, "preliminary, as of 27 Jan 2025"),
    Analogue("jan2025", "eastern_gas_usd_mmbtu", 35, "$/MMBtu", _JAN25, "4-day weekend average", True, "eastern gas hubs"),
    Analogue("jan2025", "western_pjm_gas_usd_mmbtu", 10, "$/MMBtu", _JAN25, "4-day weekend average", True, "western PJM hubs"),
    Analogue("jan2025", "transco_z6_ny_trade_floor_usd_mmbtu", 100, "$/MMBtu", _JAN25, "individual trades above this", True, "lower bound only"),
    # June 2025
    Analogue("jun2025", "peak_mw_23jun", 161770, "MW", _JUN25, "preliminary hourly"),
    Analogue("jun2025", "peak_mw_24jun", 162401, "MW", _JUN25, "preliminary hourly"),
    Analogue("jun2025", "record_peak_mw_2006", 165563, "MW", _JUN25, "verified, plan 2026-10-27", False, "not broken in June 2025"),
    Analogue("jun2025", "preemergency_dr_mw_24jun", 3800, "MW", _JUN25, "preliminary", True, "about 3,800 MW"),
    # Data-center series (plan section 6)
    Analogue("datacenter", "dom_large_load_july_peak_2026_mw", 7066, "MW", _LF26 + " Table B-9b", "2026 Load Forecast"),
    Analogue("datacenter", "dom_large_load_july_peak_2027_mw", 8925, "MW", _LF26 + " Table B-9b", "2026 Load Forecast"),
    Analogue("datacenter", "dom_large_load_july_peak_2028_mw", 10615, "MW", _LF26 + " Table B-9b", "2026 Load Forecast"),
    Analogue("datacenter", "rto_large_load_july_peak_2026_mw", 11479, "MW", _LF26, "2026 Load Forecast", True, "RTO about"),
    Analogue("datacenter", "rto_large_load_july_peak_2027_mw", 15866, "MW", _LF26, "2026 Load Forecast", True),
    Analogue("datacenter", "rto_large_load_july_peak_2028_mw", 21290, "MW", _LF26, "2026 Load Forecast", True),
    Analogue("datacenter", "rto_observed_july_peak_2025_mw", 8167, "MW", _LF26, "EDC-reported, 4 zones"),
    Analogue("datacenter", "dom_observed_july_peak_2025_mw", 5563, "MW", _LF26, "EDC-reported, 4 zones"),
    Analogue("datacenter", "dominion_energy_observed_july_peak_2025_mw", 3944, "MW", _LF26, "EDC-reported, 4 zones"),
    Analogue("datacenter", "ramp_cut_low_pct", 9, "percent", _LF26, "2026 vs 2025 forecast revision", True),
    Analogue("datacenter", "ramp_cut_high_pct", 10, "percent", _LF26, "2026 vs 2025 forecast revision", True),
    Analogue("datacenter", "dom_shortfall_vs_2026_pct", 27, "percent", _LF26, "DOM held at 2025 observed 5,563 vs 7,066", True),
    Analogue("datacenter", "zone_cut_extreme_pct", 54, "percent", _LF26, "PL 2028 revision", True),
    Analogue("datacenter", "observed_above_forecast_low_pct", 3, "percent", _LF26, "RTO, 2023-25 forecast vintages"),
    Analogue("datacenter", "observed_above_forecast_high_pct", 24, "percent", _LF26, "RTO, 2023-25 forecast vintages"),
    Analogue("datacenter", "pjm_default_utilization_pct", 70, "percent", _LF26, "36-month minimum ramp"),
    Analogue("datacenter", "dom_accepted_2028_mw", 10600, "MW", _LF26, "2026 Load Forecast", True, "10.6 GW accepted for DOM"),
    Analogue("datacenter", "dominion_requested_tiers_mw", 53800, "MW", _LF26, "2026 Load Forecast", False, "upper bound only, not a base case"),
    Analogue("datacenter", "weather_gap_sd_summer_pct", 2.5, "percent", _LF26 + " Table F1", "2026 Load Forecast"),
    Analogue("datacenter", "weather_gap_sd_winter_pct", 6.1, "percent", _LF26 + " Table F1", "2026 Load Forecast"),
)

_NY_VER = "verified, plan 2026-10-27"
_NY_PRICE = "NYISO MIS damlbmp/rtlbmp hourly integrated LBMP, daily on-peak means (plan sec 8A)"
_NY_LOAD = "NYISO palIntegrated, sum of 11 zones, vs official peak (plan sec 8A)"
_NY_GAS = "EIA Weekly Update (NGI Transco Z6 NY daily spot)"
_NY_SOM22 = "Potomac Economics 2022 State of the Market, pp. 34-40"
_NY_SOM14 = "Potomac Economics 2014 State of the Market, Table 1"
_NY_GB = "NYISO Gold Book 2026, Table I-14 (summer large load)"
_NY_GB_REV = "NYISO Gold Book 2024, 2025, 2026 editions"
_NY_GB_SCN = "NYISO Gold Book 2026, lower/higher scenarios"
_NY_QUEUE = "NYISO Gold Book 2026, Table IV-7 (queue, 15 Mar 2026)"
_NY_PT = "NYISO Power Trends 2025, 2026 / Gold Book 2026"
_NY_FC = "NYISO isolf day-ahead load forecast vs actual (plan sec 6)"
_NY_NF = "not found"
_NY_NF_V = "plan 2026-10-27"

NYISO_ANALOGUES: tuple[Analogue, ...] = (
    # Polar vortex, 7 Jan 2014 (pre-2016 pricing regime)
    Analogue("jan2014", "west_da_onpeak_usd_mwh", 137.3, "$/MWh", _NY_PRICE, _NY_VER, False, "7 Jan 2014"),
    Analogue("jan2014", "west_rt_onpeak_usd_mwh", 354.4, "$/MWh", _NY_PRICE, _NY_VER, False, "7 Jan 2014"),
    Analogue("jan2014", "nyc_da_onpeak_usd_mwh", 224.8, "$/MWh", _NY_PRICE, _NY_VER, False, "7 Jan 2014"),
    Analogue("jan2014", "nyc_rt_onpeak_usd_mwh", 509.5, "$/MWh", _NY_PRICE, _NY_VER, False, "7 Jan 2014"),
    Analogue("jan2014", "west_dart_gap_onpeak_usd_mwh", -217, "$/MWh", _NY_PRICE, _NY_VER, False, "DA minus RT, 7 Jan 2014"),
    Analogue("jan2014", "nyc_dart_gap_onpeak_usd_mwh", -285, "$/MWh", _NY_PRICE, _NY_VER, False, "DA minus RT, 7 Jan 2014"),
    Analogue("jan2014", "nyca_peak_mw", 25737.8, "MW", _NY_LOAD, _NY_VER, False, "official 25,738 MW, winter record"),
    Analogue("jan2014", "z6_ny_gas_usd_mmbtu_6jan", 56.59, "$/MMBtu", _NY_GAS, _NY_VER, False, "6 Jan 2014"),
    Analogue("jan2014", "henry_hub_usd_mmbtu_6jan", 4.50, "$/MMBtu", _NY_GAS, _NY_VER, False, "6 Jan 2014"),
    Analogue("jan2014", "q1_2014_west_lbmp_usd_mwh", 95.71, "$/MWh", _NY_SOM14, _NY_VER, False, "Q1 2014 average; definition to be matched (plan sec 8A)"),
    Analogue("jan2014", "q1_2014_nyc_lbmp_usd_mwh", 133.70, "$/MWh", _NY_SOM14, _NY_VER, False, "Q1 2014 average; definition to be matched (plan sec 8A)"),
    Analogue("jan2014", "event_day_max_lbmp_usd_mwh", None, "$/MWh", _NY_NF, _NY_NF_V, False, "event-day maximum LBMP: not found, do not cite"),
    Analogue("jan2014", "shortage_intervals", None, "count", _NY_NF, _NY_NF_V, False, "shortage-interval count: not found, do not cite"),
    # Winter Storm Elliott, 23-24 Dec 2022
    Analogue("elliott", "west_da_onpeak_usd_mwh_23dec", 82.8, "$/MWh", _NY_PRICE, _NY_VER, False, "23 Dec 2022"),
    Analogue("elliott", "west_rt_onpeak_usd_mwh_23dec", 229.6, "$/MWh", _NY_PRICE, _NY_VER, False, "23 Dec 2022"),
    Analogue("elliott", "nyc_da_onpeak_usd_mwh_23dec", 141.6, "$/MWh", _NY_PRICE, _NY_VER, False, "23 Dec 2022"),
    Analogue("elliott", "nyc_rt_onpeak_usd_mwh_23dec", 568.1, "$/MWh", _NY_PRICE, _NY_VER, False, "23 Dec 2022"),
    Analogue("elliott", "west_dart_gap_onpeak_usd_mwh", -147, "$/MWh", _NY_PRICE, _NY_VER, False, "DA minus RT, 23 Dec 2022"),
    Analogue("elliott", "nyc_dart_gap_onpeak_usd_mwh", -427, "$/MWh", _NY_PRICE, _NY_VER, False, "DA minus RT, 23 Dec 2022"),
    Analogue("elliott", "nyc_minus_west_rt_spread_usd_mwh", 338.5, "$/MWh", _NY_PRICE, _NY_VER, False, "real-time spread, 23 Dec 2022 (plan sec 3)"),
    Analogue("elliott", "nyca_peak_mw_24dec", 22003.9, "MW", _NY_LOAD, _NY_VER, False, "official 22,004 MW (24 Dec, HB17); not a load record"),
    Analogue("elliott", "nyca_winter_peak_2022_23_mw", 23369, "MW", _NY_LOAD, _NY_VER, False, "winter 2022-23 peak, higher than the Elliott day"),
    Analogue("elliott", "rt_hourly_max_long_island_usd_mwh", 3132, "$/MWh", _NY_PRICE, _NY_VER, False, "Long Island, hourly"),
    Analogue("elliott", "som_price_over_usd_mwh", 4000, "$/MWh", _NY_SOM22, _NY_VER, True, "SOM: prices 'over $4,000'; lower bound only"),
    Analogue("elliott", "pjm_sar_request_first_mw", 3000, "MW", _NY_SOM22, _NY_VER, False, "PJM request, first"),
    Analogue("elliott", "pjm_sar_request_second_mw", 2000, "MW", _NY_SOM22, _NY_VER, False, "PJM request, revised"),
    Analogue("elliott", "nyiso_sar_low_mw", 320, "MW", _NY_SOM22, _NY_VER, True, "NYISO about 320-485 MW"),
    Analogue("elliott", "nyiso_sar_high_mw", 485, "MW", _NY_SOM22, _NY_VER, True, "NYISO about 320-485 MW"),
    Analogue("elliott", "import_curtailment_1_mw", 1500, "MW", _NY_SOM22, _NY_VER, False, "plan lists 1.5/1.8/0.7 GW; hour assignment not recorded"),
    Analogue("elliott", "import_curtailment_2_mw", 1800, "MW", _NY_SOM22, _NY_VER, False, "plan lists 1.5/1.8/0.7 GW; hour assignment not recorded"),
    Analogue("elliott", "import_curtailment_3_mw", 700, "MW", _NY_SOM22, _NY_VER, False, "plan lists 1.5/1.8/0.7 GW; hour assignment not recorded"),
    Analogue("elliott", "forced_outages_mw", 1800, "MW", _NY_SOM22, _NY_VER, True, "about 1.8 GW"),
    Analogue("elliott", "z6_ny_gas_usd_mmbtu", None, "$/MMBtu", "not verified", _NY_NF_V, False, "Elliott daily gas 23-27 Dec 2022: not verified, do not cite"),
    Analogue("elliott", "event_day_max_lbmp_usd_mwh", None, "$/MWh", _NY_NF, _NY_NF_V, False, "event-day maximum LBMP: not found, do not cite"),
    Analogue("elliott", "shortage_intervals", None, "count", _NY_NF, _NY_NF_V, False, "shortage-interval count: not found, do not cite"),
    # Cold, 20-23 Jan 2025 (20 Jan is a holiday)
    Analogue("jan2025", "west_da_onpeak_low_usd_mwh", 193.5, "$/MWh", _NY_PRICE, _NY_VER, False, "lowest daily mean, 20-23 Jan 2025"),
    Analogue("jan2025", "west_da_onpeak_high_usd_mwh", 227.9, "$/MWh", _NY_PRICE, _NY_VER, False, "highest daily mean, 20-23 Jan 2025"),
    Analogue("jan2025", "west_rt_onpeak_low_usd_mwh", 115.7, "$/MWh", _NY_PRICE, _NY_VER, False, "lowest daily mean, 20-23 Jan 2025; DA above RT"),
    Analogue("jan2025", "west_rt_onpeak_high_usd_mwh", 200.1, "$/MWh", _NY_PRICE, _NY_VER, False, "highest daily mean, 20-23 Jan 2025"),
    Analogue("jan2025", "nyc_da_onpeak_low_usd_mwh", 301, "$/MWh", _NY_PRICE, _NY_VER, False, "lowest daily mean, 20-23 Jan 2025"),
    Analogue("jan2025", "nyc_da_onpeak_high_usd_mwh", 328, "$/MWh", _NY_PRICE, _NY_VER, False, "highest daily mean, 20-23 Jan 2025"),
    Analogue("jan2025", "nyca_peak_mw_22jan", 23521.3, "MW", _NY_LOAD, _NY_VER, False, "official 23,521 MW"),
    Analogue("jan2025", "z6_ny_gas_usd_mmbtu_17jan", 97.90, "$/MMBtu", _NY_GAS, _NY_VER, False, "17 Jan 2025, before the cold days"),
    Analogue("jan2025", "henry_hub_usd_mmbtu_17jan", 10, "$/MMBtu", _NY_GAS, _NY_VER, True, "about 10 on 17 Jan 2025"),
    Analogue("jan2025", "z6_ny_gas_usd_mmbtu_22jan", 17.54, "$/MMBtu", _NY_GAS, _NY_VER, False, "22 Jan 2025"),
    Analogue("jan2025", "event_day_max_lbmp_usd_mwh", None, "$/MWh", _NY_NF, _NY_NF_V, False, "event-day maximum LBMP: not found, do not cite"),
    Analogue("jan2025", "shortage_intervals", None, "count", _NY_NF, _NY_NF_V, False, "shortage-interval count: not found, do not cite"),
    # Heat, 23-25 Jun 2025
    Analogue("jun2025", "west_da_onpeak_usd_mwh_23jun", 131.6, "$/MWh", _NY_PRICE, _NY_VER, False, "23 Jun 2025"),
    Analogue("jun2025", "west_da_onpeak_usd_mwh_24jun", 144.5, "$/MWh", _NY_PRICE, _NY_VER, False, "24 Jun 2025"),
    Analogue("jun2025", "west_da_onpeak_usd_mwh_25jun", 112.0, "$/MWh", _NY_PRICE, _NY_VER, False, "25 Jun 2025"),
    Analogue("jun2025", "west_rt_onpeak_usd_mwh_23jun", 270.5, "$/MWh", _NY_PRICE, _NY_VER, False, "23 Jun 2025"),
    Analogue("jun2025", "west_rt_onpeak_usd_mwh_24jun", 416.5, "$/MWh", _NY_PRICE, _NY_VER, False, "24 Jun 2025; largest daily WEST on-peak RT mean seen"),
    Analogue("jun2025", "west_rt_onpeak_usd_mwh_25jun", 188.8, "$/MWh", _NY_PRICE, _NY_VER, False, "25 Jun 2025"),
    Analogue("jun2025", "nyc_da_onpeak_usd_mwh_24jun", 181.8, "$/MWh", _NY_PRICE, _NY_VER, False, "24 Jun 2025"),
    Analogue("jun2025", "nyc_rt_onpeak_usd_mwh_24jun", 625.5, "$/MWh", _NY_PRICE, _NY_VER, False, "24 Jun 2025; largest daily N.Y.C. on-peak RT mean seen"),
    Analogue("jun2025", "west_dart_gap_onpeak_usd_mwh_24jun", -272, "$/MWh", _NY_PRICE, _NY_VER, False, "DA minus RT"),
    Analogue("jun2025", "nyc_dart_gap_onpeak_usd_mwh_24jun", -444, "$/MWh", _NY_PRICE, _NY_VER, False, "DA minus RT"),
    Analogue("jun2025", "nyca_peak_mw_24jun", 31857.2, "MW", _NY_LOAD, _NY_VER, False, "official 31,857 MW; Major Emergency 18:13-19:58"),
    Analogue("jun2025", "rt_hourly_max_long_island_usd_mwh", 4522, "$/MWh", _NY_PRICE, _NY_VER, False, "hourly maximum, 24 Jun 2025"),
    Analogue("jun2025", "evening_avg_17_20_low_usd_mwh", 1300, "$/MWh", _NY_PRICE, _NY_VER, True, "17:00-20:00 average by region, low end, 24 Jun 2025"),
    Analogue("jun2025", "evening_avg_17_20_high_usd_mwh", 3500, "$/MWh", _NY_PRICE, _NY_VER, True, "17:00-20:00 average by region, high end, 24 Jun 2025"),
    Analogue("jun2025", "z6_ny_gas_usd_mmbtu_24jun", 3.10, "$/MMBtu", _NY_GAS, _NY_VER, False, "24 Jun 2025, calm gas: a pure load/reserve event"),
    Analogue("jun2025", "da_load_forecast_miss_pct_25jun", -9.5, "percent", _NY_FC, _NY_VER, True, "forecast minus actual at peak, up to -9.5%, 25 Jun 2025"),
    Analogue("jun2025", "event_day_max_lbmp_usd_mwh", None, "$/MWh", _NY_NF, _NY_NF_V, False, "event-day maximum LBMP (all zones): not found, do not cite"),
    Analogue("jun2025", "shortage_intervals", None, "count", _NY_NF, _NY_NF_V, False, "shortage-interval count: not found, do not cite"),
    # Large-load series (plan section 6)
    Analogue("datacenter", "large_load_summer_2026_mw", 538, "MW", _NY_GB, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_summer_2030_mw", 1831, "MW", _NY_GB, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_summer_2035_mw", 2643, "MW", _NY_GB, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_summer_2040_mw", 2880, "MW", _NY_GB, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_share_of_peak_2026_pct", 1.7, "percent", _NY_GB, "Gold Book 2026 edition", True, "of the 2026 baseline peak"),
    Analogue("datacenter", "large_load_share_of_peak_2030_pct", 5.7, "percent", _NY_GB, "Gold Book 2026 edition", True),
    Analogue("datacenter", "large_load_share_of_peak_2035_pct", 8.0, "percent", _NY_GB, "Gold Book 2026 edition", True),
    Analogue("datacenter", "large_load_2026_value_in_2024_edition_mw", 1091, "MW", _NY_GB_REV, "Gold Book 2024 edition"),
    Analogue("datacenter", "large_load_2026_value_in_2025_edition_mw", 1023, "MW", _NY_GB_REV, "Gold Book 2025 edition"),
    Analogue("datacenter", "large_load_2026_revision_cut_mw", 485, "MW", _NY_GB_REV, "2025 to 2026 edition", False, "2026 value cut from 1,023 to 538"),
    Analogue("datacenter", "large_load_2026_revision_cut_pct", 47, "percent", _NY_GB_REV, "2025 to 2026 edition", True),
    Analogue("datacenter", "large_load_2030_value_in_2024_edition_mw", 1894, "MW", _NY_GB_REV, "Gold Book 2024 edition"),
    Analogue("datacenter", "large_load_2030_value_in_2025_edition_mw", 2005, "MW", _NY_GB_REV, "Gold Book 2025 edition"),
    Analogue("datacenter", "large_load_lower_2026_mw", 337, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_lower_2030_mw", 914, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_lower_2035_mw", 1221, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_higher_2026_mw", 578, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_higher_2030_mw", 2617, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_higher_2035_mw", 4019, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_higher_2040_mw", 4336, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_range_2030_low_mw", -917, "MW", _NY_GB_SCN, "Gold Book 2026 edition", False, "lower scenario minus baseline"),
    Analogue("datacenter", "large_load_range_2030_high_mw", 786, "MW", _NY_GB_SCN, "Gold Book 2026 edition", False, "higher scenario minus baseline"),
    Analogue("datacenter", "large_load_range_2035_low_mw", -1422, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "large_load_range_2035_high_mw", 1376, "MW", _NY_GB_SCN, "Gold Book 2026 edition"),
    Analogue("datacenter", "queue_projects", 48, "count", _NY_QUEUE, "15 Mar 2026"),
    Analogue("datacenter", "queue_total_mw", 12330.1, "MW", _NY_QUEUE, "15 Mar 2026"),
    Analogue("datacenter", "queue_added_2025_mw", 3948.5, "MW", _NY_QUEUE, "15 Mar 2026"),
    Analogue("datacenter", "queue_added_2024_mw", 2722.2, "MW", _NY_QUEUE, "15 Mar 2026"),
    Analogue("datacenter", "queue_in_forecast_projects", 14, "count", _NY_QUEUE, "15 Mar 2026"),
    Analogue("datacenter", "queue_in_forecast_mw", 2557.1, "MW", _NY_QUEUE, "15 Mar 2026"),
    Analogue("datacenter", "queue_unforecast_mw", 9800, "MW", _NY_QUEUE, "15 Mar 2026", True, "about 9.8 GW"),
    Analogue("datacenter", "queue_data_center_type_mw", 5799, "MW", "plan keyword classification of Table IV-7 (not a NYISO category)", "15 Mar 2026", True),
    Analogue("datacenter", "summer_normal_peak_2026_mw", 31600, "MW", _NY_PT, "2026 editions", True, "about 31.6 GW"),
    Analogue("datacenter", "winter_normal_peak_2026_27_mw", 24600, "MW", _NY_PT, "2026 editions", True, "about 24.6 GW"),
    Analogue("datacenter", "weather_normalised_peak_2025_mw", 31405, "MW", _NY_PT, "2025 peak"),
    Analogue("datacenter", "forecast_peak_2025_mw", 31471, "MW", _NY_PT, "2025 forecast"),
    Analogue("datacenter", "shortfall_near_term_low_mw", -1500, "MW", _NY_PT, "by 2027-28", True, "scenario range, not a forecast"),
    Analogue("datacenter", "shortfall_near_term_high_mw", -500, "MW", _NY_PT, "by 2027-28", True, "scenario range, not a forecast"),
    Analogue("datacenter", "shortfall_2030_mw", -900, "MW", _NY_PT, "2030", True, "scenario range, not a forecast"),
    Analogue("datacenter", "shortfall_2035_mw", -1400, "MW", _NY_PT, "2035", True, "scenario range, not a forecast"),
    Analogue("datacenter", "overshoot_2030_mw", 800, "MW", _NY_PT, "2030", True, "scenario range, not a forecast"),
    Analogue("datacenter", "overshoot_2035_mw", 1400, "MW", _NY_PT, "2035", True, "scenario range, not a forecast"),
    Analogue("datacenter", "tail_low_mw", 3000, "MW", "plan section 6 labelled tail", "scenario", True, "not a NYISO forecast"),
    Analogue("datacenter", "tail_high_mw", 4000, "MW", "plan section 6 labelled tail", "scenario", True, "not a NYISO forecast"),
    Analogue("datacenter", "da_load_forecast_miss_low_pct", -3.0, "percent", _NY_FC, "previous-day vintage", True, "event days; a weather-type shock"),
    Analogue("datacenter", "da_load_forecast_miss_high_pct", -7.0, "percent", _NY_FC, "previous-day vintage", True, "event days; a weather-type shock"),
    Analogue("datacenter", "da_load_forecast_miss_typical_mw", -1500, "MW", _NY_FC, "previous-day vintage", True),
)

_INDEXES: dict[str, dict[tuple[str, str], Analogue]] = {
    "pjm": {(a.event, a.metric): a for a in ANALOGUES},
    "nyiso": {(a.event, a.metric): a for a in NYISO_ANALOGUES},
}
_INDEX = _INDEXES["pjm"]

PJM_EVENT_DISPLAY: dict[str, str] = {
    "elliott": "Winter Storm Elliott",
    "jan2014": "January 2014",
    "jan2025": "January 2025",
    "jun2025": "June 2025",
    "datacenter": "PJM 2026 load forecast data-center series",
}
EVENT_DISPLAY = PJM_EVENT_DISPLAY
NYISO_EVENT_DISPLAY: dict[str, str] = {
    "elliott": "Winter Storm Elliott (NYISO)",
    "jan2014": "Polar vortex January 2014 (NYISO)",
    "jan2025": "January 2025 cold (NYISO)",
    "jun2025": "June 2025 heat (NYISO)",
    "datacenter": "NYISO Gold Book large-load series",
}

PJM_EVENT_ALIASES: dict[str, str] = {
    "winter storm elliott": "elliott",
    "elliott": "elliott",
    "dec 2022": "elliott",
    "january 2014": "jan2014",
    "jan 2014": "jan2014",
    "polar vortex": "jan2014",
    "january 2025": "jan2025",
    "jan 2025": "jan2025",
    "june 2025": "jun2025",
    "jun 2025": "jun2025",
    "data center": "datacenter",
    "data-center": "datacenter",
    "datacenter": "datacenter",
    "data center load": "datacenter",
}
EVENT_ALIASES = PJM_EVENT_ALIASES
NYISO_EVENT_ALIASES: dict[str, str] = {
    **PJM_EVENT_ALIASES,
    "large load": "datacenter",
    "large-load": "datacenter",
    "largeload": "datacenter",
    "gold book": "datacenter",
}
_MARKET_TABLES: dict[str, tuple[tuple[Analogue, ...], dict[str, str], dict[str, str]]] = {
    "pjm": (ANALOGUES, PJM_EVENT_DISPLAY, PJM_EVENT_ALIASES),
    "nyiso": (NYISO_ANALOGUES, NYISO_EVENT_DISPLAY, NYISO_EVENT_ALIASES),
}


def _resolve(market: "str | Market | None") -> Market:
    return get_market(config.MARKET if market is None else market)


def _aliases(m: Market) -> tuple[dict[str, str], tuple[str, ...]]:
    al = _MARKET_TABLES[m.analogue_key][2]
    return al, tuple(sorted(al, key=len, reverse=True))


def normalise_event(event: str, market: "str | Market | None" = None) -> str:
    """Canonical event key (elliott, jan2014, jan2025, jun2025, datacenter) for the market (default: active market).

    Exact alias match first, then the longest alias contained in the name (so 'Winter Storm Elliott, Dec 2022'
    resolves); unknown names pass through lower-cased with separators removed.
    """
    aliases, longest_first = _aliases(_resolve(market))
    key = " ".join(event.strip().lower().split())
    if key in aliases:
        return aliases[key]
    for alias in longest_first:
        if alias in key:
            return aliases[alias]
    return key.replace(" ", "").replace("-", "").replace("_", "")


def analogue_table(market: "str | Market | None" = None) -> dict[str, dict[str, float]]:
    """Single source of truth shown to Claude and checked by agent.rules: {display event: {metric: value}}.

    Rows whose value is None (looked for, not found) are omitted, so citing them fails as not in the table.
    """
    rows, display, _ = _MARKET_TABLES[_resolve(market).analogue_key]
    out: dict[str, dict[str, float]] = {name: {} for name in display.values()}
    for a in rows:
        if a.value is not None:
            out[display[a.event]][a.metric] = float(a.value)
    return out


def analogue_rows(market: "str | Market | None" = None) -> tuple[Analogue, ...]:
    """All rows (including None-valued ones) of the market's table."""
    return _MARKET_TABLES[_resolve(market).analogue_key][0]


def lookup(event: str, metric: str, market: "str | Market | None" = None) -> Analogue | None:
    """Table row for (event, metric), or None if there is no such row."""
    m = _resolve(market)
    return _INDEXES[m.analogue_key].get((normalise_event(event, m), metric.strip().lower()))


def score_claim(event: str, metric: str, claimed: float | None, market: "str | Market | None" = None) -> str:
    """Score a claimed number against the table.

    Returns 'correct' (relative error <= 1%), 'within30' (<= 30%), 'wrong', or 'not_in_table' when the
    row is missing, its value is None, or the claim is missing/non-numeric.
    """
    row = lookup(event, metric, market)
    if row is None or row.value is None or claimed is None:
        return "not_in_table"
    try:
        c = float(claimed)
    except (TypeError, ValueError):
        return "not_in_table"
    if row.value == 0:
        return "correct" if c == 0 else "wrong"
    rel = abs(c - row.value) / abs(row.value)
    if rel <= CORRECT_TOL:
        return "correct"
    return "within30" if rel <= WITHIN_TOL else "wrong"


def score_analogue(analogue: dict, market: "str | Market | None" = None) -> dict[str, str]:
    """Score every claimed metric of an agent analogue block {event, dates, claimed: {metric: value}, source}."""
    event = analogue.get("event", "")
    return {m: score_claim(event, m, v, market) for m, v in (analogue.get("claimed") or {}).items()}
