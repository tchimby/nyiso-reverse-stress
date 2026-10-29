# Ranked reverse-stress scenarios (NYISO book)

Source logs: live_daily_sonnet. Models: claude-sonnet-5-5. Client kinds: live.  
Target loss 5.0M. Scenarios read: 176; ranked (eligible): 59; excluded: 117.  
q is a rank against about 250 non-overlapping 10-day windows of 2019-2025, not a probability; fit window 2019-2025; daily averaging understates hourly spikes. A client kind other than the live API means scripted output, not Claude results.  
Largest-loss channel across ranked scenarios: {"zone_volume": 59} (one channel for all of them means the book, not the search, limits diversity).

Coherence grading by a human: [PENDING]. Scenarios are drafts for a risk manager to accept or hedge, not forecasts.

## Ranked scenarios (most plausible first)

### #1 GS_W_SHORT_SEVERE_SQUEEZE_10D (gas_supply, winter, 10 days)

**Narrative.** A short, severe gas shortage hits the N.Y.C. pocket for 10 days, as in a pipeline freeze-off. Henry Hub doubles, up 100 percent, and the local basis adds $10/MMBtu to P4's gas cost, which cuts that heat-rate call's payoff relative to the unshocked path. Constrained gas in Zone J pushes the N.Y.C. minus WEST spread out by $250/MWh, inside the historical maximum of 400.6. P5 takes the loss because it is short N.Y.C. and hedged only at WEST. P2 recovers about 15 percent of it. WEST on-peak falls a further 15 percent on top of the gas-implied move because upstate supply is not constrained, which trims the gain on P1. Load stays normal, so the loss comes from the spread alone and is front-loaded into a short window. Estimate: P5 about -9.7M, P2 +1.6M, P1 and P4 net about +0.5M, total about -7.5M, stated conservatively. Confidence is low because I scaled the 5-day sensitivities.

**Shock vector (non-neutral).** `{"gas_hh_pct": 100, "ny_gas_basis_usd": 10, "ref_onpeak_pct": -15, "pocket_minus_ref_usd": 250, "duration_days": 10}`

**Loss** 8.19M (Claude stated 6.50M)  
**Plausibility.** D2 91.2, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 1.0, "l": 0.98, "s": 0.03, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.31M | P2 +1.71M | P3 -0.02M | P4 -0.06M | P5 -10.14M | P6 -0.00M  
**P&L by channel.** system +0.31M | congestion +1.71M | dart -0.02M | gas -0.06M | zone_volume -10.14M | tail -0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #2 CS_W_2_Elliott_style_RT_blowout (cold_snap, winter, 7 days)

**Narrative.** A Winter Storm Elliott-style flash freeze lasts 7 days, with forced outages and import curtailments concentrated downstate. The real-time N.Y.C. minus WEST spread blows out by $300/MWh on top of the base spread (pocket_minus_ref_usd 300), comparable to the analogue's 338.5 $/MWh. Real-time clears 120% above day-ahead (dart_pct 120), as in Elliott, which hurts the day-ahead-minus-real-time receiver P3. Load is only slightly above normal (load_peak_ratio 1.03), because Elliott had curtailments rather than record demand. Gas rises 20% (gas_hh_pct 20), with a $8 N.Y.C. gas basis (ny_gas_basis_usd 8) that cuts the P4 payoff. The N.Y.C. short in P5 loses roughly $4,650 per $/MWh-day, so about $9.8M over 7 days. P2 offsets about $1.6M. Gains on P1 and P4 from the dart and gas moves are about $0.7M. Net loss is about $7M. Estimate is by linear scaling of one-at-a-time sensitivities.

**Shock vector (non-neutral).** `{"gas_hh_pct": 20, "ny_gas_basis_usd": 8, "load_peak_ratio": 1.03, "pocket_minus_ref_usd": 300, "dart_pct": 120, "duration_days": 7}`

**Loss** 7.22M (Claude stated 7.00M)  
**Plausibility.** D2 110.6, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.99, "l": 1.0, "s": 0.33, "c": 1.0, "d": 0.91}  
**P&L by position.** P1 +0.92M | P2 +1.51M | P3 -0.47M | P4 +0.17M | P5 -9.28M | P6 -0.08M  
**P&L by channel.** system +0.92M | congestion +1.51M | dart -0.47M | gas +0.17M | zone_volume -9.28M | tail -0.08M  
**Analogue.** Winter Storm Elliott (NYISO) 23-24 December 2022; **confidence** medium; **soft penalty** 0.0

