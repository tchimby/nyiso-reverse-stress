# Ranked reverse-stress scenarios (NYISO book)

Source logs: live_haiku_r1, live_haiku_s1, live_haiku_s2, live_haiku_s3, live_haiku_s4. Models: claude-haiku-5-5. Client kinds: live.  
Target loss 5.0M. Scenarios read: 219; ranked (eligible): 41; excluded: 178.  
q is a rank against about 250 non-overlapping 10-day windows of 2019-2025, not a probability; fit window 2019-2025; daily averaging understates hourly spikes. A client kind other than the live API means scripted output, not Claude results.  
Largest-loss channel across ranked scenarios: {"zone_volume": 41} (one channel for all of them means the book, not the search, limits diversity).

Coherence grading by a human: [PENDING]. Scenarios are drafts for a risk manager to accept or hedge, not forecasts.

## Ranked scenarios (most plausible first)

### #1 CS-WIN-09-west-drop-pocket-widening (cold_snap, winter, 7 days)

**Narrative.** A seven-day cold snap in which upstate WEST on-peak prices fall 60% relative to what gas and load imply, because upstate hydro and wind keep supply long while N.Y.C. stays tight. The spread widens by 230 $/MWh, and load runs 10% above normal, which raises the size of the N.Y.C. exposure in P5. The lower WEST level reduces the value of the long WEST swap P1 and the heat-rate call P4, adding to the loss from the spread. Gas is flat and dart is zero, since the event is supply and transmission driven rather than fuel driven. There are no spike days, and the large-load shock is zero.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.1, "ref_onpeak_pct": -60.0, "pocket_minus_ref_usd": 230.0, "duration_days": 7}`

**Loss** 5.87M (Claude stated 5.70M)  
**Plausibility.** D2 89.9, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.73, "l": 1.0, "s": 0.03, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 -0.27M | P2 +0.97M | P3 +0.00M | P4 -0.07M | P5 -6.50M | P6 +0.00M  
**P&L by channel.** system -0.27M | congestion +0.97M | dart +0.00M | gas -0.07M | zone_volume -6.50M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #2 CS-W-13-deep-spread-seven-days (cold_snap, winter, 7 days)

**Narrative.** A seven-day winter cold outbreak lifts N.Y.C. on-peak load about 8% above a typical day while Central East and Hudson Valley transfer limits bind on every shocked day. The N.Y.C. minus WEST spread widens by $260/MWh, which makes the short N.Y.C. retail obligation P5 the dominant loss channel, roughly -$7.0M gross. P2 offsets part of that through its long spread position. Gas is held flat, so WEST gets no gas-driven lift. WEST on-peak falls 30% beyond the implied path because upstate generation is stranded behind the constraint, which also weakens the WEST hedge inside P5. No DART gap or spike is imposed, so the loss comes from a deep spread widening over a moderate-length episode.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.08, "ref_onpeak_pct": -30.0, "pocket_minus_ref_usd": 260.0, "duration_days": 7}`

**Loss** 6.20M (Claude stated 5.50M)  
**Plausibility.** D2 90.3, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.73, "l": 1.0, "s": 0.14, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 -0.08M | P2 +1.09M | P3 +0.00M | P4 -0.03M | P5 -7.18M | P6 +0.00M  
**P&L by channel.** system -0.08M | congestion +1.09M | dart +0.00M | gas -0.03M | zone_volume -7.18M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #3 GS-W-10-upstate-decouple-pipeline-8d (gas_supply, winter, 8 days)

**Narrative.** A winter gas-supply event decouples the pocket from upstate. Pipeline capacity into N.Y.C. binds while upstate Marcellus supply stays ample, so Henry Hub rises 35% and the delivered basis for P4's heat-rate call rises 5 USD/MMBtu, which lowers P4's payoff. The N.Y.C. minus WEST spread widens by 260 USD/MWh per day for eight days, which is the main loss channel because it hits the 140 MW short retail obligation in P5 at full size. WEST on-peak prices fall 15% beyond the gas-implied level because upstate gas is oversupplied, which reduces the value of the long WEST swap P1 and the heat-rate call P4. Load is held at 1.00 to isolate the pipeline channel. No DART or spike shock is applied.

