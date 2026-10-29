# NYISO real-data fit and event replay

**REAL DATA - NYISO (reference WEST, pocket N.Y.C.), fit window 2019-01-01 to 2025-12-31, panel 2019-01-01 to 2026-09-30; 2014 rows are a flagged out-of-window replay event**

All numbers below are computed by `scripts/run_replay.py` from the local panel. Nothing is from Claude or a FakeClient. q is a rank against non-overlapping 10-day windows, not a probability.

## 1. Price regression (log WEST on-peak = season intercept + b1 g + b2 l + b3 l^2)

Standard errors are Newey-West (10 lags); classical OLS errors shown for comparison.

| variant | n | R^2 | resid sd | b_gas (se) | b_load (se) | b_load2 (se) |
|---|---|---|---|---|---|---|
| full_2019 | 2557 | 0.452 | 0.468 | 0.681 (0.046) | 2.471 (0.160) | 0.035 (0.950) |
| post_indian_point_2021 | 1706 | 0.481 | 0.423 | 0.530 (0.049) | 2.681 (0.200) | -0.064 (1.003) |
| post_transmission_shortage_2023 | 779 | 0.584 | 0.321 | 0.620 (0.079) | 2.848 (0.295) | 0.072 (2.453) |

Full-window coefficients, all terms:

| term | coef | se (OLS) | se (Newey-West) | t (NW) |
|---|---|---|---|---|
| a_winter | 2.7852 | 0.0308 | 0.0657 | 42.42 |
| a_summer | 2.9159 | 0.0315 | 0.0614 | 47.53 |
| a_shoulder | 2.5241 | 0.0270 | 0.0571 | 44.19 |
| b_gas | 0.6811 | 0.0216 | 0.0457 | 14.89 |
| b_load | 2.4711 | 0.1055 | 0.1596 | 15.48 |
| b_load2 | 0.0347 | 0.6248 | 0.9504 | 0.04 |

Variant note: the Market primary break (2016-06-22) predates the 2019 fit window, so `include_pre_break=False` gives the same fit as the full window (check: identical R^2 = True). The two later variants cut the sample at the dates shown.

## 2. Residual diagnostics (full window)

| statistic | value |
|---|---|
| n | 2557 |
| sd | 0.4674 |
| skew | -0.9045 |
| excess_kurtosis | 3.4837 |
| jarque_bera_p | 0.0000 |
| autocorr_lag1 | 0.5688 |
| ljung_box_10_p | 0.0000 |
| durbin_watson | 0.8622 |
| share_abs_gt_3sd | 0.0125 |
| residual sd by season | winter 0.491, summer 0.380, shoulder 0.495 |
| price-floor hits (< $1) | {'wh_on': 1, 'rt_wh_on': 1, 'da_wh_on': 0} |

## 3. Covariance conditioning (Ledoit-Wolf, rolling window ending 2025-12-31)

cond(cov) mixes units (c is in $/MWh, the rest are logs); cond(corr) is unit-free.

| variant | season | n | window | shrinkage | cond(cov) | cond(corr) | min eig(corr) |
|---|---|---|---|---|---|---|---|
| full_2019 | winter | 451 | 2021-01-01 to 2025-12-31 | 0.129 | 638963.9 | 4.8 | 0.369 |
| full_2019 | summer | 276 | 2023-06-01 to 2025-08-31 | 0.361 | 54727.4 | 2.9 | 0.537 |
| full_2019 | shoulder | 549 | 2023-03-01 to 2025-11-30 | 0.090 | 15138.6 | 4.5 | 0.396 |
| post_indian_point_2021 | winter | 392 | 2021-12-01 to 2025-12-31 | 0.123 | 702930.0 | 5.4 | 0.351 |
| post_indian_point_2021 | summer | 276 | 2023-06-01 to 2025-08-31 | 0.357 | 54794.7 | 3.0 | 0.521 |
| post_indian_point_2021 | shoulder | 549 | 2023-03-01 to 2025-11-30 | 0.091 | 15262.3 | 4.6 | 0.390 |
| post_transmission_shortage_2023 | winter | 212 | 2023-12-01 to 2025-12-31 | 0.111 | 435532.5 | 6.1 | 0.306 |
| post_transmission_shortage_2023 | summer | 184 | 2024-06-01 to 2025-08-31 | 0.363 | 71821.4 | 3.1 | 0.513 |
| post_transmission_shortage_2023 | shoulder | 383 | 2023-11-14 to 2025-11-30 | 0.103 | 17537.1 | 5.7 | 0.318 |

