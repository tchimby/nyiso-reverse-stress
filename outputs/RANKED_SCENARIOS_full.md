# Ranked reverse-stress scenarios (NYISO book)

Source logs: live_full. Models: claude-haiku-5-5. Client kinds: live.  
Target loss 5.0M. Scenarios read: 165; ranked (eligible): 18; excluded: 147.  
q is a rank against about 250 non-overlapping 10-day windows of 2019-2025, not a probability; fit window 2019-2025; daily averaging understates hourly spikes. A client kind other than the live API means scripted output, not Claude results.  
Largest-loss channel across ranked scenarios: {"zone_volume": 18} (one channel for all of them means the book, not the search, limits diversity).

Coherence grading by a human: [PENDING]. Scenarios are drafts for a risk manager to accept or hedge, not forecasts.

## Ranked scenarios (most plausible first)

### #1 GS-W18-pocket-spread-12d-flat-load (gas_supply, winter, 12 days)

**Narrative.** A twelve-day N.Y.C. gas constraint widens the N.Y.C. minus WEST on-peak spread by 260 $/MWh on each shocked day, with load held at a typical winter level so the loss comes from the spread rather than from load. Henry Hub is unchanged, and the Z6 NY basis adds 6 $/MWh, which lowers the heat-rate call P4 through its gas cost. WEST on-peak prices stay near their unshocked level, so the long WEST swap P1 contributes little. The short retail obligation P5 accumulates the spread loss across the full period, partly offset by the long N.Y.C.-WEST spread P2. Real-time and day-ahead prices are assumed to move together, so P3 is not a driver. This scenario tests a long-duration, moderate-load pocket squeeze driven by a basis and spread channel rather than a spike or a national gas move.

**Shock vector (non-neutral).** `{"ny_gas_basis_usd": 6.0, "pocket_minus_ref_usd": 260.0, "duration_days": 12}`

**Loss** 9.38M (Claude stated 6.50M)  
**Plausibility.** D2 90.5, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.98, "l": 0.98, "s": 0.06, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.00M | P2 +1.87M | P3 +0.00M | P4 -0.13M | P5 -11.12M | P6 +0.00M  
**P&L by channel.** system +0.00M | congestion +1.87M | dart +0.00M | gas -0.13M | zone_volume -11.12M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #2 GS-W11-henry-hub-surge-ny-basis-6d (gas_supply, winter, 6 days)

**Narrative.** A continental gas price surge lifts Henry Hub 80% over six days as storage drawdowns and pipeline outages hit the national market. The Z6 NY gas basis widens by 10 $/MWh, which raises the effective gas cost used by the heat-rate call P4 and lowers its payoff. The N.Y.C. minus WEST spread widens by 260 $/MWh because gas-fired pocket units set the marginal price in the city while upstate hydro and nuclear limit the WEST move. Winter load runs 10% above a typical day. WEST on-peak prices are not moved separately, so the long WEST swap P1 gains little. The loss accumulates across the six days, dominated by the short N.Y.C. retail obligation P5 and the gas-linked loss on P4, with P2 offsetting part of the spread loss. The scenario tests a broad gas-price shock combined with a sustained pocket spread.

**Shock vector (non-neutral).** `{"gas_hh_pct": 80.0, "ny_gas_basis_usd": 10.0, "load_peak_ratio": 1.1, "pocket_minus_ref_usd": 260.0, "duration_days": 6}`

**Loss** 5.02M (Claude stated 5.20M)  
**Plausibility.** D2 94.2, rank q 0.035, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 1.0, "l": 1.0, "s": 0.06, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.48M | P2 +0.94M | P3 +0.00M | P4 -0.04M | P5 -6.38M | P6 -0.02M  
**P&L by channel.** system +0.48M | congestion +0.94M | dart +0.00M | gas -0.04M | zone_volume -6.38M | tail -0.02M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #3 GS-W8-pocket-spread-10d-rt-premium (gas_supply, winter, 10 days)

