# revstress: reverse stress testing of a NYISO power book with an LLM agent

Python package `revstress` for the IEOR 4723 project (plan: `../PROJECT_PLAN_NYISO_REVERSE_STRESS.md`; the folder name `pjm_revstress` is
historical, the package started as a PJM prototype and is now market-aware with NYISO as the target). A six-position book
(P1 WEST on-peak swap, P2 N.Y.C.-WEST congestion, P3 DA-RT, P4 heat-rate call, P5 N.Y.C. retail obligation, P6 short tail option) is
stressed by (a) a Claude agent loop, (b) random search, (c) an SLSQP optimizer and (d) a conditional-Gaussian most-likely-scenario
baseline, at equal engine budget, and compared on distinct breaching scenarios (primary), then plausibility (D^2, rank q), driver and
channel coverage, rule passing, coherence and gate rejection. Internal column names stay `wh_*` (reference zone WEST) and `dom_*`
(load pocket N.Y.C.); see `INTERFACES.md`. Stated hypothesis (plan): the optimizer and the conditional-Gaussian win on D^2; Claude must
win on coverage and coherence, otherwise the result is reported as negative.

## What is real, what is scripted, what is not done

Real (computed from public data, offline):
- Data: NYISO MIS WEST and N.Y.C. hourly LBMP (real-time settlement and day-ahead) and NYCA load, EIA Henry Hub, NOAA degree days;
  daily panel `data/processed/nyiso_panel.csv` (2019-01-01 to 2026-09-30, 2,811 days, 0.67% of calendar days missing) and a flagged
  2014 replay panel. Event numbers of the plan section 8A table are reproduced within 0.13% (`data/processed/nyiso_event_validation.csv`).
- Engine: shock -> daily path -> six-position P&L (`shock.py`, `book.py`), NERC-holiday and weekend aware, scenario price cap $5,000/MWh
  (a STATED ASSUMPTION, not a NYISO number; the current tariff offer cap was not verified).
- Risk fit on 2019-01-01 to 2025-12-31: price regression, robust seasonal covariance, spike model, plausibility score (D^2, q), regression
  pass-through (`eval/diagnostics.estimate_passthrough`). Outputs in `outputs/real/` (`diagnostics.md`, `fit_summary.json`, replay figures).
- Event replay (Jan 2014 flagged out of the fit window, Elliott 2022, Jan 2025, Jun 2025): `outputs/real/replay_table.csv`.
- Baselines (random, optimizer, conditional-Gaussian), metrics, ablation plumbing, gate statistics, run manifest.

Scripted (not results): the Claude arm of `run_nyiso_demo.py` is a `FakeClient` returning canned scenario templates. Everything it
touches is stamped `FAKE CLIENT - not Claude results` (every CSV `label` column, every JSONL row, the PNG title, `NOTICE.txt`,
`manifest.json`). The prompt-version and anchoring ablation tables are plumbing only: the fake client ignores the prompt, so the arms
cannot differ. With the canned scenarios the Claude arm finds no breach at the 5M target in the demo (offline run, seed 0, budget 144, 5 repeats: random 0, optimizer 15.4, conditional-Gaussian 4.4 mean distinct breaches per repeat), and the agent stops early (two empty
iterations), so the equal budget is only 24 engine calls per repeat. These tables must not be quoted as findings.

Not done:
- Live Claude runs (never executed; first live run is for the user to trigger, see below).
- Human coherence grading and the second rater (the `coherence` column is the automated rubric checks only).
- Final report numbers (tau = 1.0 z-unit, spike overlay and pass-through sizes remain placeholders or assumptions to be finalised).
- Masking test, post-cutoff test, with/without-pre-2016-data runs (the 2019 fit window starts after the 2016-06-22 break).
- The `anthropic` package is only needed for live calls and was never exercised against the API.

## Book sizes and loss target

