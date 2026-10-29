# Ranked reverse-stress scenarios (NYISO book)

Source logs: live_full_sonnet. Models: claude-sonnet-5-5. Client kinds: live.  
Target loss 5.0M. Scenarios read: 170; ranked (eligible): 55; excluded: 115.  
q is a rank against about 250 non-overlapping 10-day windows of 2019-2025, not a probability; fit window 2019-2025; daily averaging understates hourly spikes. A client kind other than the live API means scripted output, not Claude results.  
Largest-loss channel across ranked scenarios: {"zone_volume": 55} (one channel for all of them means the book, not the search, limits diversity).

Coherence grading by a human: [PENDING]. Scenarios are drafts for a risk manager to accept or hedge, not forecasts.

## Ranked scenarios (most plausible first)

### #1 GS_W_severe_gas_shortage_C (gas_supply, winter, 10 days)

**Narrative.** A severe 10-day gas shortage with Henry Hub up 150% and a $10/MMBtu New York gas basis premium hits P4, since the added gas cost lowers the heat-rate call payoff. The load peak rises 8% on cold weather. Gas-fired units downstate set the price while upstate stays comparatively insulated, so the N.Y.C. minus WEST spread widens by $250/MWh, which is inside the winter historical maximum of 400.6. P5 loses about $10M, P2 gains about $1.5M and the higher gas and load lift P1 by about $1M. The net is roughly $7M. A severe, short, high-intensity scenario, driven mainly by zone volume and congestion, with a small headwind on the gas channel. The estimate scales the 5-day sensitivities linearly and is uncertain.

**Shock vector (non-neutral).** `{"gas_hh_pct": 150, "ny_gas_basis_usd": 10, "load_peak_ratio": 1.08, "pocket_minus_ref_usd": 250, "duration_days": 10}`

**Loss** 7.41M (Claude stated 6.50M)  
**Plausibility.** D2 88.8, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 1.0, "l": 1.0, "s": 0.09, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.91M | P2 +1.50M | P3 -0.04M | P4 -0.03M | P5 -9.71M | P6 -0.05M  
**P&L by channel.** system +0.91M | congestion +1.50M | dart -0.04M | gas -0.03M | zone_volume -9.71M | tail -0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 0.0

### #2 GS_W_short_sharp_spread_F (gas_supply, winter, 8 days)

**Narrative.** A sharp 8-day downstate gas delivery failure doubles Henry Hub (+100%). The N.Y.C. minus WEST spread widens by $280/MWh, which is below the winter historical maximum of 400.6, because N.Y.C. units are forced onto scarce gas while upstate is largely unaffected. Load is normal, WEST on-peak has no extra shock beyond the gas effect, and there are no spikes. P5 loses about $8.3M on the short N.Y.C. retail obligation. P2 recovers about $1.3M, and P1 and P4 gain about $0.5M from the higher WEST price implied by gas. The loss is concentrated in a few days, so this is a short, high-intensity congestion and zone-volume scenario, unlike the long moderate ones. The estimate scales the supplied 5-day sensitivities linearly and is approximate.

**Shock vector (non-neutral).** `{"gas_hh_pct": 100, "pocket_minus_ref_usd": 280, "duration_days": 8}`

**Loss** 6.29M (Claude stated 6.40M)  
**Plausibility.** D2 90.2, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.98, "l": 0.98, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.33M | P2 +1.34M | P3 -0.02M | P4 +0.04M | P5 -7.97M | P6 -0.01M  
**P&L by channel.** system +0.33M | congestion +1.34M | dart -0.02M | gas +0.04M | zone_volume -7.97M | tail -0.01M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #3 CS_W_CONGESTION_02 (cold_snap, winter, 6 days)