**Narrative.** A ten-day gas supply tightness into N.Y.C. keeps the N.Y.C. minus WEST spread wide at 300 $/MWh on every shocked day. Scarce pocket gas forces the city to rely on expensive real-time balancing, so real-time on-peak prices clear 60% above day-ahead, which hurts the day-ahead-minus-real-time receipt in P3. Henry Hub rises 20% and the Z6 NY gas basis adds 2 $/MWh, a modest move that mainly lowers the heat-rate call P4. Load runs 10% above a typical winter day, increasing the size of the short retail obligation P5. The loss accumulates over the full ten days, so duration matters as well as magnitude, and the long WEST swap P1 gains only slightly from the higher gas-linked WEST price. This scenario combines a persistent pocket spread with a real-time premium, a channel not used in the earlier scenarios.

**Shock vector (non-neutral).** `{"gas_hh_pct": 20.0, "ny_gas_basis_usd": 2.0, "load_peak_ratio": 1.1, "pocket_minus_ref_usd": 300.0, "dart_pct": 60.0, "duration_days": 10}`

**Loss** 9.22M (Claude stated 6.00M)  
**Plausibility.** D2 102.9, rank q 0.027, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.96, "l": 1.0, "s": 0.63, "c": 1.0, "d": 0.57}  
**P&L by position.** P1 +0.94M | P2 +1.80M | P3 -0.37M | P4 +0.34M | P5 -11.87M | P6 -0.05M  
**P&L by channel.** system +0.94M | congestion +1.80M | dart -0.37M | gas +0.34M | zone_volume -11.87M | tail -0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #4 GS-W1-NYC-gas-squeeze (gas_supply, winter, 6 days)

**Narrative.** A cold pipeline outage cuts firm gas deliveries into N.Y.C. (Zone J). Henry Hub rises 60% on the shocked days as heating demand exhausts storage. Z6 NY gas becomes scarce, so pocket generators with gas-fired capacity set prices at the margin, while WEST, supplied by upstate hydro and nuclear, rises much less. The N.Y.C. minus WEST spread widens by 325 $/MWh. Load runs 10% above a typical winter day. The short N.Y.C. retail obligation P5 is the dominant loss, partly offset by long WEST P1, the N.Y.C.-WEST spread P2 and the heat-rate call P4. The shock lasts six days.

**Shock vector (non-neutral).** `{"gas_hh_pct": 60.0, "ny_gas_basis_usd": 3.0, "load_peak_ratio": 1.1, "pocket_minus_ref_usd": 325.0, "duration_days": 6}`

**Loss** 6.34M (Claude stated 5.90M)  
**Plausibility.** D2 115.4, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.98, "l": 1.0, "s": 0.18, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.40M | P2 +1.17M | P3 +0.00M | P4 +0.04M | P5 -7.94M | P6 -0.02M  
**P&L by channel.** system +0.40M | congestion +1.17M | dart +0.00M | gas +0.04M | zone_volume -7.94M | tail -0.02M  
**Analogue.** Winter Storm Elliott (NYISO) 23 Dec; **confidence** medium; **soft penalty** 0.0

### #5 WIN_CS_11_five_day_rt_scarcity_spread (cold_snap, winter, 5 days)