## 4. Spike model

| variant | thresholds $/MWh (winter/summer/shoulder) | exceedance rate | n exceed | GPD shape | bootstrap 5-95% | GPD scale |
|---|---|---|---|---|---|---|
| full_2019 | 131.3/119.4/73.5 | 0.0254 | 65 | 0.342 | -0.004 to 0.604 | 0.266 |
| post_indian_point_2021 | 152.0/143.9/81.0 | 0.0258 | 44 | 0.387 | 0.021 to 0.625 | 0.230 |
| post_transmission_shortage_2023 | 131.7/174.1/63.6 | 0.0270 | 21 | 0.307 | -1.134 to 0.751 | 0.166 |

## 5. PCA diagnostic (do the explicit factors explain over 85% of variance?)

Block: standardized log of wh_on, wh_off, dom_on, dom_off, da_wh_on, da_wh_off. Share of the block's total variance explained by a linear projection on [1, g, l, T, s, c, d]: **0.8241** (BELOW the 0.85 target). Principal components of the block needed for 85%: 2; cumulative PC shares: 0.825, 0.895, 0.945, 0.981, 0.992, 1.000. R^2 of the factors on the first three PCs: 0.889, 0.656, 0.272. Caveat: s, c and d are built from the block's own series (log WEST on-peak less its fit, N.Y.C. minus WEST, log RT/DA), so a high share is partly by construction.

| series | share explained |
|---|---|
| wh_on | 0.9286 |
| wh_off | 0.6822 |
| dom_on | 0.8636 |
| dom_off | 0.7724 |
| da_wh_on | 0.9078 |
| da_wh_off | 0.7901 |

## 6. Pass-through coefficients: placeholders replaced by the real regression

| coefficient | placeholder (core build) | estimated (full window) |
|---|---|---|
| gas_beta | 0.6 | 0.6811 |
| load_beta1 | 2.0 | 2.4711 |
| load_beta2 | 6.0 | 0.0347 |
| offpeak_scale | 0.5 | 0.5492 |

The engine's `PassThrough` defaults in `shock.py` are unchanged (they back the synthetic tests); real-data runs must pass `PassThrough(**estimated)` (see `outputs/real/fit_summary.json`, key `passthrough`). `ScenarioEngine` accepts a `passthrough` argument for this purpose.

## 7. Book sizing (plan section 3)

Rule: keep sizes if 0.5 <= worst rolling-30d loss / 5M <= 1.0, else scale all sizes by 0.75 * 5M / worst loss. Capital 20M, target loss 5M (25% of capital). Sizes in MW: P1 100, P2 25, P3 50, P4 50, P5 140, P6 25.

| statistic | value |
|---|---|
| worst_1d_loss_usd | 1,678,175 |
| worst_10d_loss_usd | 3,172,440 |
| worst_30d_loss_usd | 3,354,880 |
| p1_30d_loss_usd | 2,918,788 |
| worst_30d_loss_over_target | 0.671 |
| n_windows_ge_target | 0 |
| worst_window_end | 2022-12-29 |
| total_pnl_usd | -2,971,476 |
| verdict | sizes kept |

P&L by position over the fit window (payoff only, no premium carry): P1 0, P2 -0, P3 184,602, P4 0, P5 -3,156,079, P6 0. The largest single contribution is P3; P4 is a long call that pays no premium in this build (payoff only), so its positive drift is a carry artefact, not a result of sizing.

## 8. Event replay

Engine = event shock (window means) through `apply_shock` on a base window (same number of days, ending 14 days before the event, event calendar imposed), pass-through from the as-of regression. Window shock: one shock for the whole event, spike days placed at random, averaged over 200 seeds. Day-by-day shock: one shock per event day. Actual = book P&L on the event's daily prices. Values in USD thousand.

### Polar vortex 2014 (2014-01-06 to 2014-01-08)  -- FLAGGED: outside the 2019 fit window, pre-2016 pricing regime