**Narrative.** Storm-type event in which generator trips and import curtailments squeeze NYC while WEST stays comparatively unconstrained, as in Winter Storm Elliott. The NYC minus WEST spread widens by $350/MWh (pocket_minus_ref_usd) for 6 days (duration_days), below the 400.6 historical maximum. Load is 5% above a typical winter day (load_peak_ratio 1.05) and Henry Hub is up 40% (gas_hh_pct), which is a modest cold-snap gas response. P5 carries the loss, because it is short 140 MW in NYC around the clock and the hedge in WEST does not cover the spread. P2 and the long WEST positions offset only a small part. Estimate extrapolated linearly from 5-day sensitivities (about $3,300 net loss per $/MWh-day); the true figure is uncertain.

**Shock vector (non-neutral).** `{"gas_hh_pct": 40, "load_peak_ratio": 1.05, "pocket_minus_ref_usd": 350, "duration_days": 6}`

**Loss** 6.56M (Claude stated 6.00M)  
**Plausibility.** D2 127.7, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.93, "l": 1.0, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.23M | P2 +1.26M | P3 +0.00M | P4 +0.06M | P5 -8.10M | P6 -0.00M  
**P&L by channel.** system +0.23M | congestion +1.26M | dart +0.00M | gas +0.06M | zone_volume -8.10M | tail -0.00M  
**Analogue.** Winter Storm Elliott (NYISO) 2022-12-23; **confidence** medium; **soft penalty** 0.0

### #4 CS_W_ELLIOTT_STYLE_SPREAD_7D (cold_snap, winter, 7 days)

**Narrative.** A short, severe 7-day storm in the style of Winter Storm Elliott, with forced outages and import curtailments isolating N.Y.C. The N.Y.C. minus WEST spread widens by $350/MWh (pocket_minus_ref_usd 350), which is inside the winter historical maximum. Load is 5% above a typical winter day (load_peak_ratio 1.05) and Henry Hub is up 30% (gas_hh_pct 30), as a cold snap requires. The loss is concentrated in P5, the N.Y.C. retail obligation hedged only at WEST, for all 7 days (duration_days 7). The long spread position P2 offsets only a small part of it. The small gains on P1 and P4 from higher load and gas barely dent the total. No WEST on-peak spike, no extra WEST move and no real-time/day-ahead shock are used, so the channel is pure congestion plus zone volume. The estimate scales the supplied winter sensitivity linearly and ignores interactions.

**Shock vector (non-neutral).** `{"gas_hh_pct": 30, "load_peak_ratio": 1.05, "pocket_minus_ref_usd": 350, "duration_days": 7}`

**Loss** 7.62M (Claude stated 7.00M)  
**Plausibility.** D2 128.4, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.9, "l": 1.0, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.19M | P2 +1.47M | P3 -0.00M | P4 +0.05M | P5 -9.33M | P6 +0.00M  
**P&L by channel.** system +0.19M | congestion +1.47M | dart -0.00M | gas +0.05M | zone_volume -9.33M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) 23-24 December 2022; **confidence** medium; **soft penalty** 0.0

### #5 HW-S15-rt-below-da-cheap-gas-spread (heat_wave, summer, 30 days)

**Narrative.** A 30-day summer pattern with normal peak load (load_peak_ratio 1.0) in which day-ahead over-forecasts the heat, so real-time clears 30% below day-ahead (dart_pct -30). This lowers the WEST price seen by the long swap P1 and the heat-rate call P4, while the DART receipt P3 gains a little. Henry Hub is 25% lower (gas_hh_pct -25) on weak gas demand, and WEST on-peak is a further 10% below the implied level (ref_onpeak_pct -10). N.Y.C. stays tight, so the spread is $45/MWh wider (pocket_minus_ref_usd 45). P5 loses about $4.6M, P2 earns about $0.8M, P1 and P4 lose about $1.8M together, and P3 gains about $0.2M. Net is about -$5.4M. This is a linear extrapolation and uncertain.