### #3 HW_S9_cheap_gas_deep_dart_soft_power (heat_wave, summer, 30 days)

**Narrative.** A 30-day summer heat wave with load 2% above a typical day (load_peak_ratio 1.02) but weak upstate prices. Henry Hub falls 30% (gas_hh_pct -30), which lowers power prices implied for WEST. Real-time clears 60% below day-ahead (dart_pct -60), within the historical minimum of -84.1. WEST on-peak prices are a further 40% soft (ref_onpeak_pct -40). Together these hit the long swap P1 and the heat-rate call P4 hard, and P3 gains slightly. The N.Y.C. minus WEST spread widens by only $32/MWh (pocket_minus_ref_usd 32), which still costs the retail obligation P5 about -$3.4M, with +$0.6M back on P2. Estimated: about -$2.5M on P1 and -$0.8M on P4.

**Shock vector (non-neutral).** `{"gas_hh_pct": -30, "load_peak_ratio": 1.02, "ref_onpeak_pct": -40, "pocket_minus_ref_usd": 32, "dart_pct": -60, "duration_days": 30}`

**Loss** 5.44M (Claude stated 5.50M)  
**Plausibility.** D2 133.5, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.26, "l": 0.78, "s": 0.34, "c": 1.0, "d": 0.77}  
**P&L by position.** P1 -2.22M | P2 +0.58M | P3 +0.33M | P4 -0.80M | P5 -3.37M | P6 +0.05M  
**P&L by channel.** system -2.22M | congestion +0.58M | dart +0.33M | gas -0.80M | zone_volume -3.37M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #4 HW_S7_low_load_weak_west_soft_RT_30d (heat_wave, summer, 30 days)

**Narrative.** A hot but well-forecast 30-day summer spell in which load stays at a typical level (load_peak_ratio 1.0, the minimum allowed for a heat wave). The only physical stress is a modest N.Y.C. import constraint that widens the N.Y.C. minus WEST spread by $40/MWh (pocket_minus_ref_usd 40, about 1.4 standard deviations). That is the smallest spread shock so far. P5 pays this widening on about 140 MW around the clock, and P2 recovers only part of it. WEST on-peak prices come in 35% below what the load and gas path implies (ref_onpeak_pct -35) because upstate supply is ample. Real-time clears 40% below day-ahead (dart_pct -40) because day-ahead over-scheduled the heat. Both shocks cut the value of the long WEST swap P1 and the heat-rate call P4, while P3 gains slightly. Rough estimate: P5 about -4.1M, P2 about +0.7M, P1 and P4 about -3.0M, P3 about +0.3M, net about -6.1M. I state a lower figure because the effects are not additive. Gas and spike shocks are zero because they would only help the long positions.

**Shock vector (non-neutral).** `{"ref_onpeak_pct": -35, "pocket_minus_ref_usd": 40, "dart_pct": -40, "duration_days": 30}`

**Loss** 5.46M (Claude stated 5.60M)  
**Plausibility.** D2 134.5, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.73, "s": 0.87, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -1.69M | P2 +0.72M | P3 +0.28M | P4 -0.72M | P5 -4.11M | P6 +0.05M  
**P&L by channel.** system -1.69M | congestion +0.72M | dart +0.28M | gas -0.72M | zone_volume -4.11M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #5 HW_S7_soft_west_dart_wide_spread (heat_wave, summer, 30 days)