| name | actual | engine window | engine daily | gap window | rel gap window | within 30% (window) | sign ok (window) |
|---|---|---|---|---|---|---|---|
| P1 | 1,039.8 | 1,098.3 | 1,039.8 | 58.5 | 0.06 | True | True |
| P2 | 88.0 | 88.0 | 88.0 | -0.0 | -0.00 | True | True |
| P3 (immaterial) | -46.9 | -46.8 | -2.7 | 0.2 | 0.00 | True | True |
| P4 | 463.2 | 492.4 | 463.2 | 29.2 | 0.06 | True | True |
| P5 | -670.9 | -624.6 | -670.9 | 46.3 | 0.07 | True | True |
| P6 | -127.5 | -142.2 | -127.5 | -14.6 | -0.11 | True | True |
| system | 1,039.8 | 1,098.3 | 1,039.8 | 58.5 | 0.06 | True | True |
| congestion | 88.0 | 88.0 | 88.0 | -0.0 | -0.00 | True | True |
| dart (immaterial) | -46.9 | -46.8 | -2.7 | 0.2 | 0.00 | True | True |
| gas | 463.2 | 492.4 | 463.2 | 29.2 | 0.06 | True | True |
| zone_volume | -670.9 | -624.6 | -670.9 | 46.3 | 0.07 | True | True |
| tail | -127.5 | -142.2 | -127.5 | -14.6 | -0.11 | True | True |
| total | 745.7 | 865.2 | 789.8 | 119.5 | 0.16 | True | True |

### Elliott 2022 (2022-12-23 to 2022-12-24)

| name | actual | engine window | engine daily | gap window | rel gap window | within 30% (window) | sign ok (window) |
|---|---|---|---|---|---|---|---|
| P1 | 305.8 | 660.2 | 305.8 | 354.4 | 1.16 | False | True |
| P2 | 370.0 | 368.6 | 368.6 | -1.4 | -0.00 | True | True |
| P3 | -454.4 | -308.2 | -364.2 | 146.2 | 0.32 | False | True |
| P4 | 117.6 | 295.6 | 117.6 | 178.1 | 1.51 | False | True |
| P5 | -2,316.0 | -2,301.7 | -2,306.9 | 14.2 | 0.01 | True | True |
| P6 (immaterial) | -36.4 | -124.9 | -36.4 | -88.6 | -2.44 | False | True |
| system | 305.8 | 660.2 | 305.8 | 354.4 | 1.16 | False | True |
| congestion | 370.0 | 368.6 | 368.6 | -1.4 | -0.00 | True | True |
| dart | -454.4 | -308.2 | -364.2 | 146.2 | 0.32 | False | True |
| gas | 117.6 | 295.6 | 117.6 | 178.1 | 1.51 | False | True |
| zone_volume | -2,316.0 | -2,301.7 | -2,306.9 | 14.2 | 0.01 | True | True |
| tail (immaterial) | -36.4 | -124.9 | -36.4 | -88.6 | -2.44 | False | True |
| total | -2,013.3 | -1,410.5 | -1,915.5 | 602.9 | 0.30 | True | True |

### Cold Jan 2025 (2025-01-20 to 2025-01-23)

| name | actual | engine window | engine daily | gap window | rel gap window | within 30% (window) | sign ok (window) |
|---|---|---|---|---|---|---|---|
| P1 | 748.0 | 756.1 | 748.0 | 8.1 | 0.01 | True | True |
| P2 | 196.2 | 201.6 | 201.6 | 5.4 | 0.03 | True | True |
| P3 (immaterial) | 48.2 | 26.7 | 36.7 | -21.5 | -0.45 | False | True |
| P4 | 268.6 | 272.6 | 268.6 | 4.1 | 0.02 | True | True |
| P5 | -1,313.9 | -1,351.0 | -1,350.5 | -37.1 | -0.03 | True | True |
| P6 (immaterial) | -48.5 | -52.8 | -48.5 | -4.3 | -0.09 | True | True |
| system | 748.0 | 756.1 | 748.0 | 8.1 | 0.01 | True | True |
| congestion | 196.2 | 201.6 | 201.6 | 5.4 | 0.03 | True | True |
| dart (immaterial) | 48.2 | 26.7 | 36.7 | -21.5 | -0.45 | False | True |
| gas | 268.6 | 272.6 | 268.6 | 4.1 | 0.02 | True | True |
| zone_volume | -1,313.9 | -1,351.0 | -1,350.5 | -37.1 | -0.03 | True | True |
| tail (immaterial) | -48.5 | -52.8 | -48.5 | -4.3 | -0.09 | True | True |
| total | -101.5 | -146.9 | -144.2 | -45.4 | -0.45 | False | True |