**Shock vector (non-neutral).** `{"gas_hh_pct": -25, "ref_onpeak_pct": -10, "pocket_minus_ref_usd": 45, "dart_pct": -30, "duration_days": 30}`

**Loss** 5.43M (Claude stated 5.20M)  
**Plausibility.** D2 138.7, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.35, "l": 0.73, "s": 0.98, "c": 1.0, "d": 0.98}  
**P&L by position.** P1 -1.33M | P2 +0.81M | P3 +0.20M | P4 -0.54M | P5 -4.62M | P6 +0.05M  
**P&L by channel.** system -1.33M | congestion +0.81M | dart +0.20M | gas -0.54M | zone_volume -4.62M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #6 LLS_SUMMER_G_dart_soft_wide_spread_lower_pocket (large_load_shortfall, summer, 30 days)

**Narrative.** Large new loads arrive about 900 MW slower than the 2030 Gold Book path (large_load_shock_mw -900), so the daily peak is about 3% lower (load_peak_ratio 0.97). Upstate is oversupplied, so WEST on-peak falls a further 25% (ref_onpeak_pct -25). Day-ahead over-procured for load that never arrived, so real-time clears 45% below day-ahead (dart_pct -45), which lowers the WEST real-time settlement for the long swap P1 and the heat-rate call P4. N.Y.C. stays import-constrained, so the N.Y.C. minus WEST spread is $45/MWh wider for 30 days (pocket_minus_ref_usd 45). P5 loses about $4.4M and P2 gains about $0.8M. P1 loses about $1.8M and P4 about $0.8M, partly offset by a P3 gain of about $0.3M. Gas, basis and spike shocks are zero. This is a linear extrapolation from the 5-day sensitivities, so it is uncertain.

**Shock vector (non-neutral).** `{"load_peak_ratio": 0.97, "large_load_shock_mw": -900, "ref_onpeak_pct": -25, "pocket_minus_ref_usd": 45, "dart_pct": -45, "duration_days": 30}`

**Loss** 5.63M (Claude stated 5.80M)  
**Plausibility.** D2 138.8, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.55, "s": 0.86, "c": 1.0, "d": 0.94}  
**P&L by position.** P1 -1.79M | P2 +0.81M | P3 +0.31M | P4 -0.74M | P5 -4.26M | P6 +0.05M  
**P&L by channel.** system -1.79M | congestion +0.81M | dart +0.31M | gas -0.74M | zone_volume -4.26M | tail +0.05M  
**Analogue.** NYISO Gold Book large-load series Gold Book 2030 shortfall scenario; **confidence** low; **soft penalty** 1.0

### #7 HW_SUM_H_da_overforecast_rt_soft (heat_wave, summer, 28 days)

**Narrative.** A 28-day heat wave with load at a ratio of 1.0 leaves the N.Y.C. minus WEST spread $50/MWh wider, about 1.7 summer standard deviations, so the short N.Y.C. retail obligation P5 loses on every hour. Day-ahead over-forecasts the heat and real-time clears 40% below day-ahead (dart_pct -40). This lowers WEST on-peak realised prices and cuts the P1 and P4 gains, while P3 gains a little. WEST on-peak is a further 20% below the implied level (ref_onpeak_pct -20) as upstate supply is ample. This channel is the DA-RT mismatch, not a price spike, because spikes make the book gain overall. Estimated effects: P5 about -$5.2M including the hedge, P2 about +$0.8M, P1 and P4 about -$2.2M from the dart and WEST shocks, P3 and P6 about +$0.5M. The net loss is about $5.4M. This is a linear extrapolation of the 5-day sensitivities and is uncertain.

**Shock vector (non-neutral).** `{"ref_onpeak_pct": -20, "pocket_minus_ref_usd": 50, "dart_pct": -40, "duration_days": 28}`