**Narrative.** A 30-day summer heat wave with load only 2% above a typical day (load_peak_ratio 1.02). Downstate demand keeps the N.Y.C. minus WEST spread $40/MWh wider (pocket_minus_ref_usd 40), about 1.4 standard deviations of the summer spread factor, which hurts the short N.Y.C. retail obligation P5. Upstate surplus depresses WEST on-peak prices 40% below what load implies (ref_onpeak_pct -40). Real-time also clears 45% below day-ahead (dart_pct -45). Both weaken the long swap P1 and the heat-rate call P4, and the DART receipt P3 gains a little. Rough scaling from the sensitivities gives about -$4.2M on P5 and -$1.8M on P1, with offsets from P2, P3 and P4.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.02, "ref_onpeak_pct": -40, "pocket_minus_ref_usd": 40, "dart_pct": -45, "duration_days": 30}`

**Loss** 5.68M (Claude stated 5.60M)  
**Plausibility.** D2 134.9, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.78, "s": 0.77, "c": 1.0, "d": 0.94}  
**P&L by position.** P1 -1.81M | P2 +0.72M | P3 +0.32M | P4 -0.75M | P5 -4.21M | P6 +0.05M  
**P&L by channel.** system -1.81M | congestion +0.72M | dart +0.32M | gas -0.75M | zone_volume -4.21M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #6 HW_S5_dart_overforecast_soft_west (heat_wave, summer, 30 days)

**Narrative.** A 30-day summer heat wave with load about 10% above normal (load_peak_ratio 1.10), but day-ahead prices are set too high. Real-time clears 40% below day-ahead (dart_pct -40) as the heat-driven forecast over-shoots and cheap upstate energy floods the real-time market. WEST on-peak prices fall a further 20% (ref_onpeak_pct -20), so the long swap P1 and the heat-rate call P4 lose value. The N.Y.C. minus WEST spread still widens by $45/MWh (pocket_minus_ref_usd 45), which hurts the retail obligation P5. The DART receipt P3 gains slightly from RT below DA, which is a small offset. Gas and spikes are zero. Estimated loss is about -$4.6M from the spread and -$2.4M from WEST price weakness, with about $0.7M of load gains and $0.3M of P3 gain netted off.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.1, "ref_onpeak_pct": -20, "pocket_minus_ref_usd": 45, "dart_pct": -40, "duration_days": 30}`

**Loss** 5.55M (Claude stated 5.80M)  
**Plausibility.** D2 135.0, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.91, "s": 0.95, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -1.08M | P2 +0.81M | P3 +0.37M | P4 -0.50M | P5 -5.18M | P6 +0.05M  
**P&L by channel.** system -1.08M | congestion +0.81M | dart +0.37M | gas -0.50M | zone_volume -5.18M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #7 HW-S11-small-spread-deep-west-slump-rt-below-da (heat_wave, summer, 30 days)

**Narrative.** A 30-day hot summer with typical peak load (load_peak_ratio 1.0) and a deliberately small spread shock, so the scenario stays close to history on the congestion axis. The N.Y.C. minus WEST spread is only $35/MWh wider (pocket_minus_ref_usd 35). The WEST on-peak price is a further 55% lower (ref_onpeak_pct -55) because upstate energy is bottled and demand is weak there, and real-time clears 30% below day-ahead (dart_pct -30) as day-ahead over-procures. Together these cut the long WEST swap P1 and the heat-rate call P4 well below the unshocked path. P5 loses on the spread. P2 and the small P3 gain partly offset these losses. Gas and spike shocks are zero. The estimate is rough because the price effects are not additive, so confidence is low.

**Shock vector (non-neutral).** `{"ref_onpeak_pct": -55, "pocket_minus_ref_usd": 35, "dart_pct": -30, "duration_days": 30}`

**Loss** 5.40M (Claude stated 5.40M)  
**Plausibility.** D2 135.0, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.73, "s": 0.71, "c": 1.0, "d": 0.98}  
**P&L by position.** P1 -1.89M | P2 +0.63M | P3 +0.18M | P4 -0.77M | P5 -3.59M | P6 +0.05M  
**P&L by channel.** system -1.89M | congestion +0.63M | dart +0.18M | gas -0.77M | zone_volume -3.59M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #8 HW-S8-rt-below-da-and-mild-load (heat_wave, summer, 30 days)