**Shock vector (non-neutral).** `{"gas_hh_pct": 35.0, "ny_gas_basis_usd": 5.0, "ref_onpeak_pct": -15.0, "pocket_minus_ref_usd": 260.0, "duration_days": 8}`

**Loss** 6.20M (Claude stated 6.00M)  
**Plausibility.** D2 90.3, rank q 0.047, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.99, "l": 0.98, "s": 0.06, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.02M | P2 +1.25M | P3 -0.01M | P4 -0.07M | P5 -7.40M | P6 +0.00M  
**P&L by channel.** system +0.02M | congestion +1.25M | dart -0.01M | gas -0.07M | zone_volume -7.40M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #4 CS-WIN-15-real-time-spike-pocket-gas (cold_snap, winter, 6 days)

**Narrative.** A six-day cold snap combines a 280 $/MWh widening of the N.Y.C. minus WEST spread with real-time clearing 60% above day-ahead on the shocked days. The real-time premium hurts the WEST off-peak DART position P3 and the daily WEST on-peak average exposure in P6, while the spread and 10% load excess drive the main loss on the short N.Y.C. obligation P5. Henry Hub gas rises 20% on the same tightness, which lowers the heat-rate call P4 payoff. WEST on-peak is held at base and there are no spike days, so the scenario tests real-time exposure rather than an extreme price level. The large-load shock is zero because the event is weather-driven.

**Shock vector (non-neutral).** `{"gas_hh_pct": 20.0, "load_peak_ratio": 1.1, "pocket_minus_ref_usd": 280.0, "dart_pct": 60.0, "duration_days": 6}`

**Loss** 5.06M (Claude stated 5.80M)  
**Plausibility.** D2 92.6, rank q 0.043, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.87, "l": 1.0, "s": 0.8, "c": 1.0, "d": 0.57}  
**P&L by position.** P1 +0.70M | P2 +1.01M | P3 -0.18M | P4 +0.32M | P5 -6.86M | P6 -0.05M  
**P&L by channel.** system +0.70M | congestion +1.01M | dart -0.18M | gas +0.32M | zone_volume -6.86M | tail -0.05M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #5 GS-3-upstate-glut-NYC-squeeze (gas_supply, winter, 8 days)

**Narrative.** Upstate gas is oversupplied and sells into WEST at a deep discount, while N.Y.C. remains short of firm gas and sets a high marginal price. Over 8 days WEST on-peak prices fall 60% and the N.Y.C. minus WEST spread widens by 250 $/MWh, close to the Winter Storm Elliott real-time spread. Henry Hub rises 10% on the gas-supply disruption. The long WEST swap P1 loses most of its value, P4 loses its payoff, and the short N.Y.C. retail load P5 takes a large loss from the spread, partly offset by P2. The shock is intense but short, and it relies on a sharp WEST price collapse as well as the spread.

**Shock vector (non-neutral).** `{"gas_hh_pct": 10.0, "ref_onpeak_pct": -60.0, "pocket_minus_ref_usd": 250.0, "duration_days": 8}`

**Loss** 6.29M (Claude stated 6.67M)  
**Plausibility.** D2 94.0, rank q 0.035, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.81, "l": 0.98, "s": 0.03, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 -0.31M | P2 +1.20M | P3 +0.01M | P4 -0.07M | P5 -7.12M | P6 +0.00M  
**P&L by channel.** system -0.31M | congestion +1.20M | dart +0.01M | gas -0.07M | zone_volume -7.12M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) 23 Dec (year not stated in table); **confidence** medium; **soft penalty** 0.0

### #6 WIN-WEST-DEPRESSED-POCKET-6D (cold_snap, winter, 6 days)

**Narrative.** A six-day winter cold snap in which upstate WEST on-peak prices fall 35 percent below their unshocked path, because upstate units are curtailed and cannot export into a pocket that is itself import-constrained. The N.Y.C. minus WEST spread widens by 270 $/MWh on each day. The lower WEST price reduces the value of the 100 MW long P1 swap and the 50 MW P4 heat-rate call, and the wide spread drives the short P5 retail obligation. Gas and load stay at normal to keep the mix distinct from the earlier load-driven scenarios. The WEST move is well inside the winter historical bounds but has no analogue match, so confidence is low.

