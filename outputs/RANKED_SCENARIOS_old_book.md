# Ranked reverse-stress scenarios (NYISO book)

Source logs: live_explore_seed1, live_explore_seed2, live_explore_seed3, live_smoke_claude-haiku-5-5. Models: claude-haiku-5-5. Client kinds: live.  
Target loss 5.0M. Scenarios read: 32; ranked (eligible): 3; excluded: 29.  
q is a rank against about 250 non-overlapping 10-day windows of 2019-2025, not a probability; fit window 2019-2025; daily averaging understates hourly spikes. A client kind other than the live API means scripted output, not Claude results.  
Largest-loss channel across ranked scenarios: {"zone_volume": 3} (one channel for all of them means the book, not the search, limits diversity).

Coherence grading by a human: [PENDING]. Scenarios are drafts for a risk manager to accept or hedge, not forecasts.

## Ranked scenarios (most plausible first)

### #1 WIN-CS-01-pocket-congestion (cold_snap, winter, 6 days)

**Narrative.** A multi-day cold snap pushes N.Y.C. load above normal while the Central-East and N.Y.C. import corridors bind. The N.Y.C. zone clears well above WEST, which widens the pocket spread by $330/MWh over six days. P5 is short the N.Y.C. retail obligation, so it loses roughly $3,686 per $/MWh-day on the pocket leg, and P2 offsets only about $600 per $/MWh-day. The load ratio is raised to 1.10 to reflect the extra cold-driven demand, which adds modest P5 cost. WEST is left unshocked and gas is unchanged, so P1 and P4 do not gain or lose. The spread move is anchored to the Winter Storm Elliott analogue. Estimated net loss is about $6.0M, with the main uncertainty being whether the sensitivity scales linearly beyond five days.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.1, "pocket_minus_ref_usd": 330.0, "duration_days": 6}`

**Loss** 6.66M (Claude stated 6.00M)  
**Plausibility.** D2 120.4, rank q 0.024, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.73, "l": 1.0, "s": 0.44, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 +0.14M | P2 +1.19M | P3 +0.00M | P4 +0.07M | P5 -8.06M | P6 +0.00M  
**P&L by channel.** system +0.14M | congestion +1.19M | dart +0.00M | gas +0.07M | zone_volume -8.06M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) Dec 2022 (table dates 23 Dec and 24 Dec); **confidence** medium; **soft penalty** 0.0

### #2 WIN-CS-03-transmission-split (cold_snap, winter, 5 days)

**Narrative.** A cold snap causes a transmission split. The N.Y.C. import corridor is constrained, WEST on-peak prices fall by 30% because upstate supply is stranded, and the N.Y.C. minus WEST spread widens by $350/MWh over five days. The WEST decline hurts the long WEST positions P1 and P4, which compounds the pocket loss from P5. No gas or dart shock is assumed, and the load ratio is held at normal. The directional mix is consistent with a cold snap because the N.Y.C. zone is the stressed node. The spread magnitude is above the winter historical maximum but below the implausible ceiling. The stated loss is about $5.6M, combining about $5.4M from the pocket spread with about $0.2M from the WEST decline. The WEST-side estimate is a linear extrapolation from the one-key sensitivity.

**Shock vector (non-neutral).** `{"ref_onpeak_pct": -30.0, "pocket_minus_ref_usd": 350.0, "duration_days": 5}`

**Loss** 5.56M (Claude stated 5.60M)  
**Plausibility.** D2 138.6, rank q 0.020, class adverse, nearest past date 2022-12-24, marginal percentiles {"g": 0.73, "l": 0.98, "s": 0.14, "c": 1.0, "d": 0.09}  
**P&L by position.** P1 -0.12M | P2 +1.05M | P3 -0.00M | P4 -0.03M | P5 -6.45M | P6 +0.00M  
**P&L by channel.** system -0.12M | congestion +1.05M | dart -0.00M | gas -0.03M | zone_volume -6.45M | tail +0.00M  
**Analogue.** Winter Storm Elliott (NYISO) Dec 2022 (table dates 23 Dec and 24 Dec); **confidence** low; **soft penalty** 0.0

### #3 HW-S5-season-long-pocket-regime (heat_wave, summer, 30 days)

**Narrative.** A 30-day summer regime in which the N.Y.C. minus WEST spread stays $70/MWh wider than normal across the whole horizon, reflecting persistent pocket congestion from sustained high N.Y.C. demand. Load is 5% above normal, adding a small cost to P5. No WEST spike days or DART moves are applied, so the loss comes purely from the zone-volume channel accumulating over the full horizon. This is the least extreme daily shock but the longest duration, and it is the least plausible physically because a full 30-day congestion regime is rare.

**Shock vector (non-neutral).** `{"load_peak_ratio": 1.05, "pocket_minus_ref_usd": 70, "duration_days": 30}`

**Loss** 5.83M (Claude stated 5.40M)  
**Plausibility.** D2 160.7, rank q 0.016, class adverse, nearest past date 2022-12-23, marginal percentiles {"g": 0.69, "l": 0.84, "s": 1.0, "c": 1.0, "d": 1.0}  
**P&L by position.** P1 +0.36M | P2 +1.26M | P3 +0.00M | P4 +0.18M | P5 -7.60M | P6 -0.03M  
**P&L by channel.** system +0.36M | congestion +1.26M | dart +0.00M | gas +0.18M | zone_volume -7.60M | tail -0.03M  
**Analogue.** none ; **confidence** low; **soft penalty** 1.0

## Excluded scenarios and why

| scenario | loss (M) | reason |
|---|---|---|
| GS-W-01 | 5.25 | ordinary world (q=0.145 >= 0.05), not a tail event |
| GS-W-04 | 5.87 | implausible: marginal beyond T |
| GS-W-05 | 1.54 | loss 1.54M below target |
| GS-W-06 | 3.62 | loss 3.62M below target |
| GS-W-07 | 7.21 | ordinary world (q=0.086 >= 0.05), not a tail event |
| GS-W-08 | 1.32 | loss 1.32M below target |
| HW-M1-NYC-spread-15d-load-110 | 6.36 | implausible: marginal beyond c |
| HW-M2-dart-spike-20d-moderate-spread | 6.69 | implausible: marginal beyond c |
| HW-M3-extreme-spread-9d-high-load | 6.63 | implausible: marginal beyond c |
| HW-M4-large-load-overshoot-spread | 5.74 | implausible: marginal beyond c |
| HW-M5-gas-basis-spread-17d | 6.64 | implausible: marginal beyond c |
| HW-N1-NYC-spread-12d-load-build | 6.16 | implausible: marginal beyond c |
| HW-N2-NYC-spread-25d-moderate | 7.73 | implausible: marginal beyond c |
| HW-N3-large-load-plus-spread | 4.86 | loss 4.86M below target |
| HW-N4-short-extreme-congestion | 5.26 | implausible: marginal beyond c |
| HW-N5-spread-13d-gas-basis-stress | 5.65 | implausible: marginal beyond c |
| HW-S1-NYC-congestion-10d | 6.78 | implausible: marginal beyond c |
| HW-S2-NYC-spread-8d-high-load | 6.30 | implausible: marginal beyond c |
| HW-S3-prolonged-dome-negative-DART | 9.48 | implausible: marginal beyond c |
| HW-S4-large-load-congestion-DART | 6.45 | implausible: marginal beyond c |
| LLS-SUM-02-NYC-SPREAD-100-30D | n/a | rejected before the engine: sign_consistent |
| LLS-SUM-03-WEST-WEAK-SPREAD-30D | n/a | rejected before the engine: sign_consistent |
| LLS-SUM-04-NYC-SPIKE-SPREAD-10D | 8.01 | implausible: marginal beyond c |
| LLS-SUM-05-RT-BELOW-DA-SPREAD-20D | n/a | rejected before the engine: sign_consistent |
| LLS-SUM-06-NYC-SPREAD-WEST-SLUMP-30D | 10.43 | implausible: marginal beyond c |
| WIN-CS-02-load-growth-pocket | 7.67 | implausible: marginal beyond T |
| WIN-CS-04-sustained-pocket-spread | 5.32 | ordinary world (q=0.129 >= 0.05), not a tail event |
| WIN-CS-05-large-load-pocket-week | 5.85 | ordinary world (q=0.051 >= 0.05), not a tail event |
| WIN-CS-06-short-intense-pocket-premium | 6.61 | implausible: marginal beyond T, c |
