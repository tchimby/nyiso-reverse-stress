# Project plan: A Claude agent that finds the worlds that break a NYISO power book (reverse stress testing)

IEOR 4723, Topics in Quantitative Finance. Solo build, 6 weeks. Modelled on handout example 6 (reverse stress testing agent). Status date: 2026-10-28 (final-state update; the computation is done, grading and write-up remain). This replaces the PJM plan (section 12 lists every change).

**Course note:** the course describes a group project; the user confirmed on 2026-10-28 that solo work is allowed. NYISO terms: the only legal text is the Legal Notice at nyiso.com/legal-notice (no data-specific clause); raw data stays local, aggregates only (see the update at the end).

**Final design choices (2026-10-28):** generator is Claude Sonnet 5.5 (Haiku 5.5 kept as the cheaper comparison); the coherence judge is always a different model from the generator (Opus 5.5 on both); agent repeats run in parallel threads; the book is single-channel by an accepted limitation (rule v2 found 0 of 432 admissible multi-channel books); the severity-anchoring ablation was run on both models. Headline results are in section 8D.

**Fact labels:** "verified" means a reviewer opened the file or document and computed the number. "To verify in Week 0" (TV) means not confirmed; every TV item is collected in section 10. Rules: no future data, no image/OCR work, public data only, no employer data.

**Hypothesis, stated in advance:** the optimizer wins on D^2 (distance from the typical day; nearly guaranteed with 6 factors). Claude must win on coverage (distinct driver classes and channels) and coherence (rubric score). If it does not, the result is reported as negative.

---

## 1. Goal and the trading decision

**Question:** "Which coherent market worlds would lose this NYISO power book $5M or more, and are those worlds plausible?"

**Who uses it:** the risk manager of a power desk (head trader as second reader). Not a price forecast, not a VaR number. The loss is fixed first (25% of $20M allocated capital = $5M) and the program works backwards to the scenarios that cause it.

**Decisions it supports:**
- Accept a breaching scenario (documented sign-off) or hedge it: buy back tail calls, cut the N.Y.C.-over-WEST congestion position, shrink the DA-RT short.
- Read P&L by channel (system price, congestion, DA-RT, gas, spike) so the hedge targets the channel that loses.
- Sort scenarios into adverse, severe, implausible with the plausibility score. A human approves; Claude drafts, code computes.
- Keep an audit log a model-validation reviewer can read.

## 2. The idea in plain words, with a worked example

Claude never predicts a price. It writes a story ("a four-day cold snap with eastern gas stress") and fills a typed list of numbers. A Python engine turns the numbers into daily prices and computes book P&L. A second program scores how unusual the combination is against history. The numbers go back to Claude, which sharpens the scenario or tries another type of event. Every step is logged.

**Worked example (illustrative, not a result).** Claude proposes: cold snap, 5 days, Henry Hub +60%, New York gas basis +$20/MMBtu, peak load 1.10x normal, WEST on-peak +150%, N.Y.C.-minus-WEST spread +$60/MWh, 2 spike days with a WEST daily on-peak average of $450.
- Long WEST swap (P1) gains. Short tail call (P6) pays out about 16 h x 25 MW x ($450 - K6) per spike day. The N.Y.C. load obligation (P5) loses because load and the N.Y.C. price both rise. The DA-RT short (P3) loses if real time clears above day-ahead, as on 23 Dec 2022 and 24 Jun 2025 (section 8).
- Engine output: total P&L, loss by position and channel, and "q = 2%: rarer than 98% of past 10-day windows; nearest past analogue: late Dec 2022".
- If the loss is under $5M, Claude receives the numbers and the headroom per channel and is asked for a harsher or different scenario.

## 3. The synthetic book (6 positions on NYISO zones)

Month-ahead block (for example January 2027, daily settlement). On-peak = weekday hours 7-22 in hour-beginning stamps, i.e. HE8-23 as in the PJM plan (16 h); off-peak = other 8 h. NERC holidays excluded as on-peak (holiday handling in the data not yet applied: TV). P_W = WEST, P_N = N.Y.C. (Zone J), G = gas, d = day. All prices are daily averages of the hourly files (settlement series = real time; section 4).

**Why these zones.** WEST is the reference zone: upstate, low-cost, near the largest MW of queued large loads (section 6), and the zone whose price is least exposed to eastern gas. N.Y.C. is the load pocket: downstate, import-constrained, with Transco Z6 NY gas. The N.Y.C.-WEST on-peak spread is a real, measured congestion signal: 25 to 110 $/MWh day-ahead on the sampled event days and up to 339 in real time (23 Dec 2022: 338.5). One pair (reference, pocket) is all the engine needs. Long Island has larger spikes (4,522 hourly on 24 Jun 2025) but is excluded to keep the book to two zones.

| # | Position | Size | Channel | Daily P&L |
|---|---|---|---|---|
| P1 | Long WEST on-peak swap, strike K = forward level | 100 MW | System price | 16 x 100 x (P_W,d^on - K) |
| P2 | Long N.Y.C. / short WEST spread, around the clock | 25 MW | Congestion (location) | 24 x 25 x [(P_N,d - P_W,d) - c0] |
| P3 | Short DA-RT spread at WEST, off-peak | 50 MW | DA-RT | 8 x 50 x (DA_d^off - RT_d^off) |
| P4 | Long heat-rate call, WEST on-peak vs gas, heat rate 8.0, VOM $3 | 50 MW | Gas / spark | 16 x 50 x max(P_W,d^on - 8.0 G_d - 3, 0) - premium (fair value, $8.29/MWh) |
| P5 | Load obligation in N.Y.C.: short zone at fixed retail price R, long WEST hedge at H, volume scales with load | 140 MW x L_d/L_normal | Zone basis + volume | 24 x 140 x (L_d/L_normal) x [(R - P_N,d) + (P_W,d - H)] |
| P6 | Short call on WEST daily on-peak average, K6 = 99th percentile of that average in the fit sample | 25 MW | Spike / tail | -16 x 25 x max(P_W,d^on - K6, 0) + premium (fair value, $0.53/MWh) |