**Shock vector (non-neutral).** `{"ref_onpeak_pct": -35.0, "pocket_minus_ref_usd": 270.0, "duration_days": 6}`

**Loss** 5.19M (Claude stated 5.60M)  
**Plausibility.** D2 95.3, rank q 0.035, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.73, "l": 0.98, "s": 0.11, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 -0.19M | P2 +0.97M | P3 -0.00M | P4 -0.06M | P5 -5.91M | P6 +0.00M  
**P&L by channel.** system -0.19M | congestion +0.97M | dart -0.00M | gas -0.06M | zone_volume -5.91M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #7 WIN-GAS-BASIS-SQUEEZE-7D (cold_snap, winter, 7 days)

**Narrative.** A seven-day winter cold snap in which Henry Hub gas rises 40 percent and the N.Y.C. gas cost carries a 10 $/MMBtu basis premium over the Henry Hub index, so the pocket's marginal generation cost rises sharply. Pocket load reaches 1.10 times normal, and import limits keep the N.Y.C. minus WEST spread widened by 260 $/MWh each day. The short N.Y.C. retail obligation in P5 is the dominant loser. The gas basis lowers the P4 heat-rate payoff, which adds a small loss, while WEST on-peak and DART are held at their unshocked paths to isolate the zone-volume and gas-basis channels. No analogue is cited because no table entry matches a 260 $/MWh spread with this gas basis.

**Shock vector (non-neutral).** `{"gas_hh_pct": 40.0, "ny_gas_basis_usd": 10.0, "load_peak_ratio": 1.1, "pocket_minus_ref_usd": 260.0, "duration_days": 7}`

**Loss** 5.99M (Claude stated 5.60M)  
**Plausibility.** D2 95.7, rank q 0.035, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 1.0, "l": 1.0, "s": 0.05, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.32M | P2 +1.09M | P3 -0.01M | P4 -0.05M | P5 -7.33M | P6 -0.01M  
**P&L by channel.** system +0.32M | congestion +1.09M | dart -0.01M | gas -0.05M | zone_volume -7.33M | tail -0.01M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #8 CS-WIN-11-seven-day-real-time-squeeze (cold_snap, winter, 7 days)

**Narrative.** A seven-day cold snap keeps N.Y.C. import-constrained, so the N.Y.C. minus WEST spread widens by 250 $/MWh throughout the event. Real-time prices on the shocked days clear 70% below day-ahead, which penalises the WEST off-peak DART position P3 and creates a sustained wedge between day-ahead and real-time. Load runs 8% above a typical winter day, and WEST on-peak eases 10% relative to what gas and load imply as upstate supply stays long. Gas rises 5% on moderate Henry Hub tightness. There are no spike days and the large-load shock is zero because this is a weather-driven event.

**Shock vector (non-neutral).** `{"gas_hh_pct": 5.0, "load_peak_ratio": 1.08, "ref_onpeak_pct": -10.0, "pocket_minus_ref_usd": 250.0, "dart_pct": -70.0, "duration_days": 7}`

**Loss** 6.04M (Claude stated 5.50M)  
**Plausibility.** D2 98.0, rank q 0.035, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.78, "l": 1.0, "s": 0.01, "c": 1.0, "d": 0.0}  
**P&L by position.** P1 -0.36M | P2 +1.05M | P3 +0.25M | P4 -0.07M | P5 -6.91M | P6 +0.00M  
**P&L by channel.** system -0.36M | congestion +1.05M | dart +0.25M | gas -0.07M | zone_volume -6.91M | tail +0.00M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

### #9 GS-B-elliott-style-spread-7d (gas_supply, winter, 7 days)

**Narrative.** A short, sharp gas-supply shock: Henry Hub jumps 100 percent for 7 days after a pipeline outage, and N.Y.C. gas and generation are curtailed. The N.Y.C. minus WEST spread widens by 300 $/MWh on each of the 7 shocked days, which keeps the spread level inside the winter ceiling (implausible above 503.7) and near the Winter Storm Elliott real-time spread of 338.5 $/MWh. Because the N.Y.C. retail obligation is short at a fixed price, P5 takes most of the loss, while the gas rise gives P1 and P4 partial offsets. Load is held at normal and no large-load change applies, so this isolates the congestion-and-gas channel. Spikes and DART are neutral because the input's winter spike and DART gains would offset losses.