**Narrative.** A five-day cold snap combines a 320 $/MWh widening of the N.Y.C. minus WEST spread with a load run about 10% above a typical winter day. Upstate supply tightens as well, so WEST on-peak prices ease about 30% while real-time clears about 30% above day-ahead on the same days. The rise in real-time over day-ahead hurts the DART position (P3), and the WEST decline trims the long swap (P1). The spread widening remains the dominant loss, because it drives the short retail obligation (P5) and the long spread position (P2) offsets only part of it. The spread of 320 $/MWh stays within the 30% tolerance of the Elliott analogue spread of 338.5 $/MWh.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.1, "ref_onpeak_pct": -30.0, "pocket_minus_ref_usd": 320.0, "dart_pct": 30.0, "duration_days": 5}`

**Loss** 5.61M (Claude stated 5.30M)  
**Plausibility.** D2 120.3, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.73, "l": 1.0, "s": 0.33, "c": 1.0, "d": 0.28}  
**P&L by position.** P1 +0.06M | P2 +0.96M | P3 -0.06M | P4 +0.03M | P5 -6.60M | P6 +0.00M  
**P&L by channel.** system +0.06M | congestion +0.96M | dart -0.06M | gas +0.03M | zone_volume -6.60M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #6 WIN_CS_04_pocket_congestion_only (cold_snap, winter, 5 days)

**Narrative.** A five-day winter cold snap pushes N.Y.C. load about 10% above a typical winter day while import and Southeast-to-N.Y.C. transmission limits bind. The N.Y.C. minus WEST spread widens by 330 $/MWh, just under the Winter Storm Elliott analogue spread of 338.5 $/MWh, so the shock stays close to a documented event. WEST on-peak prices and gas are held at neutral levels, so the loss comes from congestion and zone volume alone. The short 140 MW retail obligation (P5) loses on the widened spread and on the extra volume from higher load. The long 25 MW spread position (P2) offsets only part of that loss.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.1, "pocket_minus_ref_usd": 330.0, "duration_days": 5}`

**Loss** 5.65M (Claude stated 5.60M)  
**Plausibility.** D2 120.4, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.73, "l": 1.0, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.11M | P2 +0.99M | P3 +0.00M | P4 +0.05M | P5 -6.80M | P6 +0.00M  
**P&L by channel.** system +0.11M | congestion +0.99M | dart +0.00M | gas +0.05M | zone_volume -6.80M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) 23 Dec; **confidence** medium; **soft penalty** 1.0

### #7 CS-W2-spread-dart-5d (cold_snap, winter, 5 days)