### Heat Jun 2025 (2025-06-23 to 2025-06-25)

| name | actual | engine window | engine daily | gap window | rel gap window | within 30% (window) | sign ok (window) |
|---|---|---|---|---|---|---|---|
| P1 | 1,221.1 | 1,291.8 | 1,221.1 | 70.7 | 0.06 | True | True |
| P2 | 131.2 | 131.5 | 131.5 | 0.4 | 0.00 | True | True |
| P3 (immaterial) | -0.3 | -0.6 | 3.2 | -0.2 | -0.76 | False | True |
| P4 | 603.1 | 638.5 | 603.1 | 35.4 | 0.06 | True | True |
| P5 | -1,195.9 | -1,180.6 | -1,199.2 | 15.3 | 0.01 | True | True |
| P6 | -189.3 | -207.0 | -189.3 | -17.7 | -0.09 | True | True |
| system | 1,221.1 | 1,291.8 | 1,221.1 | 70.7 | 0.06 | True | True |
| congestion | 131.2 | 131.5 | 131.5 | 0.4 | 0.00 | True | True |
| dart (immaterial) | -0.3 | -0.6 | 3.2 | -0.2 | -0.76 | False | True |
| gas | 603.1 | 638.5 | 603.1 | 35.4 | 0.06 | True | True |
| zone_volume | -1,195.9 | -1,180.6 | -1,199.2 | 15.3 | 0.01 | True | True |
| tail | -189.3 | -207.0 | -189.3 | -17.7 | -0.09 | True | True |
| total | 569.8 | 673.6 | 570.4 | 103.8 | 0.18 | True | True |

### Plausibility of the realised events

As-of model = fitted on data up to the day before the event (2014: the full 2019-2025 model, flagged). Full-fit columns use the headline model (in-sample for 2022 and 2025).

| event | window worst day | D^2 as-of | q as-of | severity as-of | nearest date (as-of) | D^2 full | q full | severity full | nearest date (full) | marginals exceeded (as-of) |
|---|---|---|---|---|---|---|---|---|---|---|
| Polar vortex 2014 (FLAGGED) | 2014-01-06 | 36.5 | 0.1647 | implausible | 2021-11-18 | 36.5 | 0.1647 | implausible | 2021-11-18 | c |
| Elliott 2022 | 2022-12-24 | 316.6 | 0.0000 | implausible | 2022-08-09 | 134.0 | 0.0235 | adverse | 2022-12-24 | c, d, s |
| Cold Jan 2025 | 2025-01-20 | 17.7 | 0.1810 | ordinary | 2022-12-25 | 15.9 | 0.3529 | ordinary | 2025-01-20 | none |
| Heat Jun 2025 | 2025-06-24 | 124.1 | 0.0085 | implausible | 2022-08-09 | 63.5 | 0.0824 | ordinary | 2025-06-24 | s |

## 9. Replay verdict and diagnosis

Check: engine within 30% of actual on material rows (|actual| >= $50k, 1% of the target). 'Daily' = the event's realised daily factor vector, one shock per day (the plan 8A test); 'window' = one shock from the window means.

| engine variant | positions within 30% | channels within 30% | total within 30% |
|---|---|---|---|
| daily, fitted pass-through | 19 of 19 | 19 of 19 | 3 of 4 |
| daily, placeholder pass-through | 19 of 19 | 19 of 19 | 3 of 4 |
| window, fitted pass-through | 16 of 19 | 16 of 19 | 3 of 4 |
| window, placeholder pass-through | 16 of 19 | 16 of 19 | 1 of 4 |