**Shock vector (non-neutral).** `{"gas_hh_pct": 100.0, "pocket_minus_ref_usd": 300.0, "duration_days": 7}`

**Loss** 5.96M (Claude stated 5.80M)  
**Plausibility.** D2 100.1, rank q 0.027, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.98, "l": 0.98, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.33M | P2 +1.26M | P3 -0.01M | P4 +0.04M | P5 -7.56M | P6 -0.01M  
**P&L by channel.** system +0.33M | congestion +1.26M | dart -0.01M | gas +0.04M | zone_volume -7.56M | tail -0.01M  
**Analogue.** Winter Storm Elliott (NYISO) 23 December (Winter Storm Elliott; year not stated in the analogue table); **confidence** medium; **soft penalty** 0.0

### #10 GS-W1-gas-pipeline-spread-blowout (gas_supply, winter, 7 days)

**Narrative.** A winter gas-supply shock: a pipeline constraint and a Henry Hub rally of 100% (gas_hh_pct) push up gas-fired marginal costs and strand firm gas supply into N.Y.C. The constraint is local to the pocket, so the N.Y.C. minus WEST spread widens by 300 $/MWh (pocket_minus_ref_usd) for 7 days. Load stays at a normal winter level (load_peak_ratio 1.0) and there are no spikes or RT/DA gaps. The book loses mainly through the 140 MW N.Y.C. retail short (P5), which is hedged only by a WEST long. P2 offsets part of the loss. Gas and WEST effects are small and partly offsetting. My estimate: P5 about -7.7M, P2 about +1.3M, net loss about 6.2M; this is a hand calculation from the summer/winter sensitivity table, not an engine run.

**Shock vector (non-neutral).** `{"gas_hh_pct": 100.0, "pocket_minus_ref_usd": 300.0, "duration_days": 7}`

**Loss** 5.96M (Claude stated 6.20M)  
**Plausibility.** D2 100.1, rank q 0.027, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.98, "l": 0.98, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.33M | P2 +1.26M | P3 -0.01M | P4 +0.04M | P5 -7.56M | P6 -0.01M  
**P&L by channel.** system +0.33M | congestion +1.26M | dart -0.01M | gas +0.04M | zone_volume -7.56M | tail -0.01M  
**Analogue.** Winter Storm Elliott (NYISO) 23Dec and 24Dec (year not stated in the analogue table); **confidence** medium; **soft penalty** 0.0

## Excluded scenarios and why

