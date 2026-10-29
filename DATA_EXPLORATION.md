# Data exploration report (as of 2026-10-27)

All numbers below come from the exploration run. Nothing was cross-checked against a second source unless stated. Where the run did not test something, it says "not tested".

## 1. Bottom line

We cannot build the real daily PJM panel today. No keyless route to daily or hourly PJM hub prices (Western Hub, Dominion Hub) or to hourly PJM load exists: the old public file folders are gone and Data Miner 2 / api.pjm.com answers 401 without a pjm.com account key. Keyless sources do work for three columns: `hh_usd` (EIA Henry Hub daily), `hdd`/`cdd` (NOAA, 6 airports) and `load_peak_mw` (EIA-930 hourly PJM demand, from July 2015). A partial stand-in for `wh_on` exists (EIA/ICE "PJM WH Real Time Peak" next-day forward price), but it is on-peak only and misses the Elliott peak days (24-27 Dec 2022). Everything else (wh_off, dom_on, dom_off, da/rt) needs the PJM key or a re-scope to another ISO (NYISO and ISO-NE are the best keyless alternatives). The single most important gap: **daily Western Hub and Dominion Hub on/off-peak DA and RT prices**.

## 2. Summary table

| Family | Source | Works now | Key/registration | History | Granularity | Elliott (Dec 2022) | Jan 2025 | Jun 2025 | Jan 2014 | Terms |
|---|---|---|---|---|---|---|---|---|---|---|
| PJM LMP keyless | pjm.com files, Data Miner 2, IMM State of the Market PDFs | No (PDF averages only) | Yes (pjm.com account + subscription key) for daily/hourly | PDFs: annual 1999-2026, quarterly 2025 | Annual/quarterly hub averages | Narrative only | Quarterly avg only | Not tested | Not tested | Unknown; (c) Monitoring Analytics; treat internal |
| Gas / ICE power | EIA Henry Hub daily; EIA/ICE electric xlsx; EIA citygate | Yes | No | HH 1997-2026-10-20; ICE downloaded 2014, 2022, 2025, 2026 (others listed, not fetched); citygate 1989-2026-07 | HH daily weekdays; ICE one on-peak PJM WH forward price per trade day; citygate monthly | HH yes; ICE misses 24-27 Dec | Yes | Yes (ICE 23-25 Jun; HH calm) | Yes (ICE and HH) | US public domain (EIA); ICE data republished with permission, licensed-in |
| Load EIA-930 | EIA grid monitor bulk CSVs | Yes | No (API needs key; bulk does not) | Jul 2015 to at least Jun 2025 (later halves not tested) | Hourly, by BA; sub-region (DOM, AEP, CE, etc.) | Yes | Yes | Yes | No | US public domain, cite EIA |
| Weather | NOAA NCEI daily summaries, 6 stations | Yes | No | 1936-46 to 2026-10-24 | Daily TMAX/TMIN | Yes | Yes | Yes | Yes | Not read; believed public, verify |
| Other ISOs | NYISO, ISO-NE, MISO, CAISO (ERCOT blocked 403) | Yes (sampled days only) | No (ISO-NE web API 401) | NYISO from at least 2014; ISO-NE day files 2016+ (2014 404); MISO ~Jan 2023+; CAISO ~3 yrs | Hourly DA; NYISO RT 5-min; zones/hubs | NYISO, ISO-NE yes; MISO, CAISO no | All four (22 Jan only) | Not tested | NYISO only | Not established; internal use |
| PJM load and notices | PJM planning files, IMM PDFs | No for hourly/daily load | Yes (hrl_load_metered) | Events 1991-2026; WN peaks 2013-2025; forecast 2026-2046 | Event, monthly forecast, annual | Event notices, IMM Dec anchors | No DR event found | Yes (events, IMM peak) | DR event dates only | Unknown; internal |

## 3. Per family