**Loss** 5.27M (Claude stated 5.40M)  
**Plausibility.** D2 140.7, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.73, "s": 0.93, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -1.19M | P2 +0.84M | P3 +0.30M | P4 -0.51M | P5 -4.74M | P6 +0.02M  
**P&L by channel.** system -1.19M | congestion +0.84M | dart +0.30M | gas -0.51M | zone_volume -4.74M | tail +0.02M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #8 LLS_SUM_WEST_DEEP_SLUMP_MODEST_SPREAD (large_load_shortfall, summer, 30 days)

**Narrative.** New large loads arrive about 800 MW late (large_load_shock_mw = -800, close to the 2030 shortfall case), and the summer peak is 4% lower (load_peak_ratio 0.96). Gas is 30% cheaper (gas_hh_pct = -30) and WEST on-peak falls a further 70% (ref_onpeak_pct = -70), inside the summer historical minimum of -88.5%. This is a deep upstate price slump. N.Y.C. is supported by local constraints, so the N.Y.C. minus WEST spread widens by only $30/MWh (pocket_minus_ref_usd = 30). All shocks last 30 days. The main losses come from the long P1 swap on the lower WEST price, gas and load, about $2.5M. The P4 heat-rate call is wiped out, about $0.8M. P5 loses about $2.8M on the wider spread at slightly lower load, and P2 gives back about $0.5M. The net is about $5.5M. I scaled this by hand from the engine's last results: P1 loses about $25k per percentage point of WEST move over 30 days, and P5 loses about $100,800 MWh times the load multiplier per $1/MWh of spread. This channel is mainly the WEST system price, with spread as a secondary factor, so it differs from the spread-led cases.

**Shock vector (non-neutral).** `{"gas_hh_pct": -30, "load_peak_ratio": 0.96, "large_load_shock_mw": -800, "ref_onpeak_pct": -70, "pocket_minus_ref_usd": 30, "duration_days": 30}`

**Loss** 5.25M (Claude stated 5.50M)  
**Plausibility.** D2 141.8, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.26, "l": 0.53, "s": 0.53, "c": 1.0, "d": 1.0}  
**P&L by position.** P1 -2.22M | P2 +0.54M | P3 -0.02M | P4 -0.80M | P5 -2.80M | P6 +0.05M  
**P&L by channel.** system -2.22M | congestion +0.54M | dart -0.02M | gas -0.80M | zone_volume -2.80M | tail +0.05M  
**Analogue.** NYISO Gold Book large-load series 2030 scenario range; **confidence** medium; **soft penalty** 1.0

### #9 LLS_SUMMER_E_soft_realtime_system_plus_spread (large_load_shortfall, summer, 30 days)

**Narrative.** Large loads arrive about 900 MW slower than the 2030 Gold Book path (large_load_shock_mw -900), cutting the daily peak by about 2% (load_peak_ratio 0.98). Upstate is oversupplied, so the WEST on-peak price falls a further 20% (ref_onpeak_pct -20). Real-time also clears 40% below day-ahead (dart_pct -40) because the day-ahead forecast over-procured for load that never arrived. That lowers WEST real-time on-peak prices, hurts the long swap P1 and the heat-rate call P4, and gives back a small gain on the DART position P3. N.Y.C. is less affected, so the spread widens by $50/MWh for 30 days (pocket_minus_ref_usd 50), costing P5 more than P2 earns. The spread contributes about -$3.6M, and the system and gas channels about -$2.0M to -$2.5M, partly offset by a P3 gain of about $0.3M. The estimate is a rough linear extrapolation, so confidence is low.

**Shock vector (non-neutral).** `{"load_peak_ratio": 0.98, "large_load_shock_mw": -900, "ref_onpeak_pct": -20, "pocket_minus_ref_usd": 50, "dart_pct": -40, "duration_days": 30}`