**Narrative.** A short, sharp cold snap pushes N.Y.C. into a severe local shortage, widening the N.Y.C. minus WEST spread by $320/MWh over 5 days, while real-time upstate prices settle 40% below day-ahead as the day-ahead market over-commits WEST supply. The spread shock dominates the loss through the 140 MW retail obligation (P5). The DART move hurts the long WEST swap (P1) and the heat-rate call (P4), while the short-real-time premium gain on P3 offsets only part of it. The WEST on-peak price is cut 40% against the unshocked path, which removes some of P1 and P4 value. The combined engine-style estimate is roughly $5.3M, with low precision because the sensitivities are not additive.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.05, "ref_onpeak_pct": -40, "pocket_minus_ref_usd": 320, "dart_pct": -40, "duration_days": 5}`

**Loss** 5.53M (Claude stated 5.30M)  
**Plausibility.** D2 127.7, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.73, "l": 1.0, "s": 0.02, "c": 1.0, "d": 0.02}  
**P&L by position.** P1 -0.25M | P2 +0.96M | P3 +0.06M | P4 -0.05M | P5 -6.25M | P6 +0.00M  
**P&L by channel.** system -0.25M | congestion +0.96M | dart +0.06M | gas -0.05M | zone_volume -6.25M | tail +0.00M  
**Analogue.** Polar vortex January 2014 (NYISO) 6 Jan; **confidence** low; **soft penalty** 0.0

### #8 GS-W-05-CityGateCongestionShock (gas_supply, winter, 6 days)

**Narrative.** A transmission and pipeline constraint into the Hudson Valley and N.Y.C. during a deep winter cold event strands the cheapest upstate gas and caps supply into the pocket. Henry Hub and WEST are unchanged, so the shock is pure congestion and zone volume. The N.Y.C. minus WEST spread widens by $350/MWh on each of six shocked days, close to the Winter Storm Elliott real-time spread of $338.5/MWh. Load is held at normal, so the loss comes entirely from the short N.Y.C. retail position P5, which is hedged only with a WEST long that does not move. P2 gains on the widened spread and partly offsets. P1, P3 and P4 are essentially neutral because no WEST, gas or real-time shock is applied. This scenario is the cleanest test of the congestion channel, and the six-day duration matches a single multi-day constraint event.

**Shock vector (non-neutral).** `{"pocket_minus_ref_usd": 350.0, "duration_days": 6}`

**Loss** 6.40M (Claude stated 6.20M)  
**Plausibility.** D2 133.2, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.73, "l": 0.98, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.00M | P2 +1.26M | P3 +0.00M | P4 +0.00M | P5 -7.66M | P6 +0.00M  
**P&L by channel.** system +0.00M | congestion +1.26M | dart +0.00M | gas +0.00M | zone_volume -7.66M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) 2022-12-23 to 2022-12-24; **confidence** low; **soft penalty** 1.0

### #9 LLS-SUM-F-30d-gas-dart-spread-grind (large_load_shortfall, summer, 30 days)

**Narrative.** A slower-than-forecast large-load ramp (-900 MW, in the Gold Book 2030 shortfall range) lowers summer peak load to 97% of normal (load_peak_ratio 0.97). Gas falls 40% (gas_hh_pct -40) as weaker power burn reduces gas demand, which lowers the WEST on-peak level and the P4 heat-rate call payoff. Real-time clears 40% below day-ahead (dart_pct -40) across 30 days, which costs the long WEST positions P1 and P4 on the DART leg, and WEST on-peak is 25% lower on top of these moves (ref_onpeak_pct -25). The N.Y.C. minus WEST spread widens by 35 $/MWh (pocket_minus_ref_usd +35), which is inside the summer historical range and drives the short retail position P5. The combined gas, DART and WEST moves are assumed to overlap, so the estimate is discounted slightly. The estimate is about $5.4M, built from linearly scaled 5-day sensitivities and not additive. Gas and DART stay inside the summer implausibility ceilings. No analogue fits this combination, so confidence is low.

**Shock vector (non-neutral).** `{"gas_hh_pct": -40, "load_peak_ratio": 0.97, "large_load_shock_mw": -900, "ref_onpeak_pct": -25, "pocket_minus_ref_usd": 35, "dart_pct": -40, "duration_days": 30}`

**Loss** 5.21M (Claude stated 5.40M)  
**Plausibility.** D2 136.8, rank q 0.020, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.13, "l": 0.55, "s": 0.9, "c": 1.0, "d": 0.96}  
**P&L by position.** P1 -2.02M | P2 +0.63M | P3 +0.19M | P4 -0.75M | P5 -3.30M | P6 +0.05M  
**P&L by channel.** system -2.02M | congestion +0.63M | dart +0.19M | gas -0.75M | zone_volume -3.30M | tail +0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #10 GS-W-02-CityGateBasisSpread (gas_supply, winter, 6 days)

**Narrative.** A pipeline capacity constraint into New York City raises the Zone J city-gate gas basis by $25/MMBtu over Henry Hub for six days, while Henry Hub itself is unchanged. The NYC gas-fired heat rate rises and the N.Y.C. minus WEST spread widens by $300/MWh on each shocked day. This isolates the congestion and zone-volume channel without a national gas rally. P4 loses its heat-rate intrinsic because its gas cost rises by 8 x $25 = $200/MWh, so its payoff is largely extinguished, which costs only modestly. P5 is short N.Y.C. load and loses on the widened spread; P2 partly offsets. WEST prices are unchanged, so P1 is neutral. Duration is 6 days, extrapolated linearly from the 5-day winter sensitivity table, which is an assumption.

**Shock vector (non-neutral).** `{"ny_gas_basis_usd": 25.0, "pocket_minus_ref_usd": 300.0, "duration_days": 6}`

**Loss** 5.56M (Claude stated 5.60M)  
**Plausibility.** D2 139.4, rank q 0.020, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 1.0, "l": 0.98, "s": 0.0, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.00M | P2 +1.08M | P3 +0.00M | P4 -0.07M | P5 -6.57M | P6 +0.00M  
**P&L by channel.** system +0.00M | congestion +1.08M | dart +0.00M | gas -0.07M | zone_volume -6.57M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) 2022-12-23 to 2022-12-24; **confidence** low; **soft penalty** 0.0

## Excluded scenarios and why

| scenario | loss (M) | reason |
|---|---|---|
| CS-W1-congestion-10d | 6.48 | ordinary world (q=0.086 >= 0.05), not a tail event |
| CS-W3-gas-basis-15d | 6.16 | implausible: marginal beyond T |
| CS-W4-pocket-spread-7d | 6.05 | implausible: marginal beyond T |
| CS-W5-persistent-spread-20d | 3.68 | loss 3.68M below target |
| CS-W6-dart-spread-12d | 5.03 | implausible: marginal beyond T |
| CS-W7-west-down-pocket-up-9d | 6.37 | implausible: marginal beyond T |
| CS-W8-long-moderate-spread-14d | 5.68 | implausible: marginal beyond T |
| CS-W9-rt-spike-spread-6d | 3.40 | loss 3.40M below target |
| GS-BASIS-20D-SPREAD120 | 6.88 | ordinary world (q=0.122 >= 0.05), not a tail event |
| GS-CONG-10D-SPREAD200-BASIS | 5.93 | ordinary world (q=0.082 >= 0.05), not a tail event |
| GS-CONG-5D-SPREAD400 | 6.09 | implausible: marginal beyond c |
| GS-SPREAD200-LOAD125-12D | 8.24 | implausible: marginal beyond T |
| GS-SPREAD430-4D-ELLIOTT | 5.26 | implausible: marginal beyond c |
| GS-W-01-PocketGasSqueeze | 5.73 | ordinary world (q=0.075 >= 0.05), not a tail event |
| GS-W-01-pocket-sustained-30d | 1.71 | loss 1.71M below target |
| GS-W-02-pocket-spike-10d | 4.66 | loss 4.66M below target |
| GS-W-03-WestGlutPocketShortage | 6.33 | implausible: marginal beyond c |
| GS-W-03-nyc-gas-basis-squeeze | 4.14 | loss 4.14M below target |
| GS-W-04-SustainedPocketSpreadLoad | 5.39 | ordinary world (q=0.153 >= 0.05), not a tail event |
| GS-W-04-pocket-spread-westdown-30d | 6.67 | ordinary world (q=0.235 >= 0.05), not a tail event |
| GS-W-05-pocket-spread-load-10d | 5.33 | ordinary world (q=0.129 >= 0.05), not a tail event |
| GS-W-06-ColdLoadGasBasisSqueeze | 5.17 | implausible: marginal beyond T |
| GS-W-06-gas-decline-dart-spread-20d | n/a | rejected before the engine: sign_consistent |
| GS-W-07-SlowLNGPocketDrawdown | 6.15 | ordinary world (q=0.129 >= 0.05), not a tail event |
| GS-W-08-RealTimeGasSpikeSpread | 4.72 | loss 4.72M below target |
| GS-W-09-ColdLoadPocketGasBasisPeak | 6.22 | implausible: marginal beyond T |
| GS-W-10-ExtendedGasCapacityDeficit | 5.29 | implausible: marginal beyond T |
| GS-W-11-RealTimeDislocationPocket | 4.98 | loss 4.98M below target |
| GS-W-12-ColdPeakBasisCompound | 4.16 | loss 4.16M below target |
| GS-W-CONSTRAINT-12D | 5.37 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-W-DECOUPLE-14D | 7.60 | ordinary world (q=0.125 >= 0.05), not a tail event |
| GS-W-DRIFT-30D | 8.05 | implausible: marginal beyond T |
| GS-W-PIPE-10D | 7.76 | implausible: marginal beyond T |
| GS-W-POCKET-9D | 5.04 | ordinary world (q=0.125 >= 0.05), not a tail event |
| GS-W-RTSQUEEZE-12D | 1.79 | loss 1.79M below target |
| GS-W10-pocket-spread-8d-load-peak | 6.21 | implausible: marginal beyond T |
| GS-W12-intense-pocket-rt-premium-4d | 5.15 | implausible: marginal beyond T |
| GS-W13-ny-gas-basis-blowout-6d | 4.96 | loss 4.96M below target |
| GS-W14-moderate-spread-18d-mild-gas | 7.49 | implausible: marginal beyond T |
| GS-W15-two-day-pocket-rt-shock | 3.13 | loss 3.13M below target |
| GS-W16-gas-rally-pocket-basis-9d | 5.38 | ordinary world (q=0.102 >= 0.05), not a tail event |
| GS-W17-rt-imbalance-long-moderate-14d | 4.49 | loss 4.49M below target |
| GS-W3-prolonged-gas-tightness | 6.80 | ordinary world (q=0.114 >= 0.05), not a tail event |
| GS-W4-NYC-pocket-spike-4d | 5.71 | implausible: marginal beyond c |
| GS-W5-load-led-pocket-7d | 5.82 | implausible: marginal beyond T |
| GS-W6-extended-pocket-bleed-25d | 4.93 | loss 4.93M below target |
| GS-W7-pocket-spread-3d-high-load | 3.54 | loss 3.54M below target |
| GS-W9-load-peak-5d-rt-spike | 4.26 | loss 4.26M below target |
| GS-WEST-SOFT-SPREAD250-8D | 6.14 | ordinary world (q=0.051 >= 0.05), not a tail event |
| HW-CONCENTRATED-POCKET-14D | 6.10 | implausible: marginal beyond c |
| HW-CONG-10D-220 | 6.34 | implausible: marginal beyond c |
| HW-FCST-BUST-20D | 6.25 | implausible: marginal beyond c |
| HW-GAS-BASIS-SPREAD-30D | 4.79 | loss 4.79M below target |
| HW-GAS-BASIS-STRESS-30D | 5.00 | loss 5.00M below target |
| HW-LONG-LOW-SPREAD-25D | 5.35 | implausible: marginal beyond T, c |
| HW-PROLONGED-POCKET-20D | 6.72 | implausible: marginal beyond c |
| HW-S1-pocket-spread-10d | 4.50 | loss 4.50M below target |
| HW-S1-sustained-NYC-congestion-30d | 8.55 | implausible: marginal beyond c |
| HW-S2-short-extreme-pocket-spread-10d | 8.02 | implausible: marginal beyond T, c |
| HW-S2-sustained-soft-west-30d | 5.33 | implausible: marginal beyond T |
| HW-S3-extreme-pocket-5d | 4.50 | loss 4.50M below target |
| HW-S4-nyc-transmission-constraint-120usd-18d | 6.16 | implausible: marginal beyond c |
| HW-S4-pocket-spread-7d-load1.4 | 5.11 | implausible: marginal beyond T, c |
| HW-S5-prolonged-moderate-spread-18d | 4.80 | loss 4.80M below target |
| HW-S5-rt-below-da-dart-plus-spread-30d | 6.35 | implausible: marginal beyond d |
| HW-S6-realtime-premium-pocket-8d | 3.66 | loss 3.66M below target |
| HW-S6-upstate-surplus-west-collapse-spread-20d | 6.35 | implausible: marginal beyond c |
| HW-S7-nyc-spread-100-dart-neg30-20d | 6.20 | implausible: marginal beyond c |
| HW-S8-gas-basis-15-dart-neg60-30d | 5.34 | implausible: marginal beyond g, s |
| HW-S9-west-collapse-spread-130-dart-neg50-14d | 6.13 | implausible: marginal beyond c |
| HW-SHARP-DOME-12D | 7.13 | implausible: marginal beyond c |
| HW-SPREAD-280-7D | 5.46 | implausible: marginal beyond c |
| HW-SPREAD-EXTREME-335-6D | 5.61 | implausible: marginal beyond c |
| HW-SPREAD-GASDROP-150-14D | 6.41 | implausible: marginal beyond c |
| HW-SUS-SPREAD-30D | 7.63 | implausible: marginal beyond c |
| HW-WEST-DROP-DART-15D | 6.10 | implausible: marginal beyond c |
| HW-WEST-SLUMP-SPREAD-200-10D | 6.15 | implausible: marginal beyond c |
| LLS-CONG-10D-03 | 5.33 | implausible: marginal beyond c |
| LLS-DART-CONG-07 | 5.88 | implausible: marginal beyond c |
| LLS-MIX-SHORT-06 | 2.26 | loss 2.26M below target |
| LLS-RT-CONG-10 | 4.16 | loss 4.16M below target |
| LLS-SUM-01-RT-GLUT | 4.52 | loss 4.52M below target |
| LLS-SUM-01-pocket-spread-10d | 5.55 | implausible: marginal beyond c |
| LLS-SUM-02-pocket-spread-max-8d | 6.10 | implausible: marginal beyond c |
| LLS-SUM-02-spread-dominant | 10.94 | implausible: marginal beyond c |
| LLS-SUM-03-GAS-DART | 4.52 | loss 4.52M below target |
| LLS-SUM-03-west-collapse | 7.37 | implausible: marginal beyond s |
| LLS-SUM-03-west-system-30d | 3.21 | loss 3.21M below target |
| LLS-SUM-04-SPREAD-WEST-SLUMP | 13.90 | implausible: marginal beyond c |
| LLS-SUM-04-pocket-spread-13d | 5.68 | implausible: marginal beyond c |
| LLS-SUM-04-sustained-spread-deficit | 9.08 | implausible: marginal beyond c |
| LLS-SUM-05-RT-PREMIUM-SHORT-EVENT | 2.84 | loss 2.84M below target |
| LLS-SUM-05-mid-window-congestion-squeeze | 6.20 | implausible: marginal beyond c |
| LLS-SUM-05-west-down-spread-13d | 5.59 | implausible: marginal beyond c |
| LLS-SUM-06-DEEP-LOAD-SHORTFALL-CONGESTION | 7.41 | implausible: marginal beyond T, c, d |
| LLS-SUM-06-flat-west-congestion-only | 5.57 | implausible: marginal beyond c |
| LLS-SUM-06-spread-dart-20d | 4.66 | loss 4.66M below target |
| LLS-SUM-07-NYC-SPREAD-LOAD-LAG | 5.63 | implausible: marginal beyond c, d |
| LLS-SUM-07-sustained-spread-120 | 7.43 | implausible: marginal beyond c |
| LLS-SUM-08-GAS-WEST-SQUEEZE | 2.73 | loss 2.73M below target |
| LLS-SUM-08-low-end-shortfall-spread-150 | 6.43 | implausible: marginal beyond c |
| LLS-SUM-09-NYC-BASIS-SHORT-WINDOW | 0.90 | loss 0.90M below target |
| LLS-SUM-09-short-intense-spread-with-dart | 5.35 | implausible: marginal beyond c, d |
| LLS-SUM-A-30d-spread-grind | 6.97 | implausible: marginal beyond c |
| LLS-SUM-B-10d-pocket-blowout | 5.43 | implausible: marginal beyond c |
| LLS-SUM-E-15d-gas-led-spread-blowout | 5.27 | implausible: marginal beyond c |
| LLS-SUM-G-12d-pocket-spread-constraint | 5.95 | implausible: marginal beyond c |
| LLS-SUM-H-20d-west-price-collapse-spread | 5.56 | implausible: marginal beyond c |
| LLS-SUM-I-30d-slow-load-rt-drift-spread | 5.08 | implausible: marginal beyond T, d, s |
| LLS-SUM-J-25d-pocket-spread-load-trough | 7.26 | implausible: marginal beyond T, c |
| LLS-SUM-K-15d-day-ahead-overforecast-dart-collapse | 4.63 | loss 4.63M below target |
| LLS-SUM-L-30d-gas-retreat-west-slump | 7.55 | implausible: marginal beyond T |
| LLS-SYS-30D-01 | 3.15 | loss 3.15M below target |
| LLS-SYS-DEEP-04 | 6.24 | implausible: marginal beyond s |
| LLS-WEST-GLUT-08 | 5.18 | implausible: marginal beyond s |
| LLS-ZJ-CONG-05 | 7.08 | implausible: marginal beyond c |
| WIN-CS-02-pocket-spread-8d | 6.03 | ordinary world (q=0.055 >= 0.05), not a tail event |
| WIN-CS-03-spread-dart-load-10d | 4.16 | loss 4.16M below target |
| WIN-CS-04-short-spread-shock-4d | 4.84 | loss 4.84M below target |
| WIN_CS_01_pocket_spread_blowout | 6.17 | implausible: marginal beyond c |
| WIN_CS_02_load_spread_west_weak | 6.97 | implausible: marginal beyond T |
| WIN_CS_03_gas_basis_west_collapse | 5.06 | implausible: marginal beyond s |
| WIN_CS_05_west_oversupply_rt_below_da | 5.91 | implausible: marginal beyond T |
| WIN_CS_06_prolonged_pocket_squeeze | 5.49 | ordinary world (q=0.129 >= 0.05), not a tail event |
| WIN_CS_07_seven_day_pocket_squeeze | 5.69 | ordinary world (q=0.055 >= 0.05), not a tail event |
| WIN_CS_08_six_day_west_softening | 5.86 | implausible: marginal beyond T |
| WIN_CS_09_four_day_elliott_spread | 5.44 | implausible: marginal beyond T |
| WIN_CS_10_fourteen_day_pocket_grind | 5.74 | ordinary world (q=0.161 >= 0.05), not a tail event |
| WIN_CS_12_six_day_load_pocket_stack | 5.84 | implausible: marginal beyond T |
| WIN_CS_13_three_day_peak_scarcity | 3.78 | loss 3.78M below target |
| WIN_CS_14_nine_day_moderate_pocket_drain | 5.63 | ordinary world (q=0.098 >= 0.05), not a tail event |
| WIN_CS_15_four_day_gas_spread_stack | 4.42 | loss 4.42M below target |
| WIN_CS_16_twelve_day_moderate_grind | 5.69 | ordinary world (q=0.153 >= 0.05), not a tail event |
| WIN_CS_17_eight_day_load_heavy_west_soft | 5.33 | implausible: marginal beyond T |
| WIN_CS_18_eleven_day_rt_premium_gas_lift | 5.17 | ordinary world (q=0.145 >= 0.05), not a tail event |
| cold_snap_extreme_pocket_spread_10d | 7.93 | implausible: marginal beyond T |
| cold_snap_pocket_import_constraint_14d | 6.25 | ordinary world (q=0.153 >= 0.05), not a tail event |
| cold_snap_west_price_collapse_pocket_squeeze_14d | 5.82 | ordinary world (q=0.157 >= 0.05), not a tail event |
| heat_wave_extended_rt_premium_15d | 3.50 | loss 3.50M below target |
| heat_wave_gas_slack_rt_premium_12d | 5.43 | implausible: marginal beyond c, d, s |
| heat_wave_nyc_spread_10d | 6.30 | implausible: marginal beyond T, c |
| heat_wave_persistent_pocket_20d | 6.32 | implausible: marginal beyond c |
| heat_wave_pocket_spread_12d | 6.56 | implausible: marginal beyond c |
| heat_wave_short_intense_pocket_6d | 5.41 | implausible: marginal beyond T, c |
| winter_cold_snap_rt_premium_spread_30d | 4.11 | loss 4.11M below target |
| winter_cold_snap_rt_spread_surge_20d | 10.18 | implausible: marginal beyond T |
| winter_cold_snap_west_price_collapse_spread_30d | 5.60 | ordinary world (q=0.259 >= 0.05), not a tail event |