`config.LOSS_TARGET_USD` is the plan's 5,000,000 USD (25% of the 20M allocated capital). The six positions and their formulas are
unchanged; the SIZES were re-set (plan section 3 calls them a starting calibration): P1 100 MW, P2 25 MW, P3 50 MW, P4 50 MW, P5 140 MW,
P6 25 MW (was 50, 50, 25, 100, 200, 25). Why: with the starting book the conditional-Gaussian most-likely 5M world has rank q about 0.075
(above the 5% cutoff), so no arm could breach, and an earlier build hid this by moving the target to 7M (fragile: 6M gave 2 breaches, 8M
gave 3). The sizes were chosen by a rule written in the `config.py` comment BEFORE the scan (code: `eval/sizing.py`): 93 candidate size vectors,
conditional-Gaussian arm, seeds 0-2, budget 144 per season, fit window 2019-2025, tau 1.0. The rule asks (a) at least 5 distinct breaches
per seed, (b) largest position at most 60% of net loss, (c) at least 2 largest-loss channels and 2 seasons, (d) worst historical
rolling-30d loss between 50% and 100% of the target. No candidate satisfies (b) or (c); the rule's stated fallback was applied (relax (c),
then (b)): 11 candidates satisfy (a) and (d), and the winner has 6, 7, 6 distinct breaches in seeds 0, 1, 2 (worst historical 30-day loss
3.22M = 64% of the target). Result at the chosen book (demo, seed 0, 5 repeats, 36 engine calls per seed family): conditional-Gaussian 4.4
and optimizer 15.4 distinct breaches per repeat, random 0, scripted Claude 0.

What this does NOT achieve (stated plainly): every breach is still one scenario family, a winter cold-snap spread blow-out (N.Y.C.-WEST
about +210 $/MWh for 7 days, load +10%), with P5 losing 110% of the net loss and the P2 hedge giving back 17%. The other channels cannot carry
a 5M loss in this engine: P1 is capped by the price floor (a 200 MW swap loses about 1.1M even when WEST on-peak falls 95%), P4 is a long call
with no premium (its loss is bounded by the base intrinsic value), P3 is offset by the gains of P1 and P4 in the same factor move, and P6 spike
worlds are either ordinary by rank (winter, q about 0.15 to 0.20) or beyond the marginal limits (summer, shoulder). Summer and shoulder
cond-Gaussian points hit the temperature or marginal limits (they fall with load), so the breach is winter only.

## Optimizer baseline (v2, equal budget)

`baselines/optimizer.py` was rebuilt as a fair competitor (details in its docstring). It warm-starts from the conditional-Gaussian linearised
point using its own engine calls, polishes with SLSQP (iteration cap 200) using Broyden-updated derivatives of loss, engine D^2 and the robust
z of the five factors (about one engine call per iteration), imposes inside the optimisation the tail condition (engine D^2 above the value that
gives rank q < 5%), the season's marginal limits, sign consistency (cold_snap needs gas >= 0) and an adaptive cap on the load factor for the
temperature limit T (bisection from the feasible side), and spends the rest of the SAME budget on restarts. With the plausibility inputs of
`pipeline.plausibility_kwargs` it is a tail-constrained most-likely-scenario finder, so it finds more breaches than the plain conditional-Gaussian
(which stops at the minimum-D^2 point), about 46% of its evaluated points are implausible (line-search wander, counted in its rule-pass share), and
it finds breaches even at the old sizes (11 to 13 per seed in the scan), so part of the old "no arm breaches" was the weak optimizer, not only the
book. `warm_start=False` runs the original version. Fairness caveat: the engine budget is equal, but this arm is given the risk model's tail threshold and marginal limits, which the plain conditional-Gaussian arm does not use.

## Sensitivity of the breach count

`eval/metrics.sensitivity_table` (wired into `run_nyiso_demo.py` as `sensitivity.csv`) recomputes q against historical windows of 5, 10 and 14
days and counts distinct breaches with tau 0.5, 1.0 and 2.0 z-units, with the weakest-breach q (the largest q among the distinct breaches).
At the demo run (10-day window, tau 1.0): conditional-Gaussian 4.4, optimizer 15.4 per repeat; with tau 0.5 / 2.0 the conditional-Gaussian count
is 16.4 / 2.0 (optimizer 20.2 / 6.8); its weakest q is 0.035 at the 10-day window and 0.049 at 14 days, so the breach is close to the 5% cutoff
under longer windows. The tau and the window length are still placeholders.

