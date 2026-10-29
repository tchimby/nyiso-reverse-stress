# revstress interfaces

Package `revstress` (run tests from this directory: `python -m pytest -q`; `pytest.ini` sets `pythonpath=.`).
Units: prices $/MWh, gas $/MMBtu, power MW, time days. On-peak = 16 h, off-peak = 8 h. `*_pct` are percent (60 = +60%).
No network or API calls anywhere in this package. Claude calls must read `ANTHROPIC_API_KEY` from the environment.

## Data contract: daily panel (`revstress.panel`)

One row per calendar day. Columns (all numeric except `date`):

| column | meaning | unit |
|---|---|---|
| date | datetime64[ns], strictly increasing, unique | |
| wh_on, wh_off | Western Hub RT on-/off-peak daily average (settlement price; MUST equal rt_wh_on / rt_wh_off) | $/MWh |
| dom_on, dom_off | Dominion on-/off-peak daily average (DOM hub is the zone proxy for P5) | $/MWh |
| da_wh_off, rt_wh_off, da_wh_on, rt_wh_on | Western Hub DA and RT averages | $/MWh |
| load_peak_mw | daily peak metered load | MW |
| hh_usd | Henry Hub spot | $/MMBtu |
| hdd, cdd | degree days, >= 0 | degF-day |

Optional extra columns are allowed (e.g. `synthetic_source`, `load_normal_mw` = seasonal-normal peak load, MW; if present it overrides the scalar normal in `pnl` and `apply_shock`).
Fallback book (P1, P4, P6) needs only `date, wh_on, hh_usd`.

```python
PANEL_COLUMNS: tuple[str, ...]                      # the 13 columns above, in order
FALLBACK_REQUIRED_COLUMNS: tuple[str, ...]          # ("date", "wh_on", "hh_usd")
class PanelError(ValueError)

validate_panel(df, fallback: bool | None = None, check_settlement: bool = True, tol: float = 1e-6) -> pd.DataFrame
    # returns df unchanged; raises PanelError on missing columns, NaN/inf, non-datetime date,
    # non-strictly-increasing dates, negative load/hdd/cdd/hh, wh_on != rt_wh_on or wh_off != rt_wh_off (full book).
    # fallback=None reads config.FALLBACK_BOOK.
season_labels(dates) -> np.ndarray[str]             # 'winter' | 'summer' | 'shoulder'
gas_price_usd(df, basis: Mapping[str, float] | None = None) -> np.ndarray   # hh_usd + seasonal basis, $/MMBtu
resolve_load_normal(df, default_mw: float | None) -> np.ndarray              # MW per row: column > default > median(load_peak_mw)
panel_window(panel, start, horizon_days: int) -> pd.DataFrame                # horizon_days rows from first date >= start; copy
```

## `revstress.config` (constants)