**Loss** 5.86M (Claude stated 5.40M)  
**Plausibility.** D2 142.3, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.57, "s": 0.93, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -1.60M | P2 +0.90M | P3 +0.29M | P4 -0.69M | P5 -4.80M | P6 +0.05M  
**P&L by channel.** system -1.60M | congestion +0.90M | dart +0.29M | gas -0.69M | zone_volume -4.80M | tail +0.05M  
**Analogue.** NYISO Gold Book large-load series Gold Book 2030 shortfall scenario; **confidence** low; **soft penalty** 1.0

### #10 LLS_SUMMER_I_system_and_gas_led_narrow_spread (large_load_shortfall, summer, 30 days)

**Narrative.** Large new loads arrive about 1,200 MW slower than the Gold Book expects (large_load_shock_mw -1200), within the stated shortfall range. The daily peak is about 4% lower (load_peak_ratio 0.96). Weak upstate demand pulls Henry Hub down 30% (gas_hh_pct -30) and WEST on-peak falls a further 35% (ref_onpeak_pct -35). Real-time clears 50% below day-ahead (dart_pct -50). This scenario is system and gas led. P1 loses about $2.4M, and P4 loses about $1.0M, helped by a $2/MMBtu N.Y.C. gas basis (ny_gas_basis_usd 2). The N.Y.C. minus WEST spread is only $35/MWh wider for 30 days (pocket_minus_ref_usd 35). P5 loses about $3.4M against a P2 gain of about $0.6M, and P3 gains about $0.3M. The estimate is a linear extrapolation and is uncertain, and P4 losses may be capped.

**Shock vector (non-neutral).** `{"gas_hh_pct": -30, "ny_gas_basis_usd": 2, "load_peak_ratio": 0.96, "large_load_shock_mw": -1200, "ref_onpeak_pct": -35, "pocket_minus_ref_usd": 35, "dart_pct": -50, "duration_days": 30}`

**Loss** 5.32M (Claude stated 5.90M)  
**Plausibility.** D2 142.6, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.84, "l": 0.48, "s": 0.19, "c": 1.0, "d": 0.92}  
**P&L by position.** P1 -2.20M | P2 +0.63M | P3 +0.24M | P4 -0.83M | P5 -3.20M | P6 +0.05M  
**P&L by channel.** system -2.20M | congestion +0.63M | dart +0.24M | gas -0.83M | zone_volume -3.20M | tail +0.05M  
**Analogue.** NYISO Gold Book large-load series Gold Book 2035 shortfall range; **confidence** low; **soft penalty** 1.0

## Excluded scenarios and why