## Install and run

Python 3.14 with numpy, pandas, scipy, scikit-learn, matplotlib, jsonschema, pytest. Run from this directory. Scripts that import
pandas must be run as `python -E -P script.py` on this machine (plain `python -I` fails to import pandas); the scripts add the package to `sys.path` themselves.

```
python -m pytest -q .                                       # tests, zero network
python -E -P run_nyiso_demo.py --dry-run                    # small wiring check (budget <= 21, repeats <= 2), writes outputs/nyiso_demo_dry_run/
python -E -P run_nyiso_demo.py --seed 0 --budget 144 --repeats 5   # full offline run, writes outputs/nyiso_demo/
python -E -P run_nyiso_demo.py --fallback-book              # reduced book P1, P4, P6
python -E -P scripts/run_replay.py                          # real-data fit and event replay, writes outputs/real/
python -E -P run_synthetic_demo.py --dry-run                # legacy PJM-scale SYNTHETIC demo (outputs/dry_run/)
python -m revstress.agent.loop --dry-run --market NYISO --driver large_load_shortfall   # print the seed prompt and cache key
```

`run_nyiso_demo.py` options: `--seed`, `--budget` (agent engine evaluations per repeat; baselines match it per seed), `--repeats`,
`--dry-run`, `--fallback-book`, `--loss-target-usd`, `--out`, `--no-ablations`, `--live`, `--i-understand-cost`.

Outputs in `outputs/nyiso_demo/`: `scenarios.jsonl` (all arms and repeats; Claude rows carry agent shock keys, baseline rows engine keys),
`audit_log*.jsonl` (prompts, responses, rule verdicts, engine numbers; one file per repeat), `comparison_table.csv` (arm table, mean and sd over
repeats), `repeat_dispersion.csv`, `sensitivity.csv` (breach count and weakest-breach q by window length 5/10/14 days and tau 0.5/1/2), `gate_rejection.csv` (per rule, per run, hard and soft), `stated_vs_implied.csv`, `ablation_anchoring.csv`,
`ablation_prompt_versions.csv` (plumbing only with the fake client), `pnl_waterfall.png` (P&L by position of the top agent scenario),
`NOTICE.txt`, `manifest.json` (data hashes and download dates, config, model, seed, prompt hash, package digest; check with
`revstress.manifest.verify_manifest`). Equal budget means equal engine evaluations: per seed, the agent's engine-call count is the budget of each baseline in
that seed's season (seeds are `Market.seed_families`: cold_snap, heat_wave, gas_supply, large_load_shortfall). Distinct breaches are counted in robust
z units of the core factors (tau = `config.DISTINCT_TAU_Z`) by both the loop and the metrics.

Code path: `revstress/pipeline_real.py` (`run_real_pipeline`: fit 2019-2025 -> `ScenarioEngine` -> agent loop with an injected client -> baselines at
equal budget with repeats -> metrics -> ablations) and `revstress/pipeline.py` (engine class and the legacy SYNTHETIC pipeline). Pipeline functions set
`config.MARKET = "NYISO"` for the call and restore it afterwards.

## Running Claude live (for the user to do; the build never makes live calls)

1. Set the key in your own environment, never in a file or in code: PowerShell `$env:ANTHROPIC_API_KEY = "..."` (current session only) or
   bash `export ANTHROPIC_API_KEY=...`. `ClaudeClient` reads `ANTHROPIC_API_KEY` from the environment only. Install the SDK once: `pip install anthropic`.
2. Dry-run first (free): `python -m revstress.agent.loop --dry-run --market NYISO --driver cold_snap` prints the exact prompt and cache key.
3. Cost: about 5-7k input and 1.5k output tokens per call, about 48 calls (4 seeds x 12 iterations) and about 350k tokens per repeat; the plan asks for at
   least 5 repeats per arm, so a full live comparison is about 1.75M tokens. Check current pricing before running; the code does not hard-code a price.
   Start with one repeat: `--repeats 1`.
