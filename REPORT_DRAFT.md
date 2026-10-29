# Reverse stress testing agent on a NYISO power book: draft (numbers from outputs/ only)

## Question
Starting from a loss of at least $5M (25% of $20M), which are the most plausible scenarios that cause it? Claude proposes coherent scenarios as typed shock vectors (no price forecasts); a factor engine computes P&L by position and channel; plausibility is D^2 and rank q against 2019-2025 history (a rank, not a probability).

## Setup
NYISO, reference WEST, load pocket N.Y.C., 6-position book, panel 2019-01-01 to 2026-09-30, fit window 2019-2025. Claude Haiku 5.5, 5 live repeats (seeds 0-4), schema + hard rules + analogue lookup + marginal ceilings. Baselines: random, SLSQP optimizer, conditional-Gaussian (Sparviero & Viola).

## Final engine: daily factor model (outputs/live_daily_sonnet, Sonnet 5.5, seed 0, 5 repeats)
Engine change (2026-10-29): the price model gains two annual harmonics and load x first harmonic, and a shock now persists after it ends (price-level and spread effects decay as phi^k, phi about 0.55 and 0.59, AR(1) of the residual factors s and c). Motivation: a walk-forward daily-factor test (scripts/daily_factor_model.py, outputs/daily_model) gave out-of-sample R2 0.68 for log WEST and 0.42 for the N.Y.C.-WEST spread with persistence versus 0.47 and 0.11 without; fuel-mix factors (wind, nuclear, hydro) added almost nothing.
| Arm | Breaches per repeat | Median D^2 | Engine calls |
|---|---|---|---|
| Claude (Sonnet 5.5) | 11.2 +- 0.4 | 156 | 42 (repeat 0) |
| Optimizer | 8.0 +- 1.4 | 93 | 144 |
| Cond-Gaussian | 0.2 +- 0.4 | 89 | 144 |
| Random | 0 | n/a | 144 |
59 of 176 scenarios ranked-eligible (all zone_volume; outputs/RANKED_SCENARIOS_daily_sonnet.md). Blind Opus 5.5 coherence 0.664 (causal 43/59, shocks explained 27/59, duration 57/59, analogue 33/59, no contradiction 36/59). Tokens 0.86M in / 0.32M out.
Caveats that matter: (1) the persistence tail makes the same shock lose about 15-20% more, so the 5M target is reachable by ordinary worlds and the cond-Gaussian point is no longer a tail event; (2) the book was NOT recalibrated: the pre-declared sizing rule v1 re-applied on this engine (48 candidates, outputs/book_scan_v3) admits no candidate (best 4 distinct breaches in the weakest seed, rule needs 5; all fail conditions b and c), and the user chose to keep the sizes and the 5M target; (3) Claude's lead on breach count over the optimizer is therefore not comparable to the earlier runs, and Claude still has the worst D^2 and uses 42 engine calls against 144. With persistence off (harmonics only, offline): optimizer 11.6, cond-Gaussian 4.4 breaches.

## Earlier engine (season intercepts only, snap-back shocks): Generator comparison: Sonnet 5.5 vs Haiku 5.5 (same protocol, seed 0, 5 parallel repeats)
| | Sonnet 5.5 (outputs/live_full_sonnet, 12 min) | Haiku 5.5 (outputs/live_full, 4.7 min) |
|---|---|---|
| Breaches per repeat | 9.8 +- 2.8 | 3.6 +- 2.3 |
| Median D^2 | 159 | 145 |
| Ranked-eligible / scenarios | 55 / 170 | 18 / 165 |
| Stated loss within 20% of engine loss | 96% | 78-95% |
| Coherence, same judge (Opus 5.5, blind) | 0.578 (55) | 0.611 (18) |
| Tokens in / out (cache dir) | 0.83M / 0.31M | 1.04M / 0.52M (includes reused calls) |

Optimizer 15.4 and conditional-Gaussian 4.4 breaches in both runs (same baselines). Sonnet finds about 2.7x more breaches than Haiku in this draw (one seed; dispersion sd 2-3), with no gain in coherence (0.578 vs 0.611, Opus-graded, different sample sizes) and no gain in D^2. All 55 Sonnet ranked scenarios lose mostly on zone_volume.