| scenario | loss (M) | reason |
|---|---|---|
| CS-W-CONG-1 | 6.91 | ordinary world (q=0.125 >= 0.05), not a tail event |
| CS-W-HILOAD-6 | 5.90 | implausible: marginal beyond T |
| CS-W-LOAD-2 | 7.79 | implausible: marginal beyond T |
| CS-W-LONGSPREAD-4 | 5.94 | ordinary world (q=0.216 >= 0.05), not a tail event |
| CS-W-SPREAD-3 | 6.80 | ordinary world (q=0.055 >= 0.05), not a tail event |
| CS-W-WESTSOFT-5 | 6.47 | ordinary world (q=0.188 >= 0.05), not a tail event |
| CS_W_DIVERGENCE_30D | 8.82 | ordinary world (q=0.165 >= 0.05), not a tail event |
| CS_W_DOWNSTATE_PINCH_08 | 6.26 | ordinary world (q=0.086 >= 0.05), not a tail event |
| CS_W_ELLIOTT_STYLE_7D | 7.04 | implausible: marginal beyond T |
| CS_W_ELLIOTT_STYLE_SPREAD_BLOWOUT | 6.98 | implausible: marginal beyond T |
| CS_W_GASBASIS_LOAD_09 | 6.37 | implausible: marginal beyond T |
| CS_W_HIGHLOAD_SHORT_10D | 6.78 | implausible: marginal beyond T |
| CS_W_ISOLATED_NYC_8D | 6.24 | ordinary world (q=0.055 >= 0.05), not a tail event |
| CS_W_LONGMILD_05 | 6.28 | ordinary world (q=0.204 >= 0.05), not a tail event |
| CS_W_LONG_MODERATE_SPREAD_30D | 6.56 | ordinary world (q=0.208 >= 0.05), not a tail event |
| CS_W_MILD_SPREAD_LONG_30D | 5.48 | ordinary world (q=0.239 >= 0.05), not a tail event |
| CS_W_NYC_BASIS_BLOWOUT_15D | 6.54 | ordinary world (q=0.106 >= 0.05), not a tail event |
| CS_W_NYC_SQUEEZE_14D | 7.36 | ordinary world (q=0.129 >= 0.05), not a tail event |
| CS_W_PERSISTENT_03 | 8.64 | implausible: marginal beyond T |
| CS_W_PERSISTENT_LAG_30D | 6.53 | implausible: marginal beyond T |
| CS_W_PERSISTENT_NYC_CONGESTION | 6.91 | implausible: marginal beyond T |
| CS_W_SHARP_HIGHLOAD_5D | 6.65 | implausible: marginal beyond T |
| CS_W_SHARP_SPREAD_12D_DART | 6.58 | ordinary world (q=0.122 >= 0.05), not a tail event |
| CS_W_SLOWBURN_04 | 5.84 | ordinary world (q=0.165 >= 0.05), not a tail event |
| CS_W_SLOW_BLEED_LAGGING_WEST_30D | 6.44 | ordinary world (q=0.235 >= 0.05), not a tail event |
| CS_W_SPREAD_WEST_SOFT_GAS_BASIS | 7.50 | ordinary world (q=0.078 >= 0.05), not a tail event |
| CS_W_TWO_WEEK_COLD_20D | 6.70 | ordinary world (q=0.161 >= 0.05), not a tail event |
| CS_W_UPSTATE_GLUT_07 | 6.43 | ordinary world (q=0.220 >= 0.05), not a tail event |
| CS_W_UPSTATE_SOFT_06 | 6.32 | ordinary world (q=0.161 >= 0.05), not a tail event |
| CS_W_WEST_GLUT_SPREAD_20D | 6.66 | ordinary world (q=0.161 >= 0.05), not a tail event |
| CS_W_WEST_SOFT_NYC_TIGHT_25D | 6.79 | ordinary world (q=0.188 >= 0.05), not a tail event |
| CS_W_ZONEJ_SQUEEZE_20D | 7.57 | implausible: marginal beyond T |
| CS_W_ZONEVOL_01 | 5.82 | implausible: marginal beyond T |
| GS-W-1-Z6-squeeze-congestion | 7.33 | implausible: marginal beyond g |
| GS-W-1-nyc-gas-squeeze | 7.60 | implausible: marginal beyond g |
| GS-W-2-gas-shortage-high-load-zonevolume | 7.28 | implausible: marginal beyond T, g |
| GS-W-2-west-decoupled-from-gas | 10.91 | implausible: marginal beyond g |
| GS-W-3-short-sharp-zone-volume | 6.91 | implausible: marginal beyond T, g |
| GS-W-3-upstate-glut-spread-decoupling | 8.13 | ordinary world (q=0.125 >= 0.05), not a tail event |
| GS-W-4-long-moderate-basis-spread | 6.15 | ordinary world (q=0.161 >= 0.05), not a tail event |
| GS-W-4-prolonged-moderate-spread | 7.55 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-W-5-three-week-cold-gas-load | 6.15 | implausible: marginal beyond T |
| GS-W-5-upstate-weakness-wide-spread | 6.72 | ordinary world (q=0.125 >= 0.05), not a tail event |
| GS-W-6-sustained-gas-squeeze-high-load | 6.90 | implausible: marginal beyond T |
| GS-W-6-two-week-downstate-squeeze | 6.30 | ordinary world (q=0.125 >= 0.05), not a tail event |
| GS_W_01_downstate_pipeline_squeeze | 6.27 | implausible: marginal beyond g |
| GS_W_02_nyc_squeeze_west_soft | 6.40 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS_W_03_acute_gas_curtailment_spread_blowout | 7.60 | implausible: marginal beyond g |
| GS_W_04_prolonged_moderate_spread | 6.07 | ordinary world (q=0.161 >= 0.05), not a tail event |
| GS_W_05_cold_load_soft_west | 5.74 | ordinary world (q=0.231 >= 0.05), not a tail event |
| GS_W_06_west_price_collapse_with_spread | 5.91 | ordinary world (q=0.165 >= 0.05), not a tail event |
| GS_W_1_NYC_gas_squeeze_congestion | 8.34 | ordinary world (q=0.129 >= 0.05), not a tail event |
| GS_W_2_NYC_basis_blowout_short | 7.22 | implausible: marginal beyond g |
| GS_W_3_persistent_load_zone_volume | 8.27 | implausible: marginal beyond T |
| GS_W_4_moderate_gas_wide_spread_flat_load | 6.15 | ordinary world (q=0.161 >= 0.05), not a tail event |
| GS_W_5_sharp_20d_basis_spread | 6.43 | implausible: marginal beyond T, g |
| GS_W_6_dart_real_time_stress_with_spread | 5.84 | implausible: marginal beyond T |
| GS_W_basis_weak_west_E | 6.37 | ordinary world (q=0.149 >= 0.05), not a tail event |
| GS_W_congestion_squeeze_A | 6.93 | ordinary world (q=0.153 >= 0.05), not a tail event |
| GS_W_flat_long_weakwest_G | 6.04 | ordinary world (q=0.243 >= 0.05), not a tail event |
| GS_W_gas_basis_load_weakwest_K | 7.64 | ordinary world (q=0.161 >= 0.05), not a tail event |
| GS_W_long_moderate_squeeze_D | 6.24 | ordinary world (q=0.204 >= 0.05), not a tail event |
| GS_W_lowspread_30d_weakwest_J | 5.80 | ordinary world (q=0.255 >= 0.05), not a tail event |
| GS_W_mild_cold_gas_basis_H | 5.97 | ordinary world (q=0.184 >= 0.05), not a tail event |
| GS_W_split_market_B | 6.61 | ordinary world (q=0.204 >= 0.05), not a tail event |
| GS_W_three_week_split_L | 5.66 | ordinary world (q=0.176 >= 0.05), not a tail event |
| GS_W_twelve_day_split_I | 5.74 | ordinary world (q=0.149 >= 0.05), not a tail event |
| HW-S1-zone-volume-congestion | 9.19 | implausible: marginal beyond T, c |
| HW-S10-short-sharp-nyc-squeeze | 5.44 | implausible: marginal beyond c |
| HW-S12-da-over-forecast-congestion | 6.07 | implausible: marginal beyond c |
| HW-S2-pocket-squeeze-west-soft | 6.83 | implausible: marginal beyond T, c |
| HW-S3-persistent-spread-gas-basis | 9.15 | implausible: marginal beyond c |
| HW-S4-persistent-nyc-congestion | 6.28 | implausible: marginal beyond c |
| HW-S5-da-premium-west-soft | 6.43 | implausible: marginal beyond c |
| HW-S7-pure-congestion-normal-load | 6.35 | implausible: marginal beyond c |
| HW_20D_HIGHLOAD_SPREAD100_SHORT_SHARP | 6.06 | implausible: marginal beyond T, c |
| HW_20D_SPREAD90_DART_NEG40_BASIS4 | 5.81 | implausible: marginal beyond c |
| HW_25D_SPREAD80_WESTDISCOUNT30 | 6.76 | implausible: marginal beyond c |
| HW_CONGESTION_NYC_PACKET_20D | 8.34 | implausible: marginal beyond c |
| HW_HIGHLOAD_30D_SPREAD60_WESTSOFT35 | 6.90 | implausible: marginal beyond T |
| HW_PERSISTENT_SPREAD_GAS_BASIS_30D | 6.87 | implausible: marginal beyond T, c |
| HW_S1_load_driven_NYC_congestion | 8.01 | implausible: marginal beyond T, c |
| HW_S1_sustained_NYC_congestion_high_load | 7.15 | implausible: marginal beyond T, c |
| HW_S2_short_extreme_NYC_pocket_squeeze | 7.13 | implausible: marginal beyond T, c |
| HW_S2_west_soft_nyc_constrained | 10.37 | implausible: marginal beyond T, c |
| HW_S3_month_long_WEST_soft_wide_spread | 8.17 | implausible: marginal beyond T, c |
| HW_S3_short_sharp_nyc_blowout | 7.07 | implausible: marginal beyond T, c |
| HW_S4_long_moderate_congestion | 6.17 | implausible: marginal beyond c |
| HW_S4_moderate_spread_soft_WEST_30d | 7.67 | implausible: marginal beyond c |
| HW_S5_high_load_gas_basis_cheap_WEST | 7.48 | implausible: marginal beyond T |
| HW_S5_west_soft_long_hot_spell | 7.31 | implausible: marginal beyond T |
| HW_S6_RT_below_DA_soft_WEST_spread | 6.85 | implausible: marginal beyond T |
| HW_S6_three_week_pocket_squeeze | 6.37 | implausible: marginal beyond c |
| HW_SEVERE_NYC_BLOWOUT_10D | 6.98 | implausible: marginal beyond T, c |
| HW_SUM_A_nyc_import_squeeze_high_load | 6.68 | implausible: marginal beyond T, c |
| HW_SUM_B_west_surplus_nyc_constrained | 7.71 | implausible: marginal beyond T, c |
| HW_SUM_C_gas_squeeze_extreme_load_spread | 8.29 | implausible: marginal beyond T, c |
| LLS-S1-congestion-widening | 7.70 | implausible: marginal beyond c |
| LLS-S2-congestion-only-pocket-spread | 7.18 | implausible: marginal beyond c |
| LLS-S2-zone-volume-short-burst | 6.46 | implausible: marginal beyond c |
| LLS-S3-gas-slump-system-plus-spread | 8.10 | implausible: marginal beyond c |
| LLS-S6-short-sharp-pocket-decoupling | 6.19 | implausible: marginal beyond c |
| LLS_SUMMER_A_congestion_glut | 8.37 | implausible: marginal beyond c |
| LLS_SUMMER_B_wide_spread_20d | 6.75 | implausible: marginal beyond c |
| LLS_SUMMER_C_short_sharp_pocket | 6.09 | implausible: marginal beyond c |
| LLS_SUMMER_H_25d_gas_soft_and_spread | 4.95 | loss 4.95M below target |
| LLS_SUMMER_K_25d_spread_led_light_system | 5.91 | implausible: marginal beyond c |
| LLS_SUMMER_L_system_gas_collapse_small_spread | 5.20 | implausible: marginal beyond T, s |
| LLS_SUM_12_basis_dart_25day_spread | 5.86 | implausible: marginal beyond c |
| LLS_SUM_1_sustained_congestion | 9.36 | implausible: marginal beyond c |
| LLS_SUM_2_downstate_squeeze | 7.75 | implausible: marginal beyond c |
| LLS_SUM_3_short_sharp_pocket | 7.15 | implausible: marginal beyond c |
| LLS_SUM_4_pure_spread_widening | 6.78 | implausible: marginal beyond c |
| LLS_SUM_6_deep_2035_shortfall | 5.96 | implausible: marginal beyond c |
| LLS_SUM_SHARP_LOCATIONAL_DIVERGENCE | 7.07 | implausible: marginal beyond c |