| scenario | loss (M) | reason |
|---|---|---|
| CS-W-01-congestion-spread | 6.12 | implausible: marginal beyond T |
| CS-W-01_sustained_zone_spread | 6.59 | implausible: marginal beyond T |
| CS-W-02-prolonged-load-congestion | 5.40 | implausible: marginal beyond T |
| CS-W-02_persistent_import_constraint | 7.32 | implausible: marginal beyond T |
| CS-W-03-gas-led-load-spread | 5.82 | implausible: marginal beyond T |
| CS-W-04-spread-moderate-load | 5.45 | ordinary world (q=0.078 >= 0.05), not a tail event |
| CS-W-05-no-gas-rt-premium | 4.85 | loss 4.85M below target |
| CS-W-05_extended_low_intensity_pocket_widening | 5.79 | implausible: marginal beyond T |
| CS-W-06_high_load_short_pocket_widening | 7.12 | implausible: marginal beyond T |
| CS-W-07-sustained-load-spread | 6.27 | implausible: marginal beyond T |
| CS-W-08_dart_reversal_with_pocket_spread | 4.80 | loss 4.80M below target |
| CS-W-09-spread-with-spike-day | 5.20 | implausible: marginal beyond T |
| CS-W-09_gas_shock_with_pocket_widening | 4.81 | loss 4.81M below target |
| CS-W-10-moderate-spread-nine-days | 5.31 | ordinary world (q=0.122 >= 0.05), not a tail event |
| CS-W-10_intense_pocket_spread_with_dart_spike | 4.88 | loss 4.88M below target |
| CS-W-11-double-spike-rt-gap | 1.97 | loss 1.97M below target |
| CS-W-11_moderate_spread_with_mild_load_over_12_days | 4.97 | loss 4.97M below target |
| CS-W-12-gas-basis-heat-rate-squeeze | 4.76 | loss 4.76M below target |
| CS-W-12_persistent_real_time_premium_with_pocket_spread | 0.86 | loss 0.86M below target |
| CS-W-13_long_load_led_pocket_widening | 6.41 | implausible: marginal beyond T |
| CS-W-14-extended-high-load-weak-spread | 7.25 | implausible: marginal beyond T |
| CS-W-15-spread-dart-spike-day | 3.15 | loss 3.15M below target |
| CS-W-15_fourteen_day_moderate_pocket_widening | 5.89 | ordinary world (q=0.161 >= 0.05), not a tail event |
| CS-W-16-short-sharp-gas-cost | 1.99 | loss 1.99M below target |
| CS-W-17-long-moderate-spread | 5.02 | ordinary world (q=0.188 >= 0.05), not a tail event |
| CS-W-18-spread-with-two-scarcity-days | -1.64 | loss -1.64M below target |
| CS-W-19-two-week-deep-weststrand | 7.72 | implausible: marginal beyond T |
| CS-W-20-three-day-extreme-spread | 4.13 | loss 4.13M below target |
| CS-W-21-eleven-day-gas-softening | n/a | rejected before the engine: sign_consistent |
| CS-W1-congestion-5d | 5.97 | implausible: marginal beyond T |
| CS-W2-west-weak-10d | 5.12 | ordinary world (q=0.137 >= 0.05), not a tail event |
| CS-W3-short-peak-4d | 5.54 | implausible: marginal beyond T |
| CS-W4-spread-10d-moderate | 5.27 | ordinary world (q=0.137 >= 0.05), not a tail event |
| CS-W5-dart-spread-14d | 3.51 | loss 3.51M below target |
| CS-W6-gas-spread-6d-sharp | 5.01 | implausible: marginal beyond T |
| CS-WIN-02-persistent-pocket-congestion | 5.39 | ordinary world (q=0.153 >= 0.05), not a tail event |
| CS-WIN-03-west-decoupling | 5.77 | ordinary world (q=0.078 >= 0.05), not a tail event |
| CS-WIN-04-sustained-pocket-spread | 7.07 | implausible: marginal beyond T |
| CS-WIN-05-long-cold-load-grind | 5.72 | implausible: marginal beyond T |
| CS-WIN-06-west-weak-dart-squeeze | 5.26 | ordinary world (q=0.051 >= 0.05), not a tail event |
| CS-WIN-07-short-pocket-spike-dart | 6.16 | implausible: marginal beyond T |
| CS-WIN-08-extended-moderate-pocket-squeeze | 5.11 | ordinary world (q=0.184 >= 0.05), not a tail event |
| CS-WIN-10-four-day-pocket-extreme | 6.23 | implausible: marginal beyond T, c |
| CS-WIN-12-moderate-spread-high-load-long | 6.70 | implausible: marginal beyond T |
| CS-WIN-13-three-day-extreme-pocket | 5.05 | implausible: marginal beyond c |
| CS-WIN-14-month-long-weak-west-grind | 5.11 | implausible: marginal beyond T |
| CS-WIN-16-spike-day-pocket-squeeze | 3.65 | loss 3.65M below target |
| CS-WIN-17-long-real-time-premium-pocket | 6.30 | implausible: marginal beyond T |
| GS-1-NYC-pipeline-congestion | 5.24 | ordinary world (q=0.129 >= 0.05), not a tail event |
| GS-2-NYC-gas-basis-spread | 7.08 | implausible: marginal beyond g |
| GS-4-NYC-sustained-spread-squeeze | 5.46 | ordinary world (q=0.051 >= 0.05), not a tail event |
| GS-5-NYC-gas-cost-basis-long-squeeze | 5.18 | implausible: marginal beyond g |
| GS-6-gas-constrained-realtime-premium | 4.02 | loss 4.02M below target |
| GS-7-NYC-gas-cold-load-squeeze | 5.73 | ordinary world (q=0.102 >= 0.05), not a tail event |
| GS-8-NYC-spread-with-upstate-realtime-premium | 3.95 | loss 3.95M below target |
| GS-9-NYC-slow-persistent-gas-constraint | 5.26 | ordinary world (q=0.251 >= 0.05), not a tail event |
| GS-A-pipeline-spread-30d | 5.77 | ordinary world (q=0.165 >= 0.05), not a tail event |
| GS-C-basis-and-spread-30d | 4.95 | loss 4.95M below target |
| GS-D-congestion-12d-150 | 5.34 | ordinary world (q=0.157 >= 0.05), not a tail event |
| GS-F-cold-load-spread-20d | 5.49 | implausible: marginal beyond T |
| GS-G-congestion-18d-110 | 5.85 | ordinary world (q=0.161 >= 0.05), not a tail event |
| GS-H-short-deep-spread-8d | 5.92 | ordinary world (q=0.055 >= 0.05), not a tail event |
| GS-I-west-decline-spread-22d | 6.47 | ordinary world (q=0.176 >= 0.05), not a tail event |
| GS-W-03-prolonged-gas-constraint-12d | 5.81 | ordinary world (q=0.122 >= 0.05), not a tail event |
| GS-W-04-rt-premium-gas-6d | 3.29 | loss 3.29M below target |
| GS-W-05-load-amplified-spread-12d | 4.47 | loss 4.47M below target |
| GS-W-06-dart-led-pocket-congestion-5d | 2.83 | loss 2.83M below target |
| GS-W-08-dart-load-mixed-9d | 4.74 | loss 4.74M below target |
| GS-W-09-short-intense-pocket-4d | 4.99 | loss 4.99M below target |
| GS-W-11-prolonged-pocket-spread-dart-20d | 2.70 | loss 2.70M below target |
| GS-W-12-extreme-pocket-gas-run-4d | 4.96 | loss 4.96M below target |
| GS-W-13-long-spread-grind-15d | 5.60 | ordinary world (q=0.165 >= 0.05), not a tail event |
| GS-W-14-load-led-pocket-cold-6d | 5.23 | implausible: marginal beyond T |
| GS-W-15-realtime-premium-spread-8d | 2.92 | loss 2.92M below target |
| GS-W-16-pocket-spread-peak-5d | 6.15 | implausible: marginal beyond c |
| GS-W-17-moderate-spread-dart-9d | 5.76 | ordinary world (q=0.075 >= 0.05), not a tail event |
| GS-W-18-west-discount-pocket-4d | 5.58 | implausible: marginal beyond c |
| GS-W1-pipeline-pocket-blowout | 5.64 | ordinary world (q=0.078 >= 0.05), not a tail event |
| GS-W2-pocket-spread-cold-load | 6.21 | implausible: marginal beyond T |
| GS-W2-zone-j-gas-isolation | 5.73 | implausible: marginal beyond g |
| GS-W3-prolonged-gas-squeeze-load | 5.92 | implausible: marginal beyond T |
| GS-W3-sustained-gas-glut-west-discount | 6.97 | implausible: marginal beyond g |
| GS-W4-load-coincident-zone-j-squeeze | 6.73 | ordinary world (q=0.114 >= 0.05), not a tail event |
| GS-W4-persistent-pocket-spread-flat-gas | 5.32 | ordinary world (q=0.176 >= 0.05), not a tail event |
| GS-W5-realtime-squeeze-dart-west-discount | 5.43 | ordinary world (q=0.106 >= 0.05), not a tail event |
| GS-W5-sharp-pocket-spread-cold-peak | 6.14 | implausible: marginal beyond T |
| GS-W6-extended-gas-squeeze-pocket-basis | 4.86 | loss 4.86M below target |
| GS-W6-prolonged-west-gas-glut-pocket-drain | 9.11 | implausible: marginal beyond g |
| GS-W7-ten-day-pocket-spread-mild-gas | 5.32 | ordinary world (q=0.129 >= 0.05), not a tail event |
| GS-W8-fourteen-day-spread-rt-premium | 4.50 | loss 4.50M below target |
| GS-W9-seven-day-high-spread-basis | 5.80 | ordinary world (q=0.055 >= 0.05), not a tail event |
| HW-A-NYC-SPREAD-10D | 5.61 | implausible: marginal beyond T, c |
| HW-B-GAS-BASIS-PocketSpread-15D | 6.09 | implausible: marginal beyond c |
| HW-C-PEAK-SPREAD-RT-DISCOUNT-5D | 5.50 | implausible: marginal beyond T, c |
| HW-D-LONG-MODERATE-SPREAD-20D | 6.95 | implausible: marginal beyond c |
| HW-E-GAS-BASIS-POCKET-14D | 6.15 | implausible: marginal beyond c |
| HW-F-RT-DISCOUNT-POCKET-15D | 7.12 | implausible: marginal beyond c |
| HW-S1-pocket-ref-dart-5d | 5.44 | implausible: marginal beyond c |
| HW-S1-sustained-pocket-widening | 6.61 | implausible: marginal beyond T, c |
| HW-S14-wide-spread-upstate-softening | 7.50 | implausible: marginal beyond c |
| HW-S15-spread-dart-basis-moderate-load | 5.26 | implausible: marginal beyond T |
| HW-S17-short-extreme-spread | 5.38 | implausible: marginal beyond c |
| HW-S2-dart-collapse-8d | 5.67 | implausible: marginal beyond c |
| HW-S2-short-intense-zone-split | 5.61 | implausible: marginal beyond T, c |
| HW-S3-pocket-persistent-12d | 6.29 | implausible: marginal beyond c, g |
| HW-S3-upstate-softening-plus-spread | 3.76 | loss 3.76M below target |
| HW-S4-pocket-spread-7d | 4.58 | loss 4.58M below target |
| HW-S4-sustained-zone-spread-moderate | 4.86 | loss 4.86M below target |
| HW-S5-upstate-glut-10d | 5.32 | implausible: marginal beyond c |
| HW-S6-load-led-spread-with-upstate-softening | 4.72 | loss 4.72M below target |
| HW-S6-pocket-basis-6d | 4.63 | loss 4.63M below target |
| HW-S7-zone-spread-dart-deep-discount | 5.28 | implausible: marginal beyond T |
| HW-S8-high-load-pure-zone-volume | 2.67 | loss 2.67M below target |
| HW-S9-zone-spread-dart-gas-basis | 6.06 | implausible: marginal beyond T |
| HW-SPREAD-10D-200-LOAD110 | 5.94 | implausible: marginal beyond c |
| HW-SPREAD-10D-280 | 8.43 | implausible: marginal beyond c |
| HW-SPREAD-12D-150-LOAD130-RTSPIKE | 5.05 | implausible: marginal beyond T, c, d |
| HW-SPREAD-5D-360-PEAK | 6.42 | implausible: marginal beyond T, c |
| HW-SPREAD-6D-290-LOAD | 5.46 | implausible: marginal beyond T, c |
| HW-SPREAD-8D-240-WESTDIP | 5.35 | implausible: marginal beyond c |
| HW-SUM-01-NYC-SPREAD-10D | 7.22 | implausible: marginal beyond c |
| HW-SUM-02-NYC-SPREAD-SEVERE-8D | 7.48 | implausible: marginal beyond T, c |
| HW-SUM-03-NYC-SPREAD-SUSTAINED-20D | 6.72 | implausible: marginal beyond c |
| HW-SUM-04-NYC-SPREAD-MID-12D-LOAD | 5.58 | implausible: marginal beyond c |
| HW-SUM-05-NYC-SPREAD-WEST-SOFT-14D | 6.17 | implausible: marginal beyond c |
| HW-SUM-06-NYC-SPREAD-GAS-SOFT-15D | 5.87 | implausible: marginal beyond c |
| LLS-S1-pocket-shortfall-10d | 5.82 | implausible: marginal beyond c |
| LLS-S2-sustained-spread-20d | 6.19 | implausible: marginal beyond c |
| LLS-S3-persistent-pocket-30d | 7.46 | implausible: marginal beyond c |
| LLS-S4-pocket-spread-15d | 6.34 | implausible: marginal beyond c |
| LLS-S5-pocket-spread-12d-deep-shortfall | 5.91 | implausible: marginal beyond c |
| LLS-S6-moderate-spread-22d | 5.93 | implausible: marginal beyond c |
| LLS-SUM-01 | 6.55 | implausible: marginal beyond c |
| LLS-SUM-01-NYC-SPREAD | 5.43 | implausible: marginal beyond c |
| LLS-SUM-01-spread-widening | 4.28 | loss 4.28M below target |
| LLS-SUM-02 | 6.21 | implausible: marginal beyond c |
| LLS-SUM-02-PERSISTENT-SHORTFALL | 9.54 | implausible: marginal beyond c |
| LLS-SUM-02-gas-led-congestion | 4.29 | loss 4.29M below target |
| LLS-SUM-03 | 6.40 | implausible: marginal beyond c |
| LLS-SUM-03-GAS-HEATRATE | 5.18 | implausible: marginal beyond c |
| LLS-SUM-03-dart-and-system-stress | 4.11 | loss 4.11M below target |
| LLS-SUM-04 | 6.02 | implausible: marginal beyond c |
| LLS-SUM-04-sustained-spread | 6.31 | implausible: marginal beyond c |
| LLS-SUM-05-long-moderate-spread | 6.86 | implausible: marginal beyond c |
| LLS-SUM-06 | 4.92 | loss 4.92M below target |
| LLS-SUM-06-dart-spread-short-window | 4.92 | loss 4.92M below target |
| LLS-SUM-07-SPREAD-100-SHORT-WINDOW | 5.72 | implausible: marginal beyond c |
| LLS-SUM-08 | 5.62 | implausible: marginal beyond c |
| LLS-SUM-08-GAS-DROP-SPREAD-80 | 6.04 | implausible: marginal beyond c |
| LLS-SUM-09 | 5.63 | implausible: marginal beyond c, d |
| LLS-SUM-09-SPREAD-140-SHORT-SPAN | 5.80 | implausible: marginal beyond c |
| LLS-SUM-10 | 6.10 | implausible: marginal beyond c |
| LLS-SUM-11 | 3.54 | loss 3.54M below target |
| LLS-SUM-12-GAS-DROP-SPREAD-25D | 6.26 | implausible: marginal beyond c |
| LLS-SUM-13 | 6.34 | implausible: marginal beyond c |
| LLS-SUM-14 | 7.72 | implausible: marginal beyond T, c, d |
| LLS-SUM-15 | 3.21 | loss 3.21M below target |
| LLS-SUM-16 | 5.13 | implausible: marginal beyond c |
| LLS-SUM-17 | 4.17 | loss 4.17M below target |
| LLS-SUM-19 | 3.96 | loss 3.96M below target |
| LLS-SUM-20 | 5.90 | implausible: marginal beyond T |
| LLS-SUM-21 | 5.77 | implausible: marginal beyond c, d |
| LLS-SUM-22 | 6.74 | implausible: marginal beyond c |
| LLS-SUM-23 | 3.87 | loss 3.87M below target |
| LLS-SUM-24 | 5.56 | implausible: marginal beyond T |
| LLS-SUMMER-DART-WEST-30D | 4.48 | loss 4.48M below target |
| LLS-SUMMER-NYC-LONG-16D | 6.95 | implausible: marginal beyond c |
| LLS-SUMMER-POCKET-9D | 6.34 | implausible: marginal beyond c |
| LLS-SUMMER-WEST-12D | 5.88 | implausible: marginal beyond c |
| LLS-SUMMER-WEST-DEEP-20D | 4.68 | loss 4.68M below target |
| LLS-SUMMER-ZONE-7D | 4.76 | loss 4.76M below target |
| WIN-GAS-LOAD-SPREAD-9D | 5.63 | implausible: marginal beyond T |
| WIN-POCKET-CONSTRAINED-8D | 5.36 | ordinary world (q=0.078 >= 0.05), not a tail event |
| WIN-POCKET-SPREAD-PEAK-4D | 5.68 | implausible: marginal beyond c |
| WIN-PROLONGED-POCKET-12D | 5.48 | ordinary world (q=0.157 >= 0.05), not a tail event |
| WIN-RT-SPIKE-PROLONGED-10D | 5.11 | ordinary world (q=0.129 >= 0.05), not a tail event |
| WIN-UPSTATE-CURTAIL-SPREAD-12D | 6.03 | ordinary world (q=0.145 >= 0.05), not a tail event |
| WIN-WEST-SPIKE-PLUS-SPREAD-6D | 3.00 | loss 3.00M below target |