Anchoring ablation on Sonnet 5.5 (outputs/live_anchoring_sonnet, one run): target shown, 33 scenarios, median loss $6.70M, 100% above target, 21% within 20%, 10 breaches; target hidden, 33 scenarios, median loss $8.64M, 88% above target, 18% within 20%, 3 breaches. Unlike Haiku (target hidden: median $1.95M, 0 breaches), Sonnet without a target does not fall short: it proposes harsher worlds, and fewer count as breaches because more fall beyond the plausibility limits (reading of the counts, not separately verified). So the anchoring seen in Haiku is not a general fact about Claude models; for Sonnet the target mainly restrains severity.

## Haiku result: single full run (outputs/live_full, seed 0, 5 repeats run in parallel, 4 min 40 s)
| Arm | Breaches per repeat (mean +- sd) | Median D^2 | Engine calls |
|---|---|---|---|
| Claude | 3.6 +- 2.3 | 145 | 36 (repeat 0) |
| Optimizer | 15.4 +- 2.9 | 93 | 144 |
| Cond-Gaussian | 4.4 +- 0.9 | 105 | 144 |
| Random | 0 | n/a | 144 |

165 scenarios, 18 ranked-eligible (all zone_volume; outputs/RANKED_SCENARIOS_full.md). Blind Sonnet 5.5 coherence on those 18: mean 0.689 (analogue 8/18, no_contradiction 10/18, shocks_explained 12/18, causal_chain 14/18, duration 18/18; outputs/coherence_llm_full). Token totals in live_cache include 57 calls reused from an interrupted sequential launch.

## Supporting result: five separate live runs (seeds 0-4, one repeat each)
Claude averaged 7.6 breaches per repeat (10, 6, 9, 9, 4) but the single full run gives 3.6: the Claude arm's breach count is unstable across draws (sd about 2-3), so no single mean should be quoted as its level. Both sets agree on the ordering optimizer > Claude ~ cond-Gaussian > random for breaches and on optimizer < cond-Gaussian < Claude for D^2.

## Results of the separate runs (outputs/live_haiku_*/comparison_table.csv)
| Arm | Breaches per repeat (mean) | Median D^2 | Engine calls |
|---|---|---|---|
| Claude | 7.6 (10, 6, 9, 9, 4) | 129 | 36-53 |
| Optimizer | 17.8 | 94 | 144 |
| Cond-Gaussian | 4.8 | 105 | 144 |
| Random | 0 | n/a | 144 |

- Hypothesis stated in advance: optimizer and conditional-Gaussian win on D^2, Claude on coverage and coherence. D^2 ordering confirmed. Driver coverage: Claude 0.31 vs 0.20 for both structured arms (supports the coverage claim); channel coverage is 0.17 for every arm (book-limited). Coherence: LLM judge (Sonnet 5.5, blind, different model from the Haiku generator) on the 41 ranked scenarios, below; the pre-registered human rater is still [PENDING].
- Gate: 1 of 219 scenarios rejected by a hard rule (sign_consistent). Soft penalty driver_class_not_overused fired on 77% in repeat 0.
- Coherence (outputs/coherence_llm/coherence_llm.csv, 41 ranked scenarios, rubric 8B combined with mechanical checks): causal_chain 35/41, shocks_explained 32/41, duration_matches 41/41, analogue relevant 31/41, no_contradiction 28/41, mean total 0.815. An LLM rater is not the human second rater; it cannot verify analogue numbers.
- Severity-anchoring ablation (Haiku 5.5, outputs/live_anchoring/ablation_anchoring.csv, one run, seed 0): with the $5M target in the prompt, 63 scenarios, median engine loss $5.77M, 52% within 20% of target, 73% above target, 11 breaches; without it, 24 scenarios, median loss $1.95M, 17% within 20%, 12.5% above target, 0 breaches. Claude's severity follows the stated target; without it the proposals do not reach the tail. The arms are not the same task (no goal vs a goal), so this shows dependence on the target, not that scenarios are fake.
- Stated vs implied loss: median relative error 7-9%; stated losses sit just above target (severity anchoring suspected, ablation not run).
- Ranked deliverable: 41 of 219 scenarios eligible, all losing mostly through P5 zone_volume (winter N.Y.C.-WEST spread story). See outputs/RANKED_SCENARIOS.md.