G_d = Henry Hub_d + b, where b is a stated New York basis assumption (section 4), not a fitted number.

**Final sizes (the table above, `config.py`).** The table shows the calibrated book; the starting values were 50/50/25/100/200/25 MW. Option premiums are set at fair value on the fit sample; the engine reports shocked minus unshocked P&L, so a constant premium cancels in scenario loss. At those sizes the $5M target was reached by ordinary worlds (conditional-Gaussian rank q about 0.075), so no arm could breach. A rule written before the scan picked, over 93 candidates, P1 100, P2 25, P3 50, P4 50, P5 140, P6 25 MW, target kept at $5M (25% of $20M). Worst historical rolling 30-day loss is $3.22M (64% of target). Limits to state: the rule's channel-mix and concentration conditions were met by none of the 93 candidates and were relaxed as the rule allowed; every breach is a winter N.Y.C.-WEST spread blow-out carried by P5 (110% of net loss, P2 gives back 17%). A redesign under a second pre-declared rule (v2, 432 candidates, fair-value premiums for P4/P6) found 0 admissible multi-channel books; the user accepted the single-channel limitation on 2026-10-28, and it is reported as a negative result on multi-channel coverage (live runs: all 41 ranked scenarios lose most on zone_volume). A price crash, DA-RT gap or spike cannot carry $5M in this engine (price floor, long call with no premium, spike worlds ordinary or beyond marginal limits). Zone liquidity of the sizes is unchecked (TV).