4. Run: `python -E -P run_nyiso_demo.py --live --i-understand-cost --repeats 1 --out outputs/nyiso_live`. Without `ANTHROPIC_API_KEY` or without
   `--i-understand-cost` the program refuses and exits with code 2. Responses are cached under `<out>/live_cache` (the call cap is `repeats x 48 + 10`);
   the ablations are skipped in live mode (run `loop.run_target_ablation` deliberately if wanted; it doubles the cost).
5. Live outputs are labelled `LIVE CLAUDE | REAL DATA - NYISO ...`; the baselines are computed on the same real data and engine. Keep the audit log and manifest.
   Grade coherence by hand on shuffled narratives (`eval.rubric.blind_order`) before quoting any coherence number.

## Updating the data

Raw files stay local in `data/raw` (git-ignored; NYISO terms of use were not located, so do not publish raw files; publish aggregates with citation only).
1. NYISO prices, load and NOAA (at most 1 request per second, resumable, hashes recorded in `data/raw/nyiso_prices/MANIFEST.json`):
   `python -E -P scripts/run_fetch_nyiso.py --start 2019-01 --end 2026-09` (`--end` is the last complete month). NYISO corrects recent months after the
   fact (the plan notes 05-2025 and 06-2025 were updated on 07/07/25), so re-download the final months and re-hash before the final run.
2. Henry Hub: save the EIA daily spot series as `data/raw/eia_gas_ice/hh_daily_2013-12_onward_parsed.csv` (columns `date`, `hh_usd`).
3. Rebuild the panel and its manifest: `python -E -P scripts/build_nyiso_panel.py --end 2026-09-30` (writes `data/processed/nyiso_panel.csv`,
   `nyiso_panel_2014_replay.csv`, `nyiso_event_validation.csv`, `nyiso_panel_manifest.json`).
4. Refit and replay: `python -E -P scripts/run_replay.py`; then rerun the demo. Check `verify_manifest(outputs/<run>/manifest.json)` reports `ok`.
The fit window is fixed in `pipeline_real.FIT_START/FIT_END` (2019-01-01 to 2025-12-31); later data are never used in the fit.

## Directory map

```
revstress/config.py          constants, MARKET flag, FALLBACK_BOOK flag
revstress/market.py          Market objects (PJM default, NYISO): zone labels, cap, breaks, analogues, seed families
revstress/panel.py, book.py, shock.py, synthetic.py   panel contract, six-position P&L, shock engine, SYNTHETIC generator
revstress/data/              NYISO downloader and loader (nyiso.py, fetch_nyiso.py); legacy PJM-era EIA-930 and fallback loaders
revstress/risk/              factors, regression, robust seasonal covariance, spike model, plausibility scoring
revstress/agent/             prompts v1-v3, schema, hard rules and soft penalties, client + FakeClient, agent loop (+ anchoring ablation)
revstress/baselines/         random, SLSQP optimizer (warm start + plausibility constraints), conditional-Gaussian (Sparviero and Viola), shared evaluator and rules
revstress/eval/              metrics (+ sensitivity table), stated-vs-implied, gate stats, replay, diagnostics, sizing (book-size selection rule), rubric, analogue tables
revstress/manifest.py        pinned-input run manifest and verifier
revstress/pipeline.py        ScenarioEngine and the SYNTHETIC pipeline;  revstress/pipeline_real.py  real-panel pipeline
run_nyiso_demo.py            NYISO demo CLI;  run_synthetic_demo.py  legacy SYNTHETIC demo
scripts/                     fetch_nyiso, build_nyiso_panel, run_replay
tests/                       unit and integration tests (hand-made fixtures; zero network)
INTERFACES.md                data contract and function signatures; DATA_EXPLORATION.md  data findings
```

## Week-0 verification checklist (plan section 10) and go/no-go gate

Go/no-go gate (plan section 10): (i) 84 months of 2019-2025 download for the three products: DONE (no download failures; no month without hourly
data); (ii) WEST and N.Y.C. present in every month: DONE; (iii) DST days handled: DONE (loader tests, 25-row and 23-row days); (iv) event replays reproduce the
section 8 table within 1%: DONE (largest deviation 0.12%, `nyiso_event_validation.csv`); (v) load sum reproduces the four official peaks: DONE (under 1 MW).