## Honest reading
Claude has no edge on D^2 nor on raw breach count; its per-call yield is higher but it used fewer calls, so budgets are not equal. Any claimed edge rests on driver coverage and coherence, the latter ungraded. Multi-channel coverage is a negative result: 0 of 432 candidate books admissible under the pre-declared rule v2; worst historical 30-day loss is $3.22M.

## Factors: what they are and how they relate (outputs/factors, scripts/factor_report.py)
The plausibility score uses five daily factors: g (log Henry Hub), l (log peak load versus its seasonal normal), s (residual of the log WEST on-peak price after gas, load, season harmonics and load x season), c (N.Y.C. minus WEST on-peak spread, $/MWh) and d (log real-time over day-ahead at WEST). Means and covariances are estimated per season (winter 632, summer 644, shoulder 1,281 days, 2019-2025).

Correlations of deviations from the season mean (figure: outputs/factors/corr_by_season.png):
| Pair | Winter | Summer | Shoulder | Reading |
|---|---|---|---|---|
| c-l | 0.42 | 0.19 | 0.10 | Cold raises load and the city spread together, only in winter: the mechanism behind the winter N.Y.C.-WEST scenarios |
| g-c | 0.38 | 0.30 | 0.42 | Gas and the spread move together |
| s-d | 0.58 | 0.71 | 0.68 | A price above its fundamentals goes with real time above day-ahead |
| s-c | 0.18 | -0.03 | -0.48 | Sign flips with the season |

Principal components of the five standardized factors: 34.6%, 28.2%, 17.9%, 12.7%, 6.6% (cumulative 34.6%, 62.8%, 80.7%, 93.4%). The five factors are not nearly one-dimensional: four components are needed for 93%. The earlier plan statement that a few components explain more than 85% of the variance referred to the price block and is not supported for this factor set; the covariance is therefore estimated on all five factors and not on a reduced set.

Most extreme days by D^2 are outside winter (outputs/factors/worst_d2_days.csv): 29 Mar 2022 (D^2 356), 20 and 21 Nov 2022 (343 and 266), 31 May 2022 (154), 29 Apr 2021 (149), all in the shoulder season. The tail of the fitted history is therefore a gas and price-residual story in 2022, not the cold events the scenarios are about.

Daily factor model (walk-forward R^2, scripts/daily_factor_model.py): see the table in the daily model section; persistence is the strongest daily factor; wind, nuclear and hydro add almost nothing; solar is not in the NYISO fuel mix.

## Limits
- NYISO terms (checked online 2026-10-28, nyiso.com/legal-notice): the only legal page linked from the site footer; no terms-of-use or data policy page exists (the /terms-of-use URL returns 404). It grants no license or ownership in site content, prohibits stand-alone reuse of images and video, requires written permission for the NYISO name and logo, disclaims accuracy, and says nothing specific about data, derivative use, attribution or automated access. No explicit permission or prohibition for market-data analysis; this project cites NYISO as source, uses the data for coursework, keeps raw files local and publishes aggregates only. Not legal advice; ask the instructor if redistribution is intended.
- Second rater: no human grader. Two LLM raters (Sonnet 5.5 and Opus 5.5, blind, same 18 Haiku scenarios) agree: causal_chain 89% (kappa 0.68), shocks_explained 83% (0.67), duration 100% (1.00), analogue 94% (0.89), no_contradiction 72% (0.47, weakest). Opus is the stricter judge. These are LLM raters, not the pre-registered human second rater, which stays [PENDING].
One model (Haiku), no Sonnet generating arm (Sonnet used only as blind coherence judge), anchoring ablation is a single run, human coherence grading [PENDING], daily averaging understates hourly spikes, price cap $5,000 a stated assumption, solo work to confirm with the instructor.

## 10-minute demo outline
1. Objective and book (2 min). 2. One live scenario end to end: narrative, shock vector, P&L by channel, D^2/q (3 min). 3. Arms table and hypothesis (2 min). 4. Negative result and limits (2 min). 5. Audit log and gate (1 min).