**Narrative.** A 30-day hot summer with slightly elevated peak load (load_peak_ratio 1.05). Day-ahead over-procures for the heat, so real-time clears 40% below day-ahead (dart_pct -40). This lowers the realized WEST prices on the long WEST swap P1 and the heat-rate call P4, and gives only a small gain on P3. The WEST on-peak price is a further 30% lower (ref_onpeak_pct -30) from ample upstate supply. The N.Y.C. minus WEST spread is $45/MWh wider (pocket_minus_ref_usd 45) as the city stays constrained. The spread and the extra load drive the loss on P5, the N.Y.C. retail obligation, and P2 offsets only part of it. Gas and spike shocks are zero. The estimate adds the scaled sensitivities and assumes they are roughly additive, so it is uncertain, and P4 may lose less than I assume.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.05, "ref_onpeak_pct": -30, "pocket_minus_ref_usd": 45, "dart_pct": -40, "duration_days": 30}`

**Loss** 5.83M (Claude stated 5.40M)  
**Plausibility.** D2 136.7, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.84, "s": 0.91, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -1.45M | P2 +0.81M | P3 +0.32M | P4 -0.64M | P5 -4.90M | P6 +0.05M  
**P&L by channel.** system -1.45M | congestion +0.81M | dart +0.32M | gas -0.64M | zone_volume -4.90M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #9 HW_S5_soft_gas_price_squeeze_all_long_legs (heat_wave, summer, 30 days)

**Narrative.** A mild-load heat month (duration_days 30) in which every long WEST leg weakens at once while the spread widens only moderately. load_peak_ratio of 1.02 is barely above normal, so P1 and P4 get little load-driven support. gas_hh_pct of -30 reflects soft Henry Hub and lowers WEST power through the fuel link. ref_onpeak_pct of -35 is an extra WEST-specific drop from upstate surplus generation, which hurts P1 and P4. dart_pct of -40 puts real-time 40% below day-ahead, cutting realised WEST prices further. pocket_minus_ref_usd of +40 widens the N.Y.C. premium for local reasons, and P5 loses on it for 30 days. The P2 long spread offsets part of that loss. The loss comes from P5 plus the system and gas channels. The stated loss is a linear estimate from the 5-day sensitivities and is uncertain because the effects are not additive. No table analogue fits a month-long soft-price heat episode.

**Shock vector (non-neutral).** `{"gas_hh_pct": -30, "load_peak_ratio": 1.02, "ref_onpeak_pct": -35, "pocket_minus_ref_usd": 40, "dart_pct": -40, "duration_days": 30}`

**Loss** 5.82M (Claude stated 5.50M)  
**Plausibility.** D2 136.9, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.26, "l": 0.78, "s": 0.87, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -1.88M | P2 +0.72M | P3 +0.22M | P4 -0.73M | P5 -4.21M | P6 +0.05M  
**P&L by channel.** system -1.88M | congestion +0.72M | dart +0.22M | gas -0.73M | zone_volume -4.21M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #10 HW_S6_mild_spread_weak_west_RT_soft_30d (heat_wave, summer, 30 days)

**Narrative.** Over 30 days of a hot but well-forecast summer, load runs only 3% above normal (load_peak_ratio 1.03), which keeps the gains on P1 and P4 small. Upstate WEST on-peak prices are 25% below what load implies (ref_onpeak_pct -25) because upstate supply is ample. Real-time clears 30% below day-ahead (dart_pct -30) because day-ahead over-scheduled the heat. Both shocks cost the long WEST swap P1 and the heat-rate call P4, while P3 gains a little. The N.Y.C. minus WEST spread widens by only $45/MWh (pocket_minus_ref_usd 45, about 1.6 standard deviations), the lowest spread shock of the three scenarios. The loss still comes mainly from P5, which pays this widening on 140 MW around the clock for 30 days. P2 recovers about 15%. Rough estimate: P5 about -5.7M, P2 about +1.0M, P1 and P4 losses from the WEST and real-time shocks about -2.2M, P3 about +0.2M, load gains about +0.2M, net about -6.5M. I state a lower figure because the effects are not additive. Gas and spike shocks are zero because they would only help the long positions. The mechanism combines weak upstate prices with a modest spread widening.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.03, "ref_onpeak_pct": -25, "pocket_minus_ref_usd": 45, "dart_pct": -30, "duration_days": 30}`

**Loss** 5.45M (Claude stated 6.00M)  
**Plausibility.** D2 137.1, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.81, "s": 0.96, "c": 1.0, "d": 0.98}  
**P&L by position.** P1 -1.20M | P2 +0.81M | P3 +0.24M | P4 -0.55M | P5 -4.79M | P6 +0.05M  
**P&L by channel.** system -1.20M | congestion +0.81M | dart +0.24M | gas -0.55M | zone_volume -4.79M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

## Excluded scenarios and why