**Risk channels.** System price: P1, P4 (and P5's WEST hedge leg). Congestion/location: P2 and P5 (both load N.Y.C. against WEST). DA-RT: P3. Gas: P4, plus the basis shock. Spike/tail: P6 and the RT spike overlay on every position. Volume: P5.

Net exposure: long system price, long N.Y.C. congestion, short DA-RT, long gas-linked optionality, short zone basis and volume, short tails. A cold snap helps P1 and P4 and can hurt P2 (if the spread collapses), P3 (RT above DA), P5 and P6.

## 4. The risk engine

**Data (daily, 2019-2025, about 2,500 days, plus 2014 for the polar-vortex replay):**
- Hourly integrated real-time zonal LBMP (the `rtlbmp` product) and day-ahead zonal LBMP, WEST and N.Y.C. This is the settlement series. Do not average raw 5-minute rows: about 6% of intervals are off-schedule extra runs, so row counts vary from 294 to 344 per day (verified, 23 Dec 2022 has 344 rows). Hourly-integrated and on-grid 5-minute on-peak means agree within about 1% on the event days checked.
- Load: sum of 11 zones from `palIntegrated` (no NYCA total in the file). Verified against official peaks to under 1 MW (section 8).
- Henry Hub (EIA daily); NOAA daily temperature, Central Park as the N.Y.C. driver, Albany/Buffalo/Syracuse for upstate, all keyless and complete 2014-2026.
- Timestamps are local clock time with no zone flag. Fall-back day has 25 hourly rows with 01:00 twice; spring day has 23 (verified). Join by row order or convert to UTC. Each daily file carries the next day's 00:00 row in the 5-minute product: drop it. Stamps read as hour-beginning from the files; NYISO's own wording is TV.

**Scope cuts (solo):** daily on/off-peak averages only; one price pair; gas = Henry Hub + stated basis; no NYISO forecast as a factor except the day-ahead load forecast miss as a shock-size reference (section 6).

**Factors** (explicit, not PCA; PCA only as a diagnostic; measured 2026-10-29: four components are needed for 93% of the variance of the five core factors, so the over-85% target is not met (outputs/factors/pca_shares.csv)): x = [g, l, T, s, c, d]
- g = log Henry Hub; l = log(daily peak NYCA load / seasonal normal); T = degree days (Central Park); s = log WEST on-peak residual after gas and load; c = (N.Y.C. - WEST) on-peak spread in dollars; d = log(RT_on / DA_on) at WEST. Real-time prices go negative in places, so check the log for d; fall back to a dollar gap if needed.
- Price model: log P_W = a_season + b1 g + b2 l + b3 l^2 + e (squared term for the convex heat-rate response).

**Gas.** No free daily New York gas history exists in the keyless set (verified): EIA/ICE files cover only 2014-03 to 2017-12, with no Transco Z6 NY or Iroquois. So b is a stated stress input, calibrated to event points, not fitted. Verified Z6 NY daily spot (EIA Weekly Update, NGI): 6 Jan 2014 56.59 vs Henry Hub 4.50; 17 Jan 2025 97.90 vs about 10; 22 Jan 2025 17.54; 24 Jun 2025 3.10 (calm). Dec 2022 Elliott days 23-27 Dec: not verified. Monthly EIA N.Y. citygate understates spikes (Jan 2014 6.09 $/Mcf). No daily-basis result may be claimed.

**Covariance:** Sigma of deviations from seasonal means for [g, l, s, c, d], by season, rolling 3-year window (5-year fallback in winter), Ledoit-Wolf shrinkage or MCD.

**Spike component (separate from the Gaussian core).** Spike day = WEST daily on-peak above the 97.5th percentile of its season, or a DA-RT gap beyond a threshold. Probability = logistic in load, extreme-temperature and outage proxies; size above threshold by peaks-over-threshold (Pareto), shape reported as a range. Scale check: the largest daily on-peak real-time averages seen are WEST 416.5 and N.Y.C. 625.5 (24 Jun 2025).

**Caps and shortage pricing (from verified rules).**
- No hard cap on LBMP is visible: real time exceeds $1,000 in 158 hourly rows and 2,567 five-minute rows; hourly maximum 4,522 (Long Island, 24 Jun 2025); Elliott "over $4,000" (2022 SOM). Day-ahead never exceeded 665 in the sampled months.
- The $2,000 offer cap (offers above $2,000 cannot set price; $1,000-2,000 are cost-verified) rests only on 2017 draft compliance slides; the current tariff is TV.
- Prices exceed $2,000 because shortage adders stack: 2025 reserve demand curve steps up to $750 (30-min NYCA), plus 10-min NYCA $750, spin $775, East $775, SENY $500; transmission shortage steps $200/$350/$600/$1,500/$2,500 and $4,000 for violations beyond the relief margin (since 14 Nov 2023).
- Engine rule: hourly LBMP clipped at a scenario cap of $5,000 (a stated assumption sitting above the verified $4,522 hourly maximum, not a NYISO number). Congestion components of -4,000 to -5,147 appear in Long Island and N.Y.C. data, so winsorize congestion in the fit and treat the scenario congestion bound as a stated assumption. Daily on-peak averages stay far below hourly spikes (17:00-20:00 on 24 Jun 2025 averaged $1,300 to $3,500 by region, yet the WEST 16-hour average was 416.5).

**Structural breaks (run with and without pre-break data):**
- 22 Jun 2016 Comprehensive Scarcity Pricing; before it, shortage pricing differs and the 2014 polar vortex is a different regime (no reserve demand curves in 2014). Primary cutoff candidate: 2016-06-22; adopt after Week 0 check.
- Indian Point 2 and 3 retirement (Apr 2020, Apr 2021): more eastern gas dependence.
- 14 Nov 2023 transmission shortage pricing revision; summer 2021 reserve demand curve revision.
- Peaker Rule retirements in N.Y.C. through 2025.
- CHPE (1,250 MW into Zone J): status as of today is unverified (press says in service 1 Jul 2026 and failed 4 Jul; a snippet says 13 May 2026). TV. If it is in service, post-2026 N.Y.C. spreads should not simply reuse 2019-2025.

**Plausibility score:**
1. D^2(s) = (s - mu)' Sigma^-1 (s - mu), Gaussian-core factors only, robust mu and Sigma.
2. q(s) = share of non-overlapping 10-day windows with D^2 at least D^2(s). About 250 windows and fewer than 10 independent extremes: q is a rank, not a probability.
3. Marginal percentiles; nearest historical date.
4. Spike overlay scored separately by empirical exceedance.

Classes: adverse if 1% <= q <= 5%; severe if q < 1% and every marginal within 1.25x its historical maximum; implausible if any marginal exceeds 1.25x or a hard rule fails.

**Conditional-Gaussian most-likely-scenario baseline** (Sparviero & Viola, 2606.09274): given a target loss, the single most likely factor vector is the conditional mean of the Gaussian core on the loss hyperplane. It is the analytic version of the optimizer and is computed alongside it (section 8).

## 5. The Claude agent loop

**Schema (enforced; units in key names; numbers, never ranges):**
```json
{
 "scenario_id": "S-014", "prompt_version": "v3",
 "narrative": "...", "horizon_days": 30,
 "season": "winter|summer|shoulder",
 "driver_class": "cold_snap|heat_wave|gas_supply|transmission|large_load_shortfall|generator_outage|reserve_shortage",
 "shocks": {
  "gas_hh_pct": 0, "ny_gas_basis_usd": 0, "load_peak_ratio": 1.0, "large_load_shock_mw": 0,
  "ref_onpeak_pct": 0, "pocket_minus_ref_usd": 0, "dart_pct": 0,
  "spike_days": 0, "spike_daily_avg_usd": 0, "duration_days": 0
 },
 "stated_loss_usd": 0,
 "analogue": {"event": "", "dates": "", "claimed": {"metric": 0}, "source": ""},
 "confidence": "low|medium|high"
}
```
`ref_onpeak_pct` is the WEST on-peak move and `pocket_minus_ref_usd` is N.Y.C. minus WEST; the prompt carries a one-line mapping (section 12, code refactor). `stated_loss_usd` is Claude's own estimate of the loss, used for the stated-vs-implied check below.

**Claude sees (seed):** the target loss, book table, channel sensitivities, season, caps, per-factor mean/sigma/historical maximum, the analogue table (section 8), the large-load ranges (section 6), the schema. **Engine returns:** numbers and rule verdicts only: total P&L, P&L by position and channel, D^2, q, marginal percentiles, nearest date, spike exceedance, hard-rule verdicts, headroom per factor.

**Termination:** 12 iterations per seed, 4 seeds (one per driver family), 3 scenarios per call, stop at 5 distinct breaches (loss >= $5M, q < 5%, pairwise distance > tau) or two empty iterations. About 48 calls per run.

**Hard rules (reject and log):** hourly LBMP above the $5,000 scenario cap; sign-inconsistent shocks (cold snap with load or gas down); spike average above what the clipped-hour logic allows; duration over horizon; invalid enum; analogue number more than 30% off the lookup table (logged as a fabricated-analogue event).
**Soft penalties (rank down):** q below 0.1%; nearest distance above the historical maximum; narrative under 40 words; same driver_class already in 3 accepted scenarios.

**Logging:** prompt version and hash, JSON in and out, engine outputs, rule verdicts, tokens, cache flag; `--dry-run` replays by prompt hash. **Pinned-input run manifest** (Soleimani 2512.07867): each run records the data file hashes and download dates (NYISO months get corrected after the fact, e.g. 05-2025 and 06-2025 were updated 07/07/25; re-download at the end and re-hash), config, model ID, temperature, seed and prompt hash, so a run can be reproduced from the manifest alone.

**Cost:** about 5-7k input and 1.5k output tokens per call, about 350k tokens per run; check live pricing, do not hard-code it.

**Added ablations (literature-driven).**
- **Severity anchoring:** Soleimani finds severity comes from the prompt, not from the model's reasoning. So run each prompt with and without the $5M loss target. If the loss distribution tracks the stated target in both arms, Claude is anchoring, not searching.
- **Repeat-run dispersion:** at least 5 repeats per arm; report the spread of breach counts, median q and coverage.
- **Stated-vs-implied loss check:** compare `stated_loss_usd` with the engine's loss; report the error distribution. Large gaps mean the narrative is not tied to the numbers.
- **Gate rejection rate:** report the share of proposals each hard rule rejects. A gate rejecting about 0.2% (as in Soleimani) is not a guardrail; if ours rejects almost nothing, say so, and report which rules ever fire.

## 6. Large-load driver (one scenario driver, not a deliverable)

It acts only through the load factor: l' = l + shock_MW / L_normal, with L_normal the seasonal-normal NYCA peak (about 31.6 GW summer 2026, 24.6 GW winter 2026-27; 1,000 MW is about 3.2% of summer peak, versus 0.65% for PJM). A location term (pocket minus ref) shifts by a **stated assumption**, not a regression: the large loads sit in zones A-E (West/Central/North), none queued in Zone J, so the link to N.Y.C. is indirect.

**Calibration (verified, NYISO Gold Book 2024, 2025, 2026; Power Trends 2025, 2026):**
- Forecast large-load MW, summer (Table I-14, 2026 edition): 538 (2026), 1,831 (2030), 2,643 (2035), 2,880 (2040). That is 1.7% of the 2026 baseline peak, 5.7% in 2030, 8.0% in 2035.
- Revisions between editions: 2026 value 1,091 (2024 edition), 1,023 (2025), 538 (2026): a cut of 485 MW (-47%) in a year; 2030 value 1,894, 2,005, 1,831. Timing slippage of 1-2 years is the main revision mode.
- Scenarios (2026 edition): Lower 337 (2026), 914 (2030), 1,221 (2035); Higher 578, 2,617, 4,019 (2035), 4,336 (2040). Range around baseline: 2030 -917/+786 MW; 2035 -1,422/+1,376 MW.
- Queue (Table IV-7, 15 Mar 2026): 48 projects, 12,330.1 MW (3,948.5 MW in 2025; 2,722.2 MW in 2024). Only 14 projects, 2,557.1 MW, are in the forecast; about 9.8 GW is queued but unforecast. By my keyword classification (not a NYISO category), about 5,799 MW are data-center-type.
- Shock ranges: shortfall -0.5 to -1.5 GW by 2027-28 (-1.5% to -5%); medium-term -0.9 GW (2030), -1.4 GW (2035); overshoot +0.8 GW (2030) to +1.4 GW (2035); labelled tail +3 to +4 GW (not a NYISO forecast).
- Day-ahead load forecast miss at peak (forecast minus actual, previous-day vintage): -3.0% to -7.0% on event days, up to -9.5% (25 Jun 2025); about -1,500 MW typical. This is a separate, weather-type shock.

**Limits:** three Gold Book vintages; no observed large-load series (so error cannot be isolated; only total peak vs forecast: weather-normalised 2025 peak 31,405 vs forecast 31,471, -0.2%); weather noise of 1-3% of peak swamps near-term revisions; load is net of distributed solar. These are scenario ranges, not an estimated distribution.

## 7. Data inventory

| Source | Used for | Verified by independent check | Access friction | History depth | Terms of use |
|---|---|---|---|---|---|
| NYISO MIS day-ahead zonal LBMP (`damlbmp`), RT hourly (`rtlbmp`), RT 5-min (`realtime`) monthly zips | WEST and N.Y.C. prices | **Yes** (7 months parsed; event days recomputed) | None: keyless HTTP, ~100 KB-1.3 MB per month, ~60 requests per product | Index lists 11-1999 on; 2001, 2010, 2014, 2019 files return 200; 2014 and 2022-2025 parsed. Every month not individually tested | **Not located** (nyiso.com terms, legal, market-data URLs returned 404); cite as NYISO MIS public data, TV |
| NYISO `palIntegrated` (hourly load by zone), `isolf` (forecast) | Daily peak load, forecast miss | **Yes** (4 peaks match official to under 1 MW) | None; `isolf` files hold 6 overlapping vintages, pick by file name | 2001-06 / 1999-11 on | Not examined |
| NYISO Gold Books 2024-26, Power Trends 2025-26 | Large-load driver | **Yes** (tables opened) | None | 3 vintages | Power Trends grants fair use for educational purposes; Gold Book gives none, so cite only |
| Potomac Economics SOM 2014, 2022, 2025; quarterly 2025Q1, Q2, 2026Q1; NYISO Operating Committee decks | Analogues, rules | **Yes** (opened) | None; charts lose numbers in text extraction | As listed; 2015-21, 2023-24 SOM not opened | Copyright notices; cite, do not republish |
| EIA Henry Hub daily | Gas factor | Yes | Free | 1997-2026 | Public domain, cite EIA |
| EIA NY citygate monthly; EIA Weekly Update (NGI Z6 NY, 4 editions) | Basis calibration | Yes (event weeks only) | Free; Weekly Update pages are 5-day tables | Citygate 1989+; Z6 NY daily only for event weeks | NGI data are third-party; do not redistribute |
| NOAA GHCN daily (6 NY stations) | Degree days | Yes | Keyless | Complete 2014-2026 | Cite NCEI; no restriction seen |
| EIA/ICE wholesale files | Not usable | Yes: **no NYISO products** | - | - | - |
| NYISO tariff (offer cap), CHPE status, Elliott-day gas | Rules | **No (TV)** | - | - | - |

Python note: pandas imports fail under `python -I` on this machine; use `python -E -P`.

## 8. Evaluation and verification

**A. Engine validation by replaying verified events.** Feed each event's realized daily factor vector through the shock-to-P&L engine and compare with P&L computed directly on actual prices; expect agreement within about 30% on averaged positions, with P3 and P6 understated by daily averaging. Check signs by position and channel. Verified daily on-peak means ($/MWh, hourly-integrated):

| Event | WEST DA / RT on-peak | N.Y.C. DA / RT on-peak | Load (NYCA peak, verified vs official) | Notes |
|---|---|---|---|---|
| Polar vortex, 7 Jan 2014 | 137.3 / 354.4 | 224.8 / 509.5 | 25,737.8 vs 25,738 MW (winter record) | Z6 NY gas 56.59 on 6 Jan; pre-2016 pricing regime |
| Elliott, 23-24 Dec 2022 | 82.8 / 229.6 (23 Dec) | 141.6 / 568.1 | 22,003.9 vs 22,004 MW (24 Dec, HB17) | Not a load record; 24-25 Dec are weekend (all-hours comparison); RT hourly max 3,132 Long Island; "over $4,000" per SOM; Elliott gas days TV |
| Cold, 20-23 Jan 2025 | 193.5-227.9 DA / 115.7-200.1 RT | DA 301-328 | 23,521.3 vs 23,521 MW (22 Jan) | DA above RT; Z6 NY 97.90 on 17 Jan (before the cold days); 20 Jan is the MLK holiday |
| Heat, 23-25 Jun 2025 | DA 131.6/144.5/112.0; RT 270.5/416.5/188.8 | 24 Jun: 181.8 / 625.5 | 31,857.2 vs 31,857 MW (24 Jun) | Major Emergency 18:13-19:58; gas calm (3.10) so a pure load/reserve event |

DA-RT on-peak gap (DA minus RT, WEST/N.Y.C.): 7 Jan 2014 -217/-285; 23 Dec 2022 -147/-427; 24 Jun 2025 -272/-444; Jan 2025 positive. This shows P3's sign is event-dependent. Also check the load-weighted monthly LBMP definition against the SOM Table 1 averages (Q1 2014: WEST 95.71, N.Y.C. 133.70) and state which definition is matched. Extra analogue: Jan-Feb 2026 cold spell (24.3 GW peak, Iroquois Z2 Q1 average $17.47), the newest winter stress; its prices are not yet downloaded (TV).

**Analogue table for Claude (each row has source and vintage):** the four events above plus the large-load series (section 6). Items not found are left empty so they are not shown to Claude: event-day maximum LBMP and shortage-interval counts for 2014, 2025 and Elliott. Peak and price numbers come from the files in section 7; Elliott system figures (PJM SAR request 3,000 then 2,000 MW, NYISO about 320-485 MW; import curtailments 1.5/1.8/0.7 GW; forced outages 1.8 GW) from the 2022 SOM pp. 34-40.

**B. Coherence rubric (pre-registered, 0-1 per item):** causal chain stated; every non-zero shock explained; duration matches narrative; analogue relevant and correctly cited; no contradictory channel. Mechanical checks first, human for the rest. With a solo build the second rater is a classmate or a re-grade a week later blind; report agreement (percent and Cohen's kappa) on at least 20 scenarios. Grade all arms with narratives shuffled.

**C. Analogue accuracy:** each claimed number scored correct / within 30% / wrong, including about 50 items with not-in-corpus entries (right answer: empty analogue or low confidence). Report fabricated-analogue rate per prompt version.

**Headline results (final).** Same protocol, seed 0, 5 repeats, target $5M. Breaches per repeat: optimizer 15.4, Claude Sonnet 5.5 9.8, cond-Gaussian 4.4, Claude Haiku 5.5 3.6, random 0. Median D^2: optimizer 93, cond-Gaussian 105, Haiku 145, Sonnet 159. Coherence (blind, same Opus 5.5 judge): Sonnet 0.578, Haiku 0.611. Every ranked scenario loses mostly on zone_volume (single-channel limitation, accepted). The pre-stated ordering holds: the optimizer wins on D^2 and breaches; Claude's measured edge is driver coverage (about 0.31 vs 0.2) and, for Sonnet, breach volume over cond-Gaussian, not plausibility or coherence. Details and caveats in the bullets below.

**D. Baselines at equal budget** (same engine evaluations: 48 per seed, 4 seeds, at least 5 repeats):
- (a) Claude in the loop.
- (b) Random search from N(mu, Sigma) plus the same spike overlay.
- (c) Optimizer (SLSQP or CMA-ES) for minimum D^2 with loss >= $5M and the same hard rules, template narrative.
- (d) Conditional-Gaussian most-likely scenario (closed form, one point per loss level; then local perturbations to fill the budget).
- **Primary metric:** number of distinct breaching scenarios (loss >= $5M, q < 5%, pairwise distance > tau, hard rules passed). **Secondary:** median q and D^2 of breaches, driver and channel coverage, rule-pass share, coherence, novelty (distance to nearest replay event), and the gate rejection rate.
- **Predicted ordering, stated in advance:** optimizer and conditional-Gaussian best on D^2; Claude best on coverage and coherence; random worst.
- **Final engine, daily factor model (outputs/live_daily_sonnet, Sonnet 5.5):** seasonal harmonics plus load x season in the price model and a persistence tail (phi 0.55 level, 0.59 spread). Breaches per repeat: Claude 11.2 (sd 0.4), optimizer 8.0, cond-Gaussian 0.2, random 0; median D^2 156 / 93 / 89; 59 of 176 ranked-eligible, all zone_volume; Opus 5.5 coherence 0.664. Rule v1 re-applied on this engine admits no book sizing (4 of 5 distinct breaches; outputs/book_scan_v3); sizes and the 5M target were kept by decision, so these numbers are not directly comparable with the earlier engine below.
- **Generator comparison, same protocol (outputs/live_full_sonnet vs live_full):** Sonnet 5.5 9.8 +- 2.8 breaches per repeat vs Haiku 3.6 +- 2.3 (optimizer 15.4, cond-Gaussian 4.4, random 0); median D^2 159 vs 145; ranked-eligible 55/170 vs 18/165; blind coherence by the same judge (Opus 5.5) 0.578 vs 0.611. More breaches, no D^2 or coherence gain. Anchoring ablation on Sonnet (one run): target shown median loss $6.70M, 10 breaches; target hidden median $8.64M, 3 breaches - opposite of Haiku's pattern ($1.95M, 0 breaches), so anchoring is model-dependent.
- **Primary live result: one full run (outputs/live_full, seed 0, 5 repeats, parallel threads, 4 min 40 s):** breaches per repeat Claude 3.6 (sd 2.3), optimizer 15.4, conditional-Gaussian 4.4, random 0; median D^2 145 / 93 / 105; 18 of 165 scenarios ranked-eligible (all zone_volume); blind Sonnet 5.5 coherence on those 18: 0.689. The five separate runs below gave Claude 7.6, so its breach count is unstable across draws and neither figure is its level.
- **Supporting live result, Claude Haiku 5.5, 5 repeats (seeds 0-4, outputs/live_haiku_r1 and live_haiku_s1..s4, 144 baseline evaluations per arm; Claude used 36-53 per repeat, so budgets are not strictly equal):** breaches per repeat, Claude 7.6 (10, 6, 9, 9, 4), optimizer 17.8, conditional-Gaussian 4.8, random 0. Median D^2 (mean over repeats): optimizer 94, conditional-Gaussian 105, Claude 129, as predicted. Breaches per engine evaluation: Claude about 0.17, optimizer 0.12, conditional-Gaussian 0.03 (derived). Hard-rule rejections 1 of 219 (sign_consistent); stated loss within 20% of the engine loss in 78-95% of scenarios per repeat (median relative error 7-9%, i.e. anchored near the target). 41 of 219 scenarios are ranked-eligible (outputs/RANKED_SCENARIOS.md); human coherence grading [PENDING]. Anchoring ablation (one live Haiku run): target shown 63 scenarios, median loss $5.77M, 73% above target, 11 breaches; target hidden 24 scenarios, median loss $1.95M, 0 breaches. Blind coherence by Sonnet 5.5 on the 41 ranked: mean 0.815 (no_contradiction 28/41 weakest); human grading still [PENDING]. Generation stays on Haiku by decision; no Sonnet arms.
- **Offline result on the calibrated book (fake Claude arm, NOT a Claude result):** optimizer 15.4 distinct breaches per repeat, conditional-Gaussian 4.4, random 0 (outputs/nyiso_demo, 5 repeats). Fairness caveat: the optimizer is given the risk model's tail threshold and marginal limits, which the other arms are not. Sensitivity (`sensitivity.csv`): conditional-Gaussian breaches fall from 16.4 to 4.4 to 2.0 as tau goes 0.5, 1, 2; weakest-breach q is 0.049 under 14-day windows, i.e. on the 5% edge. tau, window length and the spike overlay are placeholders.

**E. Ablations:** prompt v1 (no schema), v2 (schema + enums), v3 (schema + analogue table + engine feedback); leave-one-out (no plausibility feedback, no analogue table); severity anchoring; repeat-run dispersion; masking test (events renamed E1, E2, E3 with numbers kept); post-cutoff test on 2025 events with numbers hidden.

**F. What "LLM right vs hand-coded" will show:** if the optimizer plus template matches Claude on breaching and plausibility, Claude's measurable edge is coverage across driver classes, rule-passing without hand-written constraints per class, and analogues that survive the lookup. If the anchoring ablation shows Claude's severity simply follows the prompt's loss target, and the coverage edge is absent, the finding is that the LLM is not needed here. That is a valid result.

## 9. Deliverables and 10-minute demo

**Deliverables:** (1) NYISO data layer and 13-column daily panel; (2) P&L engine with unit tests; (3) factors, covariance, spike model, plausibility scorer; (4) agent loop with schema, cache, `--dry-run`, audit log, run manifest; (5) baselines and ablation results; (6) analogue table with sources; (7) 10-12 page report with data-use statement and limitations.

**Demo:** 1 min the question and the book; 2 min replay validation on Elliott and June 2025; 1 min schema and a live `--dry-run`; 3 min ranked scenarios with narrative, shock vector, P&L by channel and q, plus one rejected scenario and its rule; 2 min Claude vs random vs optimizer vs conditional-Gaussian; 1 min governance and the anchoring result.

## 10. Status by work package (replaces the week-by-week plan, 2026-10-28)

| Work package | Status | Where |
|---|---|---|
| NYISO data panel 2019-2026, event validation | done | data/processed/nyiso_panel.csv, nyiso_event_validation.csv |
| Engine, risk model, plausibility (D^2, q), hard rules | done | revstress/, 257 tests pass |
| Book sizing and multi-channel redesign | done; single-channel limitation accepted | config.py, outputs/book_scan_v2 |
| Baselines (random, optimizer, cond-Gaussian) at equal budget | done | outputs/live_full*, comparison_table.csv |
| Live Claude arms, Haiku 5.5 and Sonnet 5.5, 5 parallel repeats each | done | outputs/live_full, live_full_sonnet |
| Severity-anchoring ablation on both models | done, one run each | outputs/live_anchoring, live_anchoring_sonnet |
| Ranked scenario deliverables | done | outputs/RANKED_SCENARIOS_full.md, RANKED_SCENARIOS_sonnet.md |
| Coherence grading: two LLM raters, blind | done; agreement reported | outputs/coherence_* |
| Coherence grading: human rater (and second human) | OPEN, needs the user | marked [PENDING] |
| Report draft and 10-minute demo outline | draft done | pjm_revstress/REPORT_DRAFT.md |
| Prompt-version ablation v1/v2/v3 on the live API | not run (offline only) | run_ablations, fake client |
| Analogue accuracy test with not-in-corpus items (8C) | not run live | |
| Obsolete PJM fallback files | removed 2026-10-28 | |
| Verification list (TV items in section 7 and 12) | open: offer cap, CHPE, Elliott gas, hour-beginning wording | |

Reminder of the evaluation spend so far: about 3.1 M input and 1.3 M output tokens summed over the Haiku and Sonnet run caches (the first Haiku sequential launch is counted once); the ablation and judge calls add a few hundred thousand more, not summed. Anything marked open above is optional for the course deliverable except the human grading.

## 11. Risks (top 5) and feasibility

1. **Sample and breaks.** About 7 years, few independent extremes, several breaks, and a different shortage regime before 2016. Mitigation: shrinkage, non-overlapping windows, with/without runs; q is a rank.
2. **Spike model and daily averaging.** Hourly maxima of 3,000-4,500 vanish in 16-hour means; the Pareto shape is poorly determined; congestion components of -4,000 to -5,147 distort means. Mitigation: separate overlay, winsorize, report ranges, state replay understates P3 and P6.
3. **Agent edge may not show, or may just be anchoring.** Mitigation: pre-stated hypothesis, anchoring ablation, honest negative result.
4. **Gas history is missing.** No daily New York gas series; basis is an assumption calibrated to a handful of event days. Mitigation: no daily-basis claims; basis is an explicit shock.
5. **Refactor and unverified rules.** Converting PJM code to NYISO can break the 119 tests silently; the offer cap, CHPE and terms are unverified. Mitigation: keep names, test after each step (section 12), TV list.

**Feasibility: 3.5/5.** Data is keyless and event-verified, which is better than PJM; offset by missing gas history, a weaker large-load story (no observed series, mostly upstate) and solo bandwidth. No claim of statistical power on tail events.

## 12. What changed from the PJM plan, and why

**Corrections carried over or made while converting:**
1. Market PJM to NYISO (student decision). Hubs, HB_/LZ_ names, Dominion and Western Hub dropped; WEST and N.Y.C. LBMP zones used.
2. The PJM $3,700 energy-component cap is removed: NYISO shows no visible LBMP cap, and prices exceed the $2,000 offer cap because shortage adders stack (up to $4,522 hourly, 4,700 five-minute in Dec 2022). Engine uses a stated $5,000 scenario cap.
3. The PJM 1 Oct 2022 reserve redesign break is dropped. NYISO breaks are 22 Jun 2016 scarcity pricing, 2020-21 Indian Point, 14 Nov 2023 transmission pricing, and CHPE (unverified).
4. NYISO is summer-peaking (31.9 GW vs 22-26 GW winter), so the heat wave is the largest load stress; the book gets both cold and heat drivers.
5. Elliott is not a load record at NYISO (22,004 MW vs the 23,369 MW winter 2022-23 peak). The PJM claim set (134,700 MW etc.) is deleted.
6. PJM data access (key by email, internal-use terms, 731-day archive, 6 calls/min) replaced by keyless NYISO downloads; the terms-of-use text was not found (TV).
7. Raw 5-minute data cannot be averaged (6% off-schedule rows); the hourly integrated file is used. Daylight-saving days and next-day 00:00 rows handled.
8. Gas: PJM had a fixed Henry Hub basis; NYISO has a New York basis shock, calibrated to verified event points (6 Jan 2014 56.59; 17 Jan 2025 97.90) with a shock key `ny_gas_basis_usd`. EIA/ICE electricity files have no NYISO products, so they are dropped as a fallback.
9. Data-center driver replaced by a large-load driver calibrated to the Gold Book (three vintages, zonal table, published lower/higher scenarios, named queue). Weaker than PJM on observed data (none), but shock sizes are published, not invented. Still one driver.
10. Weather stations: PHL/PIT/DCA/ORD/CMH/CLE replaced by Central Park, LGA, JFK, Albany, Buffalo, Syracuse.
11. Added from the literature: severity-anchoring ablation, repeat-run dispersion, stated-vs-implied loss, gate rejection rate, conditional-Gaussian baseline, pinned-input manifest.
12. Active-event notes: 20 Jan 2025 is a holiday; Dec 24-25 2022 are weekend days (use all-hours means).

**Code refactor (from the code_refactor review; about 3,700 lines in 38 files, 119 tests).**
- Add `revstress/market.py`: a frozen `Market` object (name, reference and pocket zone labels, energy cap, on-peak hours, structural-break cutoff, analogue table, loader, weather stations, typical peak MW). PJM and NYISO instances; PJM stays the default so tests remain green.
- Keep internal column names `wh_*`/`dom_*` for the first pass, with documented aliases: `wh` = reference zone (WEST), `dom` = load pocket (N.Y.C.). A full rename touches about 150 lines and 37 of 119 tests and changes the agent-visible keys. Optional later step only, as a scripted rename with a legacy-column shim, shock keys last.
- Replace the hard-coded `3700` literals (plausibility failure string, FakeClient template) with the config cap; read the break cutoff from `Market` instead of the `reserve_market_redesign` key.
- Split `eval/analogues.py` into per-market rows under the same event keys; rows with no verified number stay `None` and are not shown to Claude.
- Parameterise prompt role text, baseline narratives and rubric keywords by the Market labels. Rescale FakeClient and synthetic data to NYISO scale (about 30 GW, not 150 GW).
- Add a NYISO loader producing the same 13-column daily panel; RT is the settlement series. Gate the 5 PJM-real-data tests by market and add a small NYISO loader test with hand-made fixtures.
- Order: market object and config, analogues, loader, docs, optional rename; run `python -m pytest -q` after each step.
- The shock key rename (`wh_onpeak_pct` to `ref_onpeak_pct`, `dom_minus_wh_usd` to `pocket_minus_ref_usd`) in the schema above is done in the agent contract with a mapping line in the prompt; if the internal names stay, translate at the agent boundary.

## 13. Decisions still needed

1. ~~Confirm solo work~~ done 2026-10-28. NYISO data use: no data-specific terms exist, only the Legal Notice; keep citing the source, aggregates only, no raw files in the repo or demo. Still open: human second rater for coherence (two LLM raters stand in), deletion of the obsolete PJM fallback files (not confirmed).
2. Is the fallback book (P1, P4, P6 on WEST only) acceptable if N.Y.C. data proves thin?
3. Pre-2016 data: include with a flag (more extremes, different regime) or cut at 22 Jun 2016 as the base case?
4. Scenario price cap: accept $5,000 as a stated assumption, or wait for the tariff check?
5. Keep `wh_*/dom_*` internally for now, or spend a day on the full rename?
6. Accept the pre-stated hypothesis that the optimizer wins on D^2 and Claude must win on coverage and coherence, or the result is reported as negative?
7. Add Jan-Feb 2026 as a fifth analogue (needs price download)?

## Multi-channel book attempt (rule v2, 2026-10-28)
Rule written in `config.py` before the scan (conditions as code: `eval/sizing.py` `failed_conditions_v2`; scan: `scripts/scan_book_v2.py`, output `outputs/book_scan_v2/scan_v2.json`). Levers: sizes on a 432-point grid (P1 in -100..100 incl. SHORT swap, P2, P3, P4, P5, P6) and fair-value option premiums (p4 = 8.29 $/MWh, p6 = 0.53 $/MWh, now set by `fit_book_params`; the scenario engine reports shock-attributable P&L so a constant premium cancels in scenario losses and only changes absolute P&L and the historical 30-day check, worst 30d = 0.67 x target). Result: NO candidate satisfies the rule. All 468 distinct breaches over 432 candidates are winter zone_volume (P5). Short-P1 books lose 54-167M at the most likely 5M-targeted point, but only in worlds beyond the plausibility ceilings (severity implausible), so they have no breaches. The failed conditions are c2 (>= 2 channels and >= 2 seasons) and b (largest-position share <= 0.60); no threshold was lowered. The v1 sizes are kept. Price-level channels would need roughly 3-5x larger positions to lose 5M in a plausible 30-day move, which contradicts condition (d) (worst historical 30-day loss <= target). Offline demo regenerated (seed 0, budget 144, 5 repeats, FAKE CLIENT): optimizer 15.4, cond-Gaussian 4.4, random 0, scripted Claude 0 breaches per repeat, all zone_volume/winter.


## Update 2026-10-28: terms and second rater
NYISO terms of use: checked online; only the Legal Notice (nyiso.com/legal-notice) exists, with no data-specific clause (no license, no ban on analysis, no attribution rule); raw data stays local, aggregates only. Second rater: Opus 5.5 blind-graded the same 18 Haiku scenarios as Sonnet 5.5; per-item agreement 72-100%, kappa 0.47-1.00 (no_contradiction weakest). LLM raters stand in for, but do not replace, the human second rater.

## Update 2026-10-29: daily factor model
Walk-forward daily-factor test (R2 for log WEST / spread): gas+load 0.47/0.11, +season 0.48/0.19, +weather 0.49/0.21, +persistence 0.68/0.42; wind, nuclear, hydro and net load add about nothing beyond persistence; solar not available in NYISO fuel mix. Integrated: harmonics in the price model, persistence tail in the shock engine (config.DAILY_PERSISTENCE; --no-persistence in run_nyiso_demo.py). Baselines now run in worker processes for live runs (results identical to sequential, about 2x faster).