Daily-averaging gap for the two positions the plan expects to be understated (engine minus actual, USD thousand; negative P&L = loss; 'understated' means the engine's absolute P&L is smaller than actual):

| event | position | actual | engine window | engine daily | window understated? | daily understated? |
|---|---|---|---|---|---|---|
| Polar vortex 2014 | P3 | -46.9 | -46.8 | -2.7 | True | True |
| Polar vortex 2014 | P6 | -127.5 | -142.2 | -127.5 | False | False |
| Elliott 2022 | P3 | -454.4 | -308.2 | -364.2 | True | True |
| Elliott 2022 | P6 | -36.4 | -124.9 | -36.4 | False | False |
| Cold Jan 2025 | P3 | 48.2 | 26.7 | 36.7 | True | True |
| Cold Jan 2025 | P6 | -48.5 | -52.8 | -48.5 | False | False |
| Heat Jun 2025 | P3 | -0.3 | -0.6 | 3.2 | False | False |
| Heat Jun 2025 | P6 | -189.3 | -207.0 | -189.3 | False | False |

The window engine understates P3/P6 in 3 of 8 cases; the expected understatement is therefore NOT uniformly confirmed (see mechanisms below).

Honest reading: the day-by-day engine passes every position and channel row and the total in 3 of 4 events; for P1, P4 and P6 that is close to a tautology, since each day's shock carries that day's own on-peak price. The informative parts are P2, P3 and P5 (spread, DA-RT, load) and the window engine, which fails Elliott P1/P3/P4 (and its tail) and, on the total, it fails Cold Jan 2025 (-45k on -101k). A 'within 30% on averaged positions' check therefore passes for the daily engine and fails for the window engine on the event that matters most (Elliott).

Mechanisms found (from the code and the tables above, not from extra data):

1. Spike placement. `apply_shock` puts spike days at random among shocked days, whereas the real spike days are specific days. When a real spike falls on a weekend (24 Dec 2022 is a Saturday: zero on-peak hours) the engine can instead place it on a weekday and book a large P1/P6 payoff that did not happen. This is why the window engine overstates P1 and P6 for Elliott while the day-by-day engine matches them.
2. P6 is overstated, not understated, by the window engine in this test (see the table). The understatement the plan expects is against hourly truth (a few hours at thousands of dollars vanish inside a 16-hour mean); here the actual side is itself a daily average, so that effect cannot show. What the window engine adds is the random placement above and the loss of cross-day detail (all spike days get the mean spike price).
3. P3 (DA-RT, off-peak). The shock moves off-peak levels through the on-peak residual times `offpeak_scale`, not through the actual off-peak move, so DA-RT dollars (which scale with the level) are off whenever off-peak behaves differently from on-peak (24 Dec 2022: off-peak RT 488 vs on-peak 672). P3 carries the largest relative errors but is immaterial (< $50k) in 3 of 4 events; in Elliott it is -454k actual vs -308k (window) and -364k (daily), 32% and 20% off. P3's sign by event (jan2014: -, elliott: -, jan2025: +, jun2025: -) is event dependent (negative when RT cleared above DA) and the day-by-day engine reproduced the sign in 3 of 4.
4. P2/P5 depend only on the 24h N.Y.C.-WEST spread and the load ratio; the engine matches them closely because the spread shift is set from the event's 24h spread (calendar-aware). Their errors are small relative to P5's size, and P5 is the largest absolute position in 2 of 4 events.
5. Pass-through placeholders (0.6 / 2.0 / 6.0 / 0.5) vs regression (gas_beta 0.681, load_beta1 2.471, load_beta2 0.035, offpeak_scale 0.549): the pass rates in the table are identical with either set, because the on-peak level residual `wh_onpeak_pct` is computed against whichever pass-through is used, so on-peak WEST levels are matched either way. The pass-through matters for scenarios proposed by the agent (where gas and load move and the residual is not back-solved) and only second-order for off-peak and DA scaling here. The quadratic load term is estimated at ~0 with a very large standard error (the placeholder 6.0 is not supported).
6. A fix made during this work: `event_to_shock` did not divide the RT/DA factor out of the on-peak level residual, although `apply_shock` multiplies RT on-peak by (1 + dart_pct); the level was double counted (2014 window P1 was 2.2x actual before the fix). It now divides it out. The 24h spread in `event_to_shock` is also calendar-aware (weekend and holiday days use off-peak only, as `book.pnl` does).

Limits of this test: actual P&L is also computed on daily averages (the panel has no hourly series), so the true hourly understatement of P3 and P6 is not measured here; the strikes K, K6, c0, R, H are fitted on the data available before each event; the 2014 base window (2014-01-13 to 2014-01-15) is a calm window after the event because the 2014 file covers January only; the three-day 2014 window (6 to 8 Jan) is a choice, the verified numbers are for 7 Jan.