| scenario | loss (M) | reason |
|---|---|---|
| CS_W_1_NYC_pocket_squeeze | 7.45 | implausible: marginal beyond T |
| CS_W_3_WEST_slump_wide_spread | 7.43 | implausible: marginal beyond T |
| CS_W_4_long_moderate_squeeze | 5.22 | ordinary world (q=0.200 >= 0.05), not a tail event |
| CS_W_5_upstate_soft_downstate_tight | 6.20 | implausible: marginal beyond T |
| CS_W_6_short_sharp_city_basis | 5.14 | ordinary world (q=0.157 >= 0.05), not a tail event |
| CS_W_7_two_week_city_blowout_rt_premium | 6.36 | ordinary world (q=0.078 >= 0.05), not a tail event |
| CS_W_8_west_glut_moderate_spread | 6.30 | ordinary world (q=0.180 >= 0.05), not a tail event |
| CS_W_9_extreme_spread_short_burst | 7.17 | ordinary world (q=0.055 >= 0.05), not a tail event |
| CS_W_CONGESTION_DART_30D | 7.88 | ordinary world (q=0.153 >= 0.05), not a tail event |
| CS_W_ELLIOTT_STYLE_10D | 8.14 | ordinary world (q=0.055 >= 0.05), not a tail event |
| CS_W_MODEST_LOAD_WIDE_SPREAD_30D | 7.71 | ordinary world (q=0.157 >= 0.05), not a tail event |
| CS_W_NYC_SQUEEZE_25D | 6.06 | implausible: marginal beyond T |
| CS_W_OUTAGE_STYLE_RT_PREMIUM_14D | 7.12 | ordinary world (q=0.149 >= 0.05), not a tail event |
| CS_W_SLOW_BURN_WESTSOFT_30D | 6.80 | implausible: marginal beyond T |
| CS_W_congestion_NYC_blowout | 6.02 | ordinary world (q=0.157 >= 0.05), not a tail event |
| CS_W_congestion_NYC_import_squeeze | 6.99 | ordinary world (q=0.153 >= 0.05), not a tail event |
| CS_W_congestion_NYC_squeeze_14d | 6.26 | ordinary world (q=0.157 >= 0.05), not a tail event |
| CS_W_dart_real_time_premium_25d | 3.72 | loss 3.72M below target |
| CS_W_gas_basis_dart_mix_20d | 7.49 | implausible: marginal beyond T |
| CS_W_high_load_fuel_basis_12d | 6.43 | implausible: marginal beyond T |
| CS_W_high_load_long_squeeze | 6.95 | implausible: marginal beyond T |
| CS_W_long_moderate_squeeze_30d | 5.32 | implausible: marginal beyond T |
| CS_W_persistent_congestion_low_load | 8.21 | ordinary world (q=0.157 >= 0.05), not a tail event |
| CS_W_prolonged_high_load_zoneJ | 6.14 | implausible: marginal beyond T |
| CS_W_severe_short_NYC_basis_8d | 7.14 | implausible: marginal beyond T |
| CS_W_short_sharp_Zone_J_squeeze | 7.48 | ordinary world (q=0.055 >= 0.05), not a tail event |
| CS_W_slow_burn_spread_30d | 5.97 | ordinary world (q=0.231 >= 0.05), not a tail event |
| CS_W_upstate_glut_gas_squeeze_20d | 5.50 | implausible: marginal beyond T |
| CS_W_west_discount_gas_basis | 6.68 | ordinary world (q=0.102 >= 0.05), not a tail event |
| CS_W_west_price_slump_plus_spread | 7.24 | implausible: marginal beyond T |
| CS_W_west_softness_wide_spread | 5.88 | ordinary world (q=0.196 >= 0.05), not a tail event |
| GS-W-1-NYC-gas-squeeze-12d | 6.20 | ordinary world (q=0.063 >= 0.05), not a tail event |
| GS-W-1-NYC-pipeline-constraint-30d | 6.71 | ordinary world (q=0.141 >= 0.05), not a tail event |
| GS-W-1-nyc-basis-squeeze | 5.37 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-W-2-cold-gas-squeeze-15d | 5.89 | implausible: marginal beyond g |
| GS-W-2-heat-rate-compression | 7.98 | implausible: marginal beyond T |
| GS-W-2-persistent-basis-30d | 5.71 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-W-3-acute-spread-6d | 7.26 | implausible: marginal beyond g |
| GS-W-3-gas-power-decoupling-30d | 6.24 | implausible: marginal beyond g |
| GS-W-3-pipeline-squeeze-short-severe | 7.12 | ordinary world (q=0.051 >= 0.05), not a tail event |
| GS-W-4-downstate-gas-squeeze-30d | 5.43 | implausible: marginal beyond T |
| GS-W-4-long-moderate-spread | 6.18 | ordinary world (q=0.204 >= 0.05), not a tail event |
| GS-W-4-trapped-upstate-gas-30d | 5.66 | ordinary world (q=0.231 >= 0.05), not a tail event |
| GS-W-5-basis-blowout-15d | 4.89 | loss 4.89M below target |
| GS-W-5-load-amplified-squeeze | 6.17 | implausible: marginal beyond T |
| GS-W-5-upstate-glut-heatrate-squeeze-30d | 5.60 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-W-6-gas-spike-wide-spread | 5.86 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-W-6-sharp-congestion-spell-20d | 5.70 | ordinary world (q=0.145 >= 0.05), not a tail event |
| GS-W-6-sharp-downstate-squeeze-10d | 5.11 | ordinary world (q=0.110 >= 0.05), not a tail event |
| GS_W_1_NYC_gas_squeeze_congestion | 5.63 | implausible: marginal beyond g |
| GS_W_2_stranded_upstate_gas_power_down | 5.56 | ordinary world (q=0.180 >= 0.05), not a tail event |
| GS_W_3_gas_cold_load_zone_volume | 6.01 | implausible: marginal beyond T |
| GS_W_4_basis_blowout_henryhub_flat | 6.24 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS_W_5_gas_shortfall_load_volume_westdrop | 5.65 | implausible: marginal beyond T |
| GS_W_6_gas_constraint_dart_collapse | 5.52 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS_W_BASIS_ONLY_HH_FLAT_20D | 8.76 | ordinary world (q=0.078 >= 0.05), not a tail event |
| GS_W_COLD_LOAD_GAS_CURTAIL_14D | 5.68 | ordinary world (q=0.153 >= 0.05), not a tail event |
| GS_W_MILD_GAS_WEST_SOFT_30D | 7.23 | ordinary world (q=0.188 >= 0.05), not a tail event |
| GS_W_MODEST_COLD_LOAD_BASIS_22D | 6.80 | implausible: marginal beyond T |
| GS_W_NYC_BASIS_25D_SOFT_WEST | 8.30 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS_W_NYC_BASIS_MONTH_30D | 8.53 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS_W_NYC_GAS_SQUEEZE_15D | 6.78 | ordinary world (q=0.133 >= 0.05), not a tail event |
| GS_W_PIPELINE_FREEZE_12D | 7.79 | ordinary world (q=0.078 >= 0.05), not a tail event |
| GS_W_SHARP_SPREAD_14D | 7.32 | ordinary world (q=0.125 >= 0.05), not a tail event |
| GS_W_WEST_COLLAPSE_SPREAD_30D | 8.02 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS_W_WEST_GLUT_NYC_SQUEEZE_30D | 6.49 | ordinary world (q=0.165 >= 0.05), not a tail event |
| HW-S1-sustained-NYC-congestion | 6.38 | implausible: marginal beyond c |
| HW-S12-three-week-wide-spread-soft-west | 5.38 | implausible: marginal beyond c |
| HW-S2-short-intense-NYC-scarcity | 5.95 | implausible: marginal beyond T, c |
| HW-S3-prolonged-moderate-widening-gas-basis | 5.66 | implausible: marginal beyond c |
| HW-S4-bottled-upstate-NYC-squeeze | 5.61 | implausible: marginal beyond c |
| HW-S9-concentrated-spread-gas-basis | 6.39 | implausible: marginal beyond c |
| HW_S1_NYC_congestion_blowout | 6.03 | implausible: marginal beyond T, c |
| HW_S1_NYC_congestion_sustained | 9.51 | implausible: marginal beyond c |
| HW_S1_NYC_import_constraint_10d | 6.25 | implausible: marginal beyond T, c |
| HW_S2_WEST_glut_NYC_squeeze | 6.01 | implausible: marginal beyond c |
| HW_S2_bottled_upstate_wide_spread | 8.22 | implausible: marginal beyond T, c |
| HW_S2_prolonged_congestion_20d | 5.32 | implausible: marginal beyond c |
| HW_S3_extreme_nyc_pocket_short | 9.82 | implausible: marginal beyond T, c |
| HW_S3_west_glut_RT_below_DA_12d | 7.66 | implausible: marginal beyond T, c |
| HW_S6_high_load_volume_squeeze | 5.78 | implausible: marginal beyond T, c |
| HW_S9_short_sharp_nyc_premium | 5.78 | implausible: marginal beyond c |
| HW_S9_soft_gas_wide_spread_15d | 6.13 | implausible: marginal beyond c |
| HW_SUMMER_GAS_BASIS_HEATRATE_SQUEEZE | 6.98 | implausible: marginal beyond T |
| HW_SUMMER_LOAD_LED_NYC_STRESS | 7.52 | implausible: marginal beyond T |
| HW_SUMMER_NYC_LOADPOCKET_BLOWOUT | 9.23 | implausible: marginal beyond T, c |
| HW_SUMMER_RECORD_LOAD_MODEST_SPREAD | 6.78 | implausible: marginal beyond T |
| HW_SUMMER_SHORT_SHARP_NYC_ISOLATION | 6.85 | implausible: marginal beyond c |
| HW_SUMMER_THREE_WEEK_LOAD_POCKET | 7.84 | implausible: marginal beyond c |
| HW_SUMMER_TWO_WEEK_HIGH_LOAD_SPREAD_BURST | 6.85 | implausible: marginal beyond T, c |
| LLS_SUMMER_BROAD_SOFTENING_25D | 6.66 | implausible: marginal beyond c |
| LLS_SUMMER_CONGESTION_1 | 6.37 | implausible: marginal beyond c |
| LLS_SUMMER_CONGESTION_30D | 7.28 | implausible: marginal beyond c |
| LLS_SUMMER_INTENSE_SPREAD_12D | 6.04 | implausible: marginal beyond c |
| LLS_SUMMER_MEDIUM_WINDOW_WIDE_12 | 6.82 | implausible: marginal beyond c |
| LLS_SUMMER_MID_SQUEEZE_20D | 5.91 | implausible: marginal beyond c |
| LLS_SUMMER_SHARP_SPREAD_10D | 5.53 | implausible: marginal beyond c |
| LLS_SUMMER_SHORT_INTENSE_9 | 6.25 | implausible: marginal beyond c |
| LLS_SUMMER_SHORT_SQUEEZE_15D | 6.30 | implausible: marginal beyond c |
| LLS_SUMMER_SHORT_WIDE_SPREAD_6 | 6.17 | implausible: marginal beyond c |
| LLS_SUMMER_SYSTEM_LED_5 | 4.81 | loss 4.81M below target |
| LLS_SUMMER_SYSTEM_PRICE_COLLAPSE_2 | 5.73 | implausible: marginal beyond T |
| LLS_SUMMER_WIDE_SPREAD_GAS_BASIS_8 | 7.23 | implausible: marginal beyond c |
| LLS_SUM_02_short_sharp_pocket_squeeze | 6.78 | implausible: marginal beyond c |
| LLS_SUM_03_gas_and_west_slump | 6.05 | implausible: marginal beyond c |
| LLS_SUM_05_pocket_squeeze_25d | 6.43 | implausible: marginal beyond c |
| LLS_SUM_08_sharp_15d_pocket_dislocation | 6.09 | implausible: marginal beyond c |
| LLS_SUM_1_upstate_load_miss_spread_blowout | 4.91 | loss 4.91M below target |
| LLS_SUM_2_west_price_collapse_gas_soft | 4.98 | loss 4.98M below target |
| LLS_SUM_3_short_sharp_nyc_congestion | 4.79 | loss 4.79M below target |
| LLS_SUM_7_pure_congestion_zone_volume | 6.36 | implausible: marginal beyond c |
| LLS_SUM_A_congestion_widening | 7.63 | implausible: marginal beyond c |
| LLS_SUM_C_short_sharp_spread | 6.28 | implausible: marginal beyond c |
| LLS_SUM_G_pure_congestion_30d | 6.36 | implausible: marginal beyond c |
| LLS_SUM_H_short_extreme_spread_15d | 7.03 | implausible: marginal beyond c |
| LLS_SUM_I_severe_spread_12d_price_dip | 7.03 | implausible: marginal beyond c |
| LLS_SUM_K_deep_shortfall_system_slump_30d | 6.26 | implausible: marginal beyond T |