`ON_PEAK_HOURS=16, OFF_PEAK_HOURS=8, DAY_HOURS=24`, `ALLOCATED_CAPITAL_USD=20e6`, `LOSS_TARGET_USD=5e6` (the plan's 25% of capital; the sizes were re-set instead of moving the target, see the BOOK-SIZE SELECTION RULE and RESULT comments in `config.py`),
`ENERGY_COMPONENT_CAP_USD=3700.0`, `POSITION_SIZES_MW` (P1 100, P2 25, P3 50, P4 50, P5 140, P6 25; the plan's starting book was 50, 50, 25, 100, 200, 25), `POSITIONS`,
`FALLBACK_POSITIONS=("P1","P4","P6")`, `FALLBACK_BOOK=False` (flag; read at call time, so tests can monkeypatch),
`POSITION_CHANNEL` (P1 system, P2 congestion, P3 dart, P4 gas, P5 zone_volume, P6 tail), `CHANNELS`,
`HEAT_RATE_MMBTU_PER_MWH=8.0, VOM_USD_PER_MWH=3.0, SPIKE_STRIKE_QUANTILE=0.99, RETAIL_ZONE="DOM"`,
`GAS_BASIS_USD` (winter 1.50, summer 0.30, shoulder 0.90: stated ASSUMPTIONS, shoulder is a midpoint),
`SEASON_MONTHS, MONTH_TO_SEASON, SEASONS`, `FACTOR_NAMES=("g","l","T","s","c","d")`, `GAUSSIAN_CORE_FACTORS=("g","l","s","c","d")`,
`SHOCK_KEYS`, `NEUTRAL_SHOCK`, `DRIVER_CLASSES`, `STRUCTURAL_BREAKS` (reserve redesign 2022-10-01; gas shift window 2021-01-01..2022-12-31 approximate; data-center era 2023-01-01; offer-cap start None = unverified),
`SPIKE_SEASON_PERCENTILE=97.5, Q_ADVERSE_MAX=0.05, Q_SEVERE_MAX=0.01, IMPLAUSIBLE_MARGINAL_MULT=1.25, WINDOW_DAYS=10`,
`ITERATIONS_PER_SEED=12, N_SEEDS=4, SCENARIOS_PER_CALL=3, EARLY_STOP_BREACHES=5`, `DEFAULT_MODEL="claude-sonnet-5-5"`.

## `revstress.book`

```python
@dataclass(frozen=True) class BookParams:
    k1_usd: float; c0_usd: float; k6_usd: float; r_usd: float; h_usd: float; l_normal_mw: float   # $/MWh, MW
    heat_rate: float = 8.0; vom_usd: float = 3.0
    p4_premium_usd: float = 0.0; p6_premium_usd: float = 0.0      # $/MWh; 0 = payoff only (carry excluded)
    sizes_mw: dict[str, float]; basis_usd: dict[str, float]

fit_book_params(panel) -> BookParams
    # K=mean wh_on; c0=mean 24h(DOM-WH); K6=99th pct wh_on; H=mean WH 24h; R=mean DOM 24h; l_normal=median load. Needs full panel.
active_positions(fallback: bool | None = None) -> tuple[str, ...]
pnl(path_df, params: BookParams, fallback: bool | None = None) -> pd.DataFrame
    # columns: date, P1, P2, P3, P4, P5, P6, system, congestion, dart, gas, zone_volume, tail, total   (USD per day)
    # inactive positions (fallback) are 0.0. Deterministic, vectorised.
pnl_totals(pnl_df) -> pd.Series            # sum over days of every column except date (USD)
scenario_loss_usd(pnl_df) -> float         # -sum(total); positive = loss
is_breach(pnl_df, target_usd: float = config.LOSS_TARGET_USD) -> bool
with_strikes(params, **changes) -> BookParams
POSITION_COLUMNS, CHANNEL_COLUMNS, PNL_COLUMNS
```
On weekends and NERC holidays (`panel.onpeak_day_flags`; optional panel column `is_onpeak_day` overrides) there are 0 on-peak hours:
P1, P4, P6 = 0, wh24 = wh_off, dom24 = dom_off and the P3 leg uses 24 h. K and K6 are fitted on on-peak days only.
Daily formulas (on-peak days; sizes are config.POSITION_SIZES_MW, shown here as symbols s1..s6, original values 50, 50, 25, 100, 200, 25, production values 100, 25, 50, 50, 140, 25): P1 = 16*s1*(wh_on-K); P2 = 24*s2*((dom24-wh24)-c0); P3 = 8*s3*(da_wh_off-rt_wh_off);
P4 = 16*s4*(max(wh_on-8*G-3,0)-premium), G = hh_usd + seasonal basis; P5 = 24*s5*(load/normal)*((R-dom24)+(wh24-H));
P6 = -16*s6*(max(wh_on-K6,0)-premium); wh24 = (16*wh_on+8*wh_off)/24, dom24 likewise.
Note P5 depends on the DOM-WH spread, not the level (hedge offsets), so P2 and P5 both respond to the spread, in opposite directions per MW (net spread exposure at production sizes: P5 140 MW against a P2 hedge of 25 MW).

## `revstress.shock`

```python
@dataclass(frozen=True) class PassThrough:    # PLACEHOLDER coefficients until the price regression (plan sec 4) is fitted
    gas_beta: float = 0.6; load_beta1: float = 2.0; load_beta2: float = 6.0
    offpeak_scale: float = 0.5; l_normal_mw: float | None = None

validate_shock(shock: Mapping[str, float], horizon_days: int) -> dict[str, float]
    # fills missing keys from config.NEUTRAL_SHOCK; ValueError on unknown key, duration_days > horizon, spike_days > duration,
    # load_peak_ratio <= 0, gas_hh_pct / wh_onpeak_pct / dart_pct <= -100, spike_daily_avg_usd < 0.
apply_shock(base_panel_slice: pd.DataFrame, shock: Mapping[str, float], rng_seed: int, passthrough: PassThrough | None = None) -> pd.DataFrame
```
Shock keys: `gas_hh_pct` (%), `load_peak_ratio` (x), `dc_load_shock_mw` (MW added to peak load), `wh_onpeak_pct` (% residual on WH level, on top of gas/load pass-through),
`dom_minus_wh_usd` ($/MWh added to DOM-WH spread, on and off peak), `dart_pct` (% RT over DA, on and off peak), `spike_days` (count),
`spike_daily_avg_usd` ($/MWh WH on-peak RT daily average on spike days), `duration_days` (shock applies to the first `duration_days` rows; the rest of the slice is unchanged).
Output: same columns as the slice (shocked `wh_*, dom_*, da_*/rt_*, hh_usd, load_peak_mw`; `hdd, cdd` unchanged) plus
`load_normal_mw` (MW), `shock_day`, `spike_day`, `energy_clipped` (bool). Input is not mutated. Spike days are drawn by `np.random.default_rng(rng_seed)` among shocked days.
Clipping: WH DA/RT series are capped at 3700 (treated as the energy component, since WH congestion/losses are not separable in daily data); DOM = clipped WH + spread, so DOM can exceed 3700.
Limitation: daily averaging understates hourly spikes (P3 and P6 are understated vs hourly truth).
`SCENARIO_EXTRA_COLUMNS` lists the four extra columns.

## `revstress.synthetic` (tests/demos only)

```python
SYNTHETIC_WARNING: str; SYNTHETIC_SOURCE_LABEL = "SYNTHETIC"
generate_synthetic_panel(seed: int, start: str = "2019-01-01", end: str = "2025-12-31", warn: bool = True) -> pd.DataFrame
```
Panel columns plus `synthetic_source == "SYNTHETIC"`; `df.attrs["warning"] = SYNTHETIC_WARNING`; emits a `UserWarning` unless `warn=False`.
Never present anything computed from it as a real result.

## Not yet built (owned by other engineers)
Factors/regression/covariance/spike model/plausibility (`revstress/factors.py` etc., plan sec 4), agent loop and rules (sec 5), baselines (sec 8D), real data loaders.

## Market refactor (plan section 12): `revstress.market` and the market-aware functions

PJM is the default market, so every PJM call is unchanged. NYISO is selected explicitly: set `config.MARKET = "NYISO"` (read at call time, so tests can monkeypatch it) or pass `market="NYISO"` where a function takes one. `market=None` always means the active market.
Internal column and shock names are kept (`wh_*` = reference zone: PJM Western Hub, NYISO WEST; `dom_*` = load pocket: PJM Dominion, NYISO N.Y.C.).

```python
@dataclass(frozen=True) class Market:          # revstress/market.py
    name; reference_zone; pocket_zone; reference_label; pocket_label           # NYISO: "WEST", "N.Y.C."
    energy_cap_usd: float; cap_is_assumption: bool; cap_note: str              # PJM 3700 (rule); NYISO 5000 (STATED ASSUMPTION, not a NYISO number)
    cap_failure_label: str; cap_rule_name: str                                 # plausibility string / agent rule name
    onpeak_hours: int; onpeak_definition: str; nerc_holidays: bool
    structural_breaks: tuple[(key, iso date | (start, end) | None), ...]; primary_break_key: str
    analogue_key: str; weather_stations: tuple[(label, GHCN id), ...]; typical_peak_mw: tuple[(season, MW), ...]
    large_load_ranges_mw; large_load_driver_class; gas_basis_usd (stated ASSUMPTIONS; NYISO values are placeholders)
    driver_classes; default_driver_class; seed_families; shock_key_map: tuple[(agent key, engine key), ...]; loader_module; synthetic_label
    # properties: agent_shock_keys, engine_shock_keys, agent_to_engine, engine_to_agent, structural_break_dates,
    #             primary_break_cutoff, typical_peak_by_season, gas_basis_by_season, large_load_ranges, weather_station_ids
PJM, NYISO: Market;  MARKETS: Mapping[str, Market];  get_market(name: str | Market | None = None) -> Market   # None -> PJM
```
NYISO breaks: `scarcity_pricing` 2016-06-22 (the primary cutoff), `indian_point_2_retirement` 2020-04, `indian_point_3_retirement` 2021-04, `transmission_shortage_pricing` 2023-11-14, `reserve_curve_revision_2021` None, `chpe_in_service` None (unverified).

`config` additions: `MARKET="PJM"`, `active_market()`, `energy_cap_usd()` (use this, not the constant), `gas_basis_by_season()`, `structural_breaks()`, `break_cutoff()`, `OPTIONAL_SHOCK_KEYS=("ny_gas_basis_usd",)`.
`ENERGY_COMPONENT_CAP_USD` (3700) and `GAS_BASIS_USD`, `STRUCTURAL_BREAKS` stay as the PJM values. `SHOCK_KEYS`/`NEUTRAL_SHOCK` (engine keys) are unchanged.

Engine (`shock.py`): `validate_shock` also accepts the optional engine key `ny_gas_basis_usd` ($/MMBtu, default 0, not added to the returned dict when absent). `apply_shock` adds it to `hh_usd` on shocked days (the gas leg of P4 only; it is not passed into the WEST price). Price clipping uses `config.energy_cap_usd()`.
`risk.fit_risk_model(include_pre_break=False)` cuts at `config.break_cutoff()` (PJM 2022-10-01, NYISO 2016-06-22). `score_scenario` hard-rule failure for a price above the cap is `Market.cap_failure_label` ("energy_component_above_3700" for PJM, "scenario_cap_above_5000" for NYISO).
`book.BookParams.basis_usd` and `panel.gas_price_usd` default to `config.gas_basis_by_season()`.
`baselines.common.SpikeOverlay.max_avg_usd` defaults to `config.energy_cap_usd()`; `default_hard_rules` uses it. `classify_driver(shock, season, market=None)` (NYISO: dc_load_shock_mw < 0 -> `large_load_shortfall`, fallback `reserve_shortage`; PJM unchanged) and `template_narrative(shock, season, driver_class, loss_usd=None, market=None)` (zone labels from the market; ny_gas_basis_usd clause) take a market.

### Agent boundary (`agent/`)
Agent-facing shock keys (`Market.agent_shock_keys`). PJM: the 9 `config.SHOCK_KEYS`. NYISO (plan section 5): `gas_hh_pct, ny_gas_basis_usd, load_peak_ratio, large_load_shock_mw, ref_onpeak_pct, pocket_minus_ref_usd, dart_pct, spike_days, spike_daily_avg_usd, duration_days` plus a required top-level `stated_loss_usd` (USD, Claude's own estimate).
Documented mapping, applied by `rules.to_engine_shocks` (identity for PJM; also stated in the NYISO prompt as `rules.SHOCK_MAPPING_LINE`):
`ref_onpeak_pct == wh_onpeak_pct`, `pocket_minus_ref_usd == dom_minus_wh_usd`, `large_load_shock_mw == dc_load_shock_mw` (`ny_gas_basis_usd` and the rest keep their names).

```python
rules.resolve_market(market=None) -> Market;  rules.default_analogue_table(market=None) -> dict   # DEFAULT_ANALOGUE_TABLE stays the PJM table
rules.to_engine_shocks(shocks, market=None) -> dict;  rules.to_agent_shocks(shocks, market=None) -> dict;  rules.SHOCK_MAPPING_LINE: str
rules.check_hard_rules(scenario, analogue_table=None, tol=0.30, market=None)   # market enums, agent keys, cap rule name Market.cap_rule_name
    # ("energy_component_cap" PJM, "scenario_price_cap" NYISO), NYISO sign rule: large_load_shortfall with large_load_shock_mw > 0 fails
rules.lookup_event(table, event, market=None)
schema.scenario_schema(market=None) / schema.response_schema(market=None) -> dict;  schema.validate_scenario(obj, market=None)
    # SCENARIO_SCHEMA / RESPONSE_SCHEMA remain the PJM schemas
prompts.role_text(market=None);  prompts.NYISO_ROLE;  prompts.build_seed_prompt(..., target_loss_usd=..., market=None)
    # NYISO: role text with WEST / N.Y.C. / about 30 GW, scenario-cap line labelled a stated assumption, mapping line,
    # stated_loss_usd instruction, large-load ranges (MW) and the NYISO analogue table. PJM prompt text is byte-identical to before.
loop.run_loop(..., distance_fn=None, market=None)   # validates with the market's schema and rules, calls engine_fn with ENGINE keys
client.FAKE_CLIENT_LABEL = "FAKE CLIENT - not Claude results";  client.canned_scenarios(driver_class, iteration, n, version="v3", market=None)
client.FakeClient(responses=None, scenarios_per_call=..., market=None, **kw)   # market=None: active market at call time
    # every canned narrative contains FAKE_CLIENT_LABEL; fake cache entries carry "label": FAKE_CLIENT_LABEL
```
`loop` CLI: `python -m revstress.agent.loop --dry-run [--market NYISO] --driver large_load_shortfall`.

### Analogues (`eval/analogues.py`)
`ANALOGUES`, `EVENT_DISPLAY`, `EVENT_ALIASES` stay the PJM tables; `NYISO_ANALOGUES`, `NYISO_EVENT_DISPLAY`, `NYISO_EVENT_ALIASES` are the NYISO tables under the same event keys (`jan2014, elliott, jan2025, jun2025, datacenter`; the `datacenter` key is the Gold Book large-load series for NYISO). Rows come only from plan sections 6 and 8A, each with source and vintage; unverified numbers (event-day maximum LBMP and shortage-interval counts for 2014, 2025, Elliott; Elliott daily Z6 NY gas) are `None` and omitted from the table Claude sees.
```python
normalise_event(event, market=None);  analogue_table(market=None);  analogue_rows(market=None) -> tuple[Analogue, ...]
lookup(event, metric, market=None);  score_claim(event, metric, claimed, market=None);  score_analogue(analogue, market=None)
```

### Synthetic (`synthetic.py`)
`generate_synthetic_panel(seed, start, end, warn=True, market=None)`: NYISO scale (load about 15-31 GW, WEST on-peak mean about 50 $/MWh, N.Y.C.-WEST spread mean about 13 $/MWh, prices clipped at 5,000), warning text from `synthetic_warning(market=None)` ("... is not NYISO data ..."); PJM output is unchanged. Still SYNTHETIC only.

## Literature-driven methods and run diagnostics (plan sections 5 and 8)

```python
# baselines/cond_gaussian.py  (Sparviero and Viola, arXiv 2606.09274)
cond_gaussian_search(engine_fn, spec: FactorSpec, *, budget, seed, season="winter", horizon_days=30, duration_days=7,
                     spike_days=0, spike_daily_avg_usd=0.0, target_usd=LOSS_TARGET_USD, rules_fn=default_hard_rules,
                     fd_step_sd=0.25, max_newton=6, damping=0.9, overshoot=0.02, local_scale=0.15, bound_sd=6.0) -> list[dict]
```
Same engine_fn interface and record schema as `random_search` / `optimizer_search`, arm `"cond_gaussian"` (template narratives). Steps: base point mu and forward-difference gradient of the loss in factor units (1 + 5 engine calls); closed form x* = mu + lam * Sigma g, lam = (aim - L0) / (g' Sigma g), aim = target*(1+overshoot); damped Newton / secant correction on lam with the true engine; remaining budget on local perturbations of the best feasible point, projected onto the hyperplane g'dx = 0. At most `budget` engine calls (cache hits are free); deterministic given seed. Duration and the spike overlay are fixed inputs (no spike by default). Exported from `revstress.baselines`.

`eval/metrics.py` additions (inputs are the agent loop's scenario dicts, i.e. `LoopResult.scenario_records` or the audit log's `scenarios`, unless stated):
```python
records_from_loop(scenario_records) -> list[dict]            # to the baseline record schema (then run_metrics / compare_arms / repeat_dispersion)
stated_vs_implied(scenario_records, group_key="prompt_version") -> DataFrame
    # per group: n, n_stated, n_scored, abs_err_mean/median/p90 (USD), rel_abs_median/rel_abs_p90, rel_err_median (signed, (stated-engine)/|engine|), share_within_20pct
target_anchoring_report(arms: {arm: scenario_records}, target_usd, tol=0.20) -> DataFrame
    # per arm: n_scenarios, n_engine, loss_mean/median/p10/p90, share_within_tol (|loss-target| <= tol*target), share_above_target, n_breaches
gate_rejection_stats(scenario_records) -> dict
    # n_scenarios, n_accepted, n_rejected, rejection_rate, hard {rule: {count, rate}} (incl. 'schema', 'engine_error'),
    # n_soft_scored, soft {rule: {count, rate, penalty_sum}}, mean_penalty
repeat_dispersion(repeats: list[list[record]], target_usd, tau) -> DataFrame    # rows n_breaches, median_q, driver_coverage, channel_coverage; cols n, mean, sd (ddof 1), min, max (baseline-schema records, any arm)
```

Loop and prompts:
- `prompts.build_seed_prompt(..., include_loss_target=True)` and `prompts.build_feedback_message(..., include_loss_target=True)`: False is the severity-anchoring ablation arm. The dollar target and the "breaching scenarios found so far" counter are dropped from the task, method and feedback text; everything else is identical. The default text is byte-identical to before. (The caller must also keep the target out of `context`.)
- `loop.run_loop(..., include_loss_target=True)`: the flag only changes the prompts; `loss_target_usd` still defines a breach. `LoopResult` gains `scenario_records` (every proposed scenario; each also carries `prompt_version`, `seed_index`, `iteration`, `stated_loss_usd`), `include_loss_target`, and `gate_stats()`. Call log records carry `include_loss_target`; the audit-log summary event carries `include_loss_target` and `gate_stats`.
- `loop.run_target_ablation(client_factory, engine_fn, seeds, *, log_dir=None, run_id="ablation", loss_target_usd, **run_loop_kwargs) -> {"with_target": LoopResult, "without_target": LoopResult}`: runs both arms with identical seeds and arguments and a fresh client per arm; logs `<log_dir>/<run_id>_<arm>.jsonl`. Report with `metrics.target_anchoring_report({a: r.scenario_records ...})`.

### Run manifest (`revstress/manifest.py`)
```python
write_run_manifest(run, *, model, temperature, seed, prompt_version, prompt_hash=None, system=None, messages=None, market=None,
                   label=None, data_root=<project>/data, outputs_root=<project>/outputs, extra=None) -> Path   # outputs/<run>/manifest.json
verify_manifest(manifest_path, *, data_root=..., check_raw=True, check_package=True) -> {ok, checked, mismatched, missing, package_ok, prompt_hash}
collect_data_records(data_root) -> {raw, processed, processed_labels, panel_date_range};  sha256_file(path);  package_version() -> "0.1.0+src.<12 hex>"
```
Records: sha256 and download dates of the raw files (from every `data/raw/**/MANIFEST.json`; keys as the loader writes them), sha256 and build time of the processed panel files (from `data/processed/*manifest.json`), market and cap flag, selected `config` constants, model id / temperature (None = API default) / seed, prompt version and sha256 (given, or computed from system + messages), python / numpy / pandas versions, and a git-less package digest (sha256 over the package's .py files). `label` must carry the provenance text ('FAKE CLIENT - not Claude results', 'SYNTHETIC', or the real data range). `verify_manifest` re-hashes the processed and raw files and the package source; it does not touch the network.

### Real-panel pipeline (`revstress/pipeline_real.py`) and `run_nyiso_demo.py`
```python
run_real_pipeline(seed=0, budget=144, *, repeats=5, fallback=None, client_factory=None, log_dir=None, panel=None, fit_panel=None,
                  prompt_version="v3", loss_target_usd=config.LOSS_TARGET_USD, n_boot=50, ablations=True) -> RealPipelineResult
    # sets config.MARKET="NYISO" for the call; fit window FIT_START..FIT_END (2019-01-01..2025-12-31); regression pass-through;
    # arms ARMS = (claude, random, optimizer, cond_gaussian) at equal per-seed engine budget; client_factory=None -> FakeClient (label FAKE_LABEL)
load_real_panel(data_root) -> (panel, fit_panel);  nyiso_market() (context manager);  real_data_label(panel);  run_label(panel, fake)
run_ablations(...) -> (runs, anchoring report, prompt-version table);  gate_table(gate, label) -> DataFrame;  coherence_mechanical(records)
```
`RealPipelineResult`: `label` (stamp for every output), `fake`, `table` (compare_arms + engine_calls), `dispersion[arm]`, `gate[run]`, `stated_vs_implied`, `anchoring`, `prompt_versions`, `repeats[arm]`, `loop_results`.
`run_nyiso_demo.main(argv)`: `--seed --budget --repeats --dry-run --fallback-book --loss-target-usd --out --no-ablations --live --i-understand-cost`; `check_live_guard(live, understand_cost, environ)` returns a refusal text (live needs `ANTHROPIC_API_KEY` set and `--i-understand-cost`; exit code 2 otherwise).
Fix made during integration: `risk.covariance.fit_season_cov` now applies Ledoit-Wolf shrinkage in standardized units (factors mix log points and USD/MWh; unscaled shrinkage inflated the log-factor sds about 100x and made baseline draws absurd).

## Book-size selection, optimizer v2 and sensitivity table (this revision)

```python
# eval/sizing.py: the pre-stated rule of the config.py comment, as code
largest_position_share(rec) -> float      # largest single-position loss / net loss (can exceed 1 when a hedge gains)
candidate_stats(records_by_seed, worst_30d_loss_usd, *, target_usd, tau) -> dict
    # breaches_per_seed, min_breaches, share, n_channels, channels, n_seasons, seasons, worst_30d_loss_usd, worst_30d_ratio
failed_conditions(st, relax=()) -> list[str];  is_admissible(st, relax=()) -> bool      # conditions 'a'..'d'
select_candidate(candidates: [{'sizes', 'stats'}]) -> (index | None, relaxed: tuple)    # max min-breaches; ties: lower share, smaller gross MW; relax c, then b

# baselines/optimizer.py
optimizer_search(engine_fn, spec, *, budget, seed, season="winter", horizon_days=30, duration_range=(3, 14), n_starts=4, bound_sd=6.0,
                 sigma_mult=1.0, spike=None, target_usd=..., rules_fn=..., max_iter=200, warm_start=True, warm_duration=7,
                 tail_d2=None, z_limits=None, margin_loss=0.01, margin_tail=0.05, margin_z=0.5, fd_step_sd=0.25, max_newton=5,
                 damping=0.9, overshoot=0.02, restart_scale=0.5) -> list[dict]
    # Same record schema, arm 'optimizer', at most `budget` engine calls. warm_start=False = original version (sigma_mult, spike, n_starts
    # as before). With warm_start: conditional-Gaussian linearised start + SLSQP with Broyden-updated derivatives of loss, sqrt(engine D^2)
    # and the engine z of the five factors; constraints loss >= target, engine D^2 >= tail_d2 (tail), z inside z_limits (marginal limits),
    # adaptive load cap when the engine lists 'T' among marginals_exceeded, sign consistency as variable bounds; restarts share the budget.
pipeline.plausibility_kwargs(model, season, q_max=0.05) -> {"tail_d2": float, "z_limits": {factor: (lo_z, hi_z)}}   # inputs of the above, from the risk model

# eval/metrics.py
requantile(records, window_d2) -> list[dict]          # engine q recomputed as mean(window_d2 >= engine d2)
sensitivity_table(runs: {arm: [repeat records]}, window_d2_by_days: {n: array}, *, target_usd, taus=(0.5, 1.0, 2.0), q_max=0.05) -> DataFrame
    # SENSITIVITY_COLUMNS: arm, window_days, tau, n_repeats, n_breaches_mean/sd/min/max, repeats_with_breach, weakest_q_mean, weakest_q_max
    # one row per (arm, window length, tau); weakest q = largest q among the distinct breaches of a repeat
# eval/diagnostics.py
window_d2_by_length(model, lengths=(5, 10, 14)) -> {n: array of max-daily-D^2 of non-overlapping n-day windows}
sizing_check(...)   # the 'rule' text and the report now quote the actual target (previously the text said 5M and 25% regardless)
```
`RealPipelineResult.sensitivity` holds the table; `run_nyiso_demo.py` writes it to `sensitivity.csv`. The pipeline passes `plausibility_kwargs` to the optimizer per season.

## Update 2026-10-28 (rule v2)
`book.fit_book_params` now sets `p4_premium_usd` and `p6_premium_usd` to the fair value (mean payoff per on-peak MWh on the fit sample). `POSITION_SIZES_MW["P1"]` may be negative (short swap); `agent/context.book_table` follows the sign. `eval/sizing.py` adds `breach_mix`, `failed_conditions_v2`, `select_candidate_v2`. The glossary entries `large_load_shock_mw` and `load_peak_ratio` and the v2/v3 method text state the sign rules of `sign_consistent`.