| # | Item | Status |
|---|---|---|
| 1 | NYISO terms of use / redistribution for MIS data | NOT DONE (text not located; raw files kept local, aggregates only) |
| 2 | Current tariff offer cap and bid limits | NOT DONE ($5,000/MWh scenario cap is a stated assumption) |
| 3 | CHPE in-service status and date | NOT DONE (listed as an unverified break, no date used) |
| 4 | Elliott daily gas, 23-27 Dec 2022 | NOT DONE (basis is a stated shock, no daily-basis claim) |
| 5 | NYISO wording of hour-beginning stamps | NOT DONE (stamps read as hour-beginning, assumption) |
| 6 | NERC holiday handling for on-peak days | DONE (`panel.onpeak_day_flags`, `is_onpeak_day` column, used by the book) |
| 7 | Every month 2019-2025 downloads cleanly | DONE (all months present, hashes in the manifest) |
| 8 | Structural-break cutoff (2016-06-22) against price behaviour | NOT DONE (cutoff is configured; it predates the 2019 fit window, so it has no effect on the headline fit; later breaks compared as variants in `outputs/real/`) |
| 9 | EIA-930 balancing-authority code for NYISO | NOT DONE / not needed (the NYISO panel does not use EIA-930) |
| 10 | Position sizes against N.Y.C. and WEST liquidity | PARTLY (sizes re-set by the pre-stated scan rule and checked on the fit window with `diagnostics.sizing_check` at the 5M target: worst 30-day loss 3.22M = 64% of target, `outputs/real` regenerated at these sizes; liquidity not checked) |
| 11 | Event-day maximum LBMP and shortage-interval counts (2014, 2025) | NOT DONE (left `None`, not shown to Claude) |
| 12 | Jan-Feb 2026 cold spell prices and load | PARTLY (the prices are in the panel through 2026-09-30; not analysed as a fifth analogue) |

Also open from the plan: confirm solo work with the instructor (not a code item).

## Known limitations

- Daily averaging understates hourly spikes (P3 and P6); q is a rank against about 250 non-overlapping 10-day windows, not a probability.
- Scenario T (hdd/cdd) is derived from the load shock through a fitted load-vs-degree-day slope (`shock.DegreeDaySlopes`), a stated simplification.
- NYISO gas basis (`ny_gas_basis_usd`) is a stated shock; `Market.gas_basis_usd` defaults for NYISO are placeholders.
- The mechanical coherence checks use the rubric keyword lists (extended with WEST / N.Y.C. / large-load words); they are a screen, not a grade.
- Panel rows after 2026-06-30 are partly missing at the source (days dropped by the loader, see `nyiso_panel_manifest.json`); the fit never uses them.

## Multi-channel book attempt (rule v2, 2026-10-28)
Rule written in `config.py` before the scan (conditions as code: `eval/sizing.py` `failed_conditions_v2`; scan: `scripts/scan_book_v2.py`, output `outputs/book_scan_v2/scan_v2.json`). Levers: sizes on a 432-point grid (P1 in -100..100 incl. SHORT swap, P2, P3, P4, P5, P6) and fair-value option premiums (p4 = 8.29 $/MWh, p6 = 0.53 $/MWh, now set by `fit_book_params`; the scenario engine reports shock-attributable P&L so a constant premium cancels in scenario losses and only changes absolute P&L and the historical 30-day check, worst 30d = 0.67 x target). Result: NO candidate satisfies the rule. All 468 distinct breaches over 432 candidates are winter zone_volume (P5). Short-P1 books lose 54-167M at the most likely 5M-targeted point, but only in worlds beyond the plausibility ceilings (severity implausible), so they have no breaches. The failed conditions are c2 (>= 2 channels and >= 2 seasons) and b (largest-position share <= 0.60); no threshold was lowered. The v1 sizes are kept. Price-level channels would need roughly 3-5x larger positions to lose 5M in a plausible 30-day move, which contradicts condition (d) (worst historical 30-day loss <= target). Offline demo regenerated (seed 0, budget 144, 5 repeats, FAKE CLIENT): optimizer 15.4, cond-Gaussian 4.4, random 0, scripted Claude 0 breaches per repeat, all zone_volume/winter.