### 3.1 PJM LMP keyless (does not work for daily data)
- Fetched: IMM State of the Market section 3 PDFs (2022, Q1 2025), Data Miner 2 JS bundle, HTML probes. Old directories `/pub/account/lmpda/`, `/lmp/`, `/lmpmonthly/`, `/lmpgen/` are soft-404 (HTTP 200 with "Page Not Found" title; check the title, not the status). api.pjm.com returned 401; the bundle adds an `Ocp-Apim-Subscription-Key` header. Data Viewer (JSF page) was not driven; its exports are untested. No key was registered or used.
- Files (all under `pjm_revstress\data\raw\pjm_lmp_keyless\`): `2022-som-pjm-sec3.pdf` (4.4 MB, 150 pp), `2025q1-som-pjm-sec3.pdf` (3.8 MB, 152 pp), `dm2_main_bundle.js`, HTML shells/soft-404 pages. Scripts in `pjm_revstress\data_exploration\scripts\` (probe_pjm.py, probe2.py, probe3.py, inspect_pages.py, profile_pdf.py, hubrows.py).
- Profile ($/MWh): 2022 annual, Western Hub DA DLMP 72.90, RT PLMP 74.25; Dominion DA 76.47, RT PLMP 79.56. Jan-Mar 2025, Western Hub DA 53.80, RT PLMP 52.72; Dominion DA 55.72, RT PLMP 58.25. Q1 2025 PDF notes $135.9M DA uplift during the polar vortex.
- Quality: PDF table text extraction depends on layout; annual averages are far too coarse for a daily panel. Use only as annual sanity checks.

### 3.2 Gas and ICE power (EIA)
- Fetched: Henry Hub daily HTML table (the .xls downloaded but was not opened: no xlrd), ICE electric xlsx for 2022, 2025, 2026 and legacy xls for 2014 (read with custom `xls_min.py`), state citygate monthly pages (PA, NJ, MD, OH, VA, US).
- Files (under `data\raw\eia_gas_ice\`): `rngwhhdD.htm`, `RNGWHHDd.xls` (295 KB), `hh_daily_2013-12_onward_parsed.csv`, `ice_electric-2014final.xls` (252 KB), `ice_electric-2022final.xlsx` (103 KB), `ice_electric-2025final.xlsx` (92 KB), `ice_electric-2026.xlsx` (78 KB), `citygate_monthly_2013-12_onward_parsed.csv`, `n3050{pa,nj,md,oh,va,us}3m.htm`, `N3050{PA,NJ,MD,OH,VA,US}3m.xls` (47-55 KB each, unread), `wholesale.htm` (63 KB), `ng_pri_sum.htm`. Scripts: eia_p1..p6.py, eia_dbg.py, xls_min.py.
- Henry Hub: 7,170 weekday slots 1997-01-06 to 2026-10-20; missing 3.5% since 2014 and 4.3% since 2019 (forward-fill). Range since 2014: 1.21 to 30.72. Examples: 22 Dec 2022 7.10, 23 Dec 7.15; 17 Jan 2025 9.86; 23 Jun 2025 3.50; 23 Jan 2026 30.72.
- ICE: only ONE PJM product, "PJM WH Real Time Peak" (Western Hub, on-peak, next-day forward trade, not settled LMP). No off-peak, no day-ahead, no Dominion. Rows: 2022 236, 2025 235, 2026 183, 2014 252. Mean WH price: 2022 86.59, 2025 60.22, 2026 95.87. Event values by delivery day: 23 Dec 2022 181.75 then no rows for 24-27 Dec; 20-22 Jan 2025 163.20, 255.95, 196.69; 23-25 Jun 2025 203.65, 216.31, 188.90 (26 Jun no row); Jan 2014 up to 498.68 (28 Jan); 27 Jan 2026 1014.40.
- Citygate: monthly, USD/Mcf not MMBtu; 5-12 blanks since 2019; correlation with monthly HH 0.54 (MD) to 0.84 (US). Loose proxy only.
- Quality: 50 text-valued volume cells in the 2025 file ("57,600"); one duplicated trade date in 2022; hub names change in 2014 (key on a name pattern); ICE prices are thin on some days. Not downloaded: ICE 2015-2021, 2023, 2024, historical zip.

### 3.3 Load, EIA-930
- Fetched: half-yearly bulk CSVs (URL pattern guessed, works): BALANCE 2022 Jul-Dec (42.9 MB, 275,330 rows, PJM 4,417), BALANCE 2025 Jan-Jun (47.6 MB, 264,934 rows, PJM 4,343), SUBREGION 2022 Jul-Dec (26.4 MB). 2018 and 2015 Jul-Dec files exist (HEAD/range only).
- Files (under `data\raw\eia930_load\`): the three CSVs above, `gm_home.html` (43 KB). Script: `eia930_profile.py`.
- Profile: Demand missing 1 of 4,417 rows in 2022 (last row), 0 in 2025. Daily maxima: 23 Dec 2022 135,328 MW (PJM reports about 134,700, +0.5%); 22 Jan 2025 144,420 (PJM hourly 143,714, +0.5%); 23 Jun 2025 160,560. Day-ahead forecast is included and understated the peaks by 5% (Dec 2022) and 3.5% (Jan 2025). DOM sub-region peaked at 22,415 MW on 24 Dec 2022.
- Quality: column count changes across years (19/44/65), so select by name; dates are MM/DD/YYYY, hour-ending; EIA peaks sit about 0.5% above PJM's; history starts July 2015 so Jan 2014 is not covered; 2025 H2 and 2026 files were not tested; the "about" and "known issues" pages could not be read.

### 3.4 Weather, NOAA
- Fetched: GHCN daily summaries for PHL (USW00013739), PIT (USW00094823), DCA (USW00013743), ORD (USW00094846), CMH (USW00014821), CLE (USW00014820), 11-12 MB each.
- Files (under `data\raw\noaa_weather\`): `PHL_USW00013739.csv`, `PIT_USW00094823.csv`, `DCA_USW00013743.csv`, `ORD_USW00094846.csv`, `CMH_USW00014821.csv`, `CLE_USW00014820.csv`. Scripts: noaa_fetch.py, noaa_profile.py.
- Profile: 2014-01-01 to 2026-10-24, 4,680 of 4,680 days at all stations; TMAX and TMIN 0% missing; TAVG 100% missing for 2014+, so use (TMAX+TMIN)/2. Units are tenths of degrees C. My computed 6-station HDD: 24 Dec 2022 56.2; 21 Jan 2025 56.9; 7 Jan 2014 62.6. CDD 24 Jun 2025 21.0.
- Quality: quality flags not applied; tail is provisional; calendar-day extremes; airports only (no Virginia/Dominion station except DCA; ORD is far from Western Hub); values not validated against official NOAA degree days.

### 3.5 Other ISOs (keyless)
- Fetched: NYISO monthly zips (DA Dec 2022, Jan 2025, Jan 2014; RT Dec 2022), CAISO OASIS DAM (NP15), ISO-NE histRpts DA/RT, MISO market reports. ERCOT 403 (bot wall, not bypassed). ISO-NE web API 401.
- Files (under `data\raw\other_iso_keyless\`): `nyiso_damlbmp_20221201damlbmp_zone_csv.zip`, `..._20250101...zip`, `..._20140101...zip`, `nyiso_realtime_20221201realtime_zone_csv.zip`, `caiso_dam_20250122.zip`, `caiso_probe_20231223.zip`, `isone_da_20221223.csv`, `isone_da_20250122.csv`, `isone_rt_20221223.csv`, `miso_da_20250122.csv`, `miso_rt_20250122.csv`, `miso_probe_20230122.csv`, other small probes, `ercot_403.html`. Scripts: other_iso_fetch.py, other_iso_profile.py, other_iso_profile2.py. Sizes not recorded (ISO-NE about 2.5 MB/day, MISO 1.0-1.3 MB/day).
- Profile (single sampled days): NYISO DA 23 Dec 2022 WEST mean 73.72, NYC 117.37; 22 Jan 2025 WEST 212.77, NYC 298.54; 7 Jan 2014 WEST 116.02. ISO-NE Internal Hub DA 23 Dec 2022 mean 163.52; 22 Jan 2025 201.65. MISO Indiana Hub DA 22 Jan 2025 115.27. CAISO NP15 22 Jan 2025 mean 50.47.
- Quality: NYISO RT showed 344 rows per zone-day, not resolved; CAISO errors return HTTP 200 with a tiny zip; MISO times are EST (no DST); Python urllib failed CAISO TLS while curl worked; Jun 2025 not tested in any ISO. Full-history profiles were not done.

### 3.6 PJM load and notices
- Fetched: PJM load-forecast package files and IMM PDFs; hourly metered load not available (old static files 404; api 401).
- Files (under `data\raw\pjm_load_and_notices\`): `alm-history.xlsx` (41 KB), `weather-normalized-peaks.xlsx` (27 KB), `2026-load-report-data.xlsx` (217 KB, forecast only), `summer-2025-peaks-and-5cps.pdf` (128 KB), `imm_load_by_state_2022.xls` (36 KB, unparsed), `2022-som-pjm-sec3.pdf` (4.4 MB), `2025-som-pjm-sec3.pdf` (4.6 MB), `imm_rt_lw_lmp_anchors_transcribed.csv`. Script: probe_load.py.
- Useful content: load-management (DR) events: #60 and #61 (23-24 Dec 2022), #62-64 (23-25 Jun 2025), events 46-52 (Jan 2014); none found for Jan 2025. IMM monthly anchors: Dec 2022 RT on-peak 129.51, off-peak 153.54; Jan 2025 on-peak 70.54, off-peak 55.29; Jun 2025 on-peak 94.51, off-peak 39.62; 24 Jun 2025 administratively set at $3,700; daily RT DLMP 24 Dec 2022 1,179.84. IMM peaks: 156,256 MWh (23 Jun 2025) and 140,043 MWh (22 Jan 2025, accounting load excluding DR addback).
- Conflict to note: the plan's Jan 2025 peak (143,714 MW) differs from the IMM's 140,043; probably definitional (DR addback), not verified. EIA-930 (144,420) is close to the plan figure. IMM annual series was read from raw-order pdftotext and should be checked against the PDF.

## 4. Mapping to the engine's panel columns

| Column | Source available now | Fit | Missing / substitute |
|---|---|---|---|
| wh_on | ICE "PJM WH Real Time Peak" (EIA) | Partial proxy (next-day on-peak forward, about 94% of business days) | Misses 24-27 Dec 2022; true source is PJM Data Miner 2 (key) |
| wh_off | None | No | PJM key; no keyless off-peak. IMM monthly off-peak is an anchor only |
| dom_on, dom_off | None | No | PJM key. Annual Dominion averages (PDF) only. Could proxy with wh_on plus a basis assumption (not data) |
| da / rt (wh) | None | No | PJM key. NYISO or ISO-NE if re-scoped |
| load_peak_mw | EIA-930 PJM Demand, daily max | Yes, about 0.5% above PJM metered | Jan 2014 not covered; download 2019 H1 onward |
| hh_usd | EIA Henry Hub daily | Yes | Forward-fill weekends/holidays and 3.5-4.3% blanks |
| hdd, cdd | NOAA 6 airports, base 65F | Yes | Weights are the student's choice; unvalidated vs official degree days |

## 5. Recommended data stack

Primary (if the PJM key arrives; registration is free per the findings, but untested): PJM Data Miner 2 for hub DA/RT LMPs and hourly load; EIA Henry Hub for gas; NOAA for HDD/CDD; EIA-930 as the load cross-check; IMM tables as annual/monthly validation anchors.

Fallback A (no key, stay on PJM): `wh_on` from EIA/ICE WH (download 2015-2021, 2023, 2024 files, about 5 small downloads for 2019-2026); `load_peak_mw` from EIA-930; `hh_usd` EIA; `hdd/cdd` NOAA. Drop wh_off, dom_*, da/rt columns, or use IMM monthly on/off-peak averages as coarse anchors. Elliott's peak days cannot be reconstructed from ICE.

Fallback B (re-scope to another ISO): NYISO (hourly DA and RT, back to 2014 at least on the three sampled months) and/or ISO-NE (DA/RT hub from about 2016). Both cover Elliott and Jan 2025; only NYISO sampled 2014. The hub/zone columns replace Western/Dominion; price-cap and spike logic must use that ISO's rules; load, gas and weather need new sources (the PJM-specific EIA-930 and NOAA stations would change). Jun 2025 coverage for these ISOs is untested.

Which of P1..P6 survive: the findings do not define P1..P6, so I cannot say which survive. They are not in the exploration output. Plain consequences: anything that needs on/off-peak spreads, Dominion vs Western basis, or DA vs RT spreads needs the PJM key or a re-scope. Anything that needs only on-peak Western Hub level, gas, weather and load can run on Fallback A, with the Elliott gap. The data-center load-driver idea can use EIA-930 DOM sub-region demand (2022 H2 tested) and the PJM 2026 forecast file.

## 6. Terms of use and what not to publish

- EIA (HH, citygate, EIA-930): public domain; use and distribute with acknowledgment, "Source: U.S. Energy Information Administration" plus date.
- EIA/ICE electricity files: republished by EIA with ICE permission; EIA warns private contributions may need owner permission. Do not redistribute the raw ICE files widely or commercially. My reading, not legal advice.
- NOAA: terms page not read; believed public but unverified.
- PJM and Monitoring Analytics: no redistribution clause found; PJM reserves IP rights; IMM footer is (c) Monitoring Analytics. Treat PDFs and derived tables as internal. The Data Miner 2 key, once obtained, must stay out of the repo and out of any report.
- NYISO, ISO-NE, MISO, CAISO: terms not retrieved. Do not commit raw files to a public repo.
- Rule of thumb: publish derived charts and summary statistics with source citations; do not publish raw ICE, PJM, IMM or ISO files.

## 7. Open questions and next steps

Open: Does a free PJM account and key actually give access (not tested)? Are PJM Data Miner 2 manual CSV exports or Data Viewer exports usable (not tested)? Do EIA-930 2025 H2 and 2026 files exist? How does the plan define P1..P6? Which station weights for HDD/CDD? Why the NYISO RT row count of 344? What explains the 143,714 vs 140,043 MW difference?

Next steps, in order:
1. Register for a PJM account and Data Miner 2 key (the student does this); request hourly/daily DA and RT LMP for Western and Dominion hubs, and hrl_load_metered.
2. In parallel, download the missing ICE years (2015-2021, 2023, 2024) and EIA-930 BALANCE files 2019 H1 to 2026 H1; confirm the newest file names exist.
3. Build `hh_usd` (forward-filled) and `hdd/cdd` (station weights chosen explicitly) from the saved files.
4. Build `load_peak_mw` as daily max of PJM Demand, and check the Elliott and Jan 2025 peaks against PJM's reported values.
5. Decide, on the key outcome, between the primary stack, Fallback A, and Fallback B; if B, test NYISO and ISO-NE for Jun 2025 and full history first.
6. Read the terms pages for PJM, IMM, NOAA and the ISOs before sharing any data.

## Files saved

Sizes are given where the run reported them (see section 3); files without a size were not measured. Raw data lives under `pjm_revstress\data\raw\` in the folders pjm_lmp_keyless, eia_gas_ice, eia930_load, noaa_weather, other_iso_keyless, pjm_load_and_notices. Scripts live in `pjm_revstress\data_exploration\scripts\`.
