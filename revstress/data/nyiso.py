"""NYISO loader: monthly MIS zips and NOAA files to the 13-column daily panel of revstress.panel (no network).

Mapping (internal names are kept, see plan sec 12): wh_* = WEST (reference zone), dom_* = N.Y.C. (load pocket, Zone J).
  da_wh_on / da_wh_off  WEST day-ahead LBMP mean over on-peak / off-peak hours, $/MWh
  rt_wh_on / rt_wh_off  WEST hourly-integrated real-time LBMP means; wh_on / wh_off equal them (settlement = RT)
  dom_on / dom_off      N.Y.C. real-time LBMP means, $/MWh
  load_peak_mw          daily max over hours of the sum of the 11 NYCA load zones (palIntegrated), MW
  hh_usd                Henry Hub spot, forward-filled over weekends/holidays/gaps, $/MMBtu
  hdd, cdd              base 65 degF degree days, weighted over stations (WEATHER_WEIGHTS), degF-days
Timestamps are local clock time, hour-beginning, with no zone flag. DST is handled by row order: a spring day has
23 rows and a fall day 25 (01:00 twice); hours are never re-indexed, so both 01:00 rows are kept. Rows stamped on a
different date than the file's own date (the next-day 00:00 row) are dropped.
On-peak = weekdays, hour-beginning 7..22 (HE8-23, 16 h), excluding the six NERC holidays (panel.nerc_holidays; MLK
day is not one). Weekend / holiday handling (least invasive for the panel contract, which forbids NaN): column
'is_onpeak_day' (bool) is added; on such days *_off = mean over all 24 hours (the panel.py rule 'wh24 = wh_off'),
and *_on is still reported as the hour-beginning 7..22 window mean for information only (the book ignores it there).
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from ..panel import PANEL_COLUMNS, onpeak_day_flags

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
REF_ZONE = "WEST"
POCKET_ZONE = "N.Y.C."
NYCA_LOAD_ZONES = ("CAPITL", "CENTRL", "DUNWOD", "GENESE", "HUD VL", "LONGIL", "MHK VL", "MILLWD", "N.Y.C.", "NORTH", "WEST")
ONPEAK_HOURS = tuple(range(7, 23))  # hour-beginning 7..22 = HE8-23
MIN_ROWS_PER_DAY = 23  # a DST spring day has 23 hourly rows
# Degree-day weights: Central Park (N.Y.C. load/price driver) 0.5, three upstate stations 1/6 each (student choice,
# unvalidated against official degree days); LGA and JFK are downloaded but have weight 0.
WEATHER_WEIGHTS: dict[str, float] = {"NYC_CentralPark": 0.5, "ALB": 1 / 6, "BUF": 1 / 6, "SYR": 1 / 6}
STATION_IDS = {"NYC_CentralPark": "USW00094728", "LGA": "USW00014732", "JFK": "USW00094789",
               "ALB": "USW00014735", "BUF": "USW00014733", "SYR": "USW00014771"}
BASE_F = 65.0
_DATE_IN_NAME = re.compile(r"^(\d{8})")


def read_zip_csv(path: str | Path | io.BytesIO) -> pd.DataFrame:
    """Concatenate every .csv member of a monthly zip in name order; adds 'file_date' (from the member name).

    Only CSV members are parsed (data is untrusted: nothing is executed). Row order inside each file is kept.
    """
    frames = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(n for n in z.namelist() if n.lower().endswith(".csv")):
            df = pd.read_csv(io.BytesIO(z.read(name)), encoding="latin1")
            df.columns = [str(c).strip() for c in df.columns]
            m = _DATE_IN_NAME.match(Path(name).name)
            df["file_date"] = pd.to_datetime(m.group(1), format="%Y%m%d") if m else pd.NaT
            frames.append(df)
    if not frames:
        raise ValueError("zip holds no CSV member")
    return pd.concat(frames, ignore_index=True)


def _find_col(df: pd.DataFrame, prefix: str) -> str:
    for c in df.columns:
        if c.startswith(prefix):
            return c
    raise KeyError(f"no column starting with {prefix!r} in {list(df.columns)}")


def _stamp_parts(df: pd.DataFrame) -> pd.DataFrame:
    """Local date, hour-beginning hour and occurrence index (second 01:00 on a fall day = 1) per row."""
    s = df[_find_col(df, "Time Stamp")].astype(str).str.strip()
    out = pd.DataFrame({"date": pd.to_datetime(s.str[:10], format="%m/%d/%Y"), "hour": s.str[11:13].astype(int)})
    out["file_date"] = df["file_date"].fillna(out["date"])
    out["name"] = df["Name"].astype(str).str.strip()
    out = out[out["date"] == out["file_date"]]  # drop next-day 00:00 rows
    out["occ"] = out.groupby(["date", "name", "hour"]).cumcount()
    return out


def parse_lbmp(df: pd.DataFrame, zone: str) -> pd.DataFrame:
    """Hourly LBMP of one zone from a read_zip_csv frame: columns date, hour, occ, price ($/MWh)."""
    parts = _stamp_parts(df)
    price = pd.to_numeric(df.loc[parts.index, _find_col(df, "LBMP")], errors="coerce")
    out = parts.assign(price=price)
    out = out[out["name"] == zone][["date", "hour", "occ", "price"]]
    return out.reset_index(drop=True)


def parse_nyca_load(df: pd.DataFrame, zones: tuple[str, ...] = NYCA_LOAD_ZONES) -> pd.DataFrame:
    """Hourly NYCA load = sum over the 11 zones: columns date, hour, occ, load_mw. Hours missing any zone are NaN."""
    parts = _stamp_parts(df)
    load = pd.to_numeric(df.loc[parts.index, _find_col(df, "Integrated Load")], errors="coerce")
    t = parts.assign(load=load)
    t = t[t["name"].isin(zones)]
    g = t.groupby(["date", "hour", "occ"])
    out = pd.DataFrame({"load_mw": g["load"].sum(min_count=len(zones)), "n": g["load"].count()}).reset_index()
    out.loc[out["n"] < len(zones), "load_mw"] = np.nan
    return out[["date", "hour", "occ", "load_mw"]]


def _concat_parsed(paths: list[Path], parser, **kw) -> pd.DataFrame:
    frames = [parser(read_zip_csv(p), **kw) for p in paths]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(["date", "hour", "occ"], keep="last")


def month_files(directory: Path, suffix: str, start: str | None = None, end: str | None = None) -> list[Path]:
    """Monthly zips YYYYMM01<suffix>.zip in a directory, sorted, optionally restricted to [start, end] (YYYY-MM-DD)."""
    out = []
    for p in sorted(Path(directory).glob(f"*{suffix}.zip")):
        d = pd.Timestamp(p.name[:8])
        if (start is None or d >= pd.Timestamp(start).replace(day=1)) and (end is None or d <= pd.Timestamp(end)):
            out.append(p)
    return out


def build_hourly(prices_dir: Path, load_dir: Path, start: str | None = None, end: str | None = None,
                 include: list[str] | None = None) -> pd.DataFrame:
    """Hourly table keyed by (date, hour, occ): wh_da, wh_rt, dom_da, dom_rt ($/MWh), load_mw.

    include: extra month-start stamps ('20140101') to load besides those in [start, end].
    """
    def sel(directory: Path, suffix: str) -> list[Path]:
        files = month_files(directory, suffix, start, end)
        extra = [Path(directory) / f"{s}{suffix}.zip" for s in (include or [])]
        return sorted({*files, *[p for p in extra if p.exists()]})

    key = ["date", "hour", "occ"]
    cols = []
    for tag, suffix in (("da", "damlbmp_zone_csv"), ("rt", "rtlbmp_zone_csv")):
        files = sel(prices_dir, suffix)
        for pref, zone in (("wh", REF_ZONE), ("dom", POCKET_ZONE)):
            t = _concat_parsed(files, parse_lbmp, zone=zone).rename(columns={"price": f"{pref}_{tag}"})
            cols.append(t.set_index(key))
    load = _concat_parsed(sel(load_dir, "palIntegrated_csv"), parse_nyca_load).set_index(key)
    cols.append(load)
    out = pd.concat(cols, axis=1).sort_index().reset_index()
    return out


def onpeak_mask(hour: pd.Series | np.ndarray) -> np.ndarray:
    """True for hour-beginning 7..22."""
    h = np.asarray(hour)
    return (h >= ONPEAK_HOURS[0]) & (h <= ONPEAK_HOURS[-1])


def daily_means(hourly: pd.DataFrame, value: str, day_flags: pd.Series) -> pd.DataFrame:
    """Daily on / off-peak means of a column. day_flags: bool Series indexed by date (True = on-peak day).

    On on-peak days: on = mean over hours 7..22, off = mean over the other hours. On other days: off = mean over all
    rows (24 h), on = mean over hours 7..22 (informational). Rows with NaN values are ignored. Returns index date,
    columns on, off, n_rows, n_on_rows.
    """
    t = hourly[["date", "hour", value]].dropna()
    t = t.assign(is_on=onpeak_mask(t["hour"]), flag=t["date"].map(day_flags).fillna(False).astype(bool))
    on = t[t["is_on"]].groupby("date")[value].mean()
    off = t[(~t["is_on"]) | (~t["flag"])].groupby("date")[value].mean()  # off-peak hours; all 24 h on non-on-peak days
    n = t.groupby("date")[value].count()
    n_on = t[t["is_on"]].groupby("date")[value].count()
    return pd.DataFrame({"on": on, "off": off, "n_rows": n, "n_on_rows": n_on})


def day_flag_series(dates: pd.DatetimeIndex) -> pd.Series:
    """Bool Series indexed by date: weekday and not a NERC holiday (uses panel.onpeak_day_flags)."""
    idx = pd.DatetimeIndex(dates)
    flags = onpeak_day_flags(pd.DataFrame({"date": idx}))
    return pd.Series(flags, index=idx)


def load_henry_hub(path: Path | None = None) -> pd.Series:
    """Henry Hub daily spot, $/MMBtu, reindexed to calendar days and forward-filled."""
    path = path or RAW / "eia_gas_ice" / "hh_daily_2013-12_onward_parsed.csv"
    s = pd.read_csv(path, parse_dates=["date"]).set_index("date")["hh_usd"].astype(float).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D")).ffill()


def read_station_degree_days(path: Path) -> pd.DataFrame:
    """GHCN-Daily station CSV to daily hdd, cdd (degF-days, base 65) from (TMAX+TMIN)/2; tenths of degC input."""
    df = pd.read_csv(path, usecols=["DATE", "TMAX", "TMIN"], parse_dates=["DATE"])
    tmean_f = ((pd.to_numeric(df["TMAX"], errors="coerce") + pd.to_numeric(df["TMIN"], errors="coerce")) / 2 / 10) * 1.8 + 32
    out = pd.DataFrame({"hdd": (BASE_F - tmean_f).clip(lower=0), "cdd": (tmean_f - BASE_F).clip(lower=0)})
    out.index = df["DATE"]
    return out[~out.index.duplicated(keep="last")].sort_index()


def weighted_degree_days(noaa_dir: Path, weights: dict[str, float] = WEATHER_WEIGHTS) -> pd.DataFrame:
    """Weighted hdd/cdd over stations; weights are renormalised over stations that report on a day."""
    frames = []
    for name, w in weights.items():
        if w <= 0:
            continue
        files = sorted(Path(noaa_dir).glob(f"{name}_*.csv"))
        if not files:
            raise FileNotFoundError(f"no NOAA file for station {name} in {noaa_dir}")
        frames.append((w, read_station_degree_days(files[0])))
    idx = frames[0][1].index
    for _, d in frames[1:]:
        idx = idx.union(d.index)
    den = sum(w * d["hdd"].reindex(idx).notna() for w, d in frames)
    out = pd.DataFrame({k: sum(w * d[k].reindex(idx).fillna(0.0) for w, d in frames) / den.where(den > 0)
                        for k in ("hdd", "cdd")})
    return out.reindex(pd.date_range(idx.min(), idx.max(), freq="D")).ffill()


def build_daily_panel(hourly: pd.DataFrame, hh: pd.Series, dd: pd.DataFrame, min_rows: int = MIN_ROWS_PER_DAY
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily panel (13 contract columns + is_onpeak_day) and a coverage table of dropped days.

    A day is kept only if each of WEST DA/RT and N.Y.C. RT has >= min_rows valid hourly rows and the NYCA load is
    complete for >= min_rows hours; hh, hdd, cdd must exist (hh and degree days are forward-filled).
    Returns (panel, dropped) with dropped columns date, reason.
    """
    days = pd.DatetimeIndex(sorted(hourly["date"].unique()))
    flags = day_flag_series(days)
    wh_da = daily_means(hourly, "wh_da", flags)
    wh_rt = daily_means(hourly, "wh_rt", flags)
    dom_rt = daily_means(hourly, "dom_rt", flags)
    peak = hourly.dropna(subset=["load_mw"]).groupby("date")["load_mw"].agg(["max", "count"])
    panel = pd.DataFrame(index=days)
    panel["wh_on"], panel["wh_off"] = wh_rt["on"], wh_rt["off"]
    panel["dom_on"], panel["dom_off"] = dom_rt["on"], dom_rt["off"]
    panel["da_wh_off"], panel["rt_wh_off"] = wh_da["off"], wh_rt["off"]
    panel["da_wh_on"], panel["rt_wh_on"] = wh_da["on"], wh_rt["on"]
    panel["load_peak_mw"] = peak["max"]
    panel["hh_usd"] = hh.reindex(days).ffill()
    panel["hdd"], panel["cdd"] = dd["hdd"].reindex(days), dd["cdd"].reindex(days)
    panel["is_onpeak_day"] = flags.reindex(days).to_numpy()
    reasons: dict[pd.Timestamp, str] = {}
    counts = {"wh_da": wh_da["n_rows"], "wh_rt": wh_rt["n_rows"], "dom_rt": dom_rt["n_rows"], "load": peak["count"]}
    for d in days:
        bad = [k for k, c in counts.items() if c.get(d, 0) < min_rows]
        bad += [c for c in ("wh_on", "dom_on", "da_wh_on", "hh_usd", "hdd", "cdd") if pd.isna(panel.at[d, c])]
        if bad:
            reasons[d] = ",".join(dict.fromkeys(bad))
    dropped = pd.DataFrame({"date": list(reasons), "reason": list(reasons.values())})
    panel = panel.drop(index=list(reasons)).rename_axis("date").reset_index()
    panel = panel[[*PANEL_COLUMNS, "is_onpeak_day"]]
    return panel, dropped


def onpeak_day_window_check(panel: pd.DataFrame) -> dict[str, int]:
    """Counts of on-peak days and non-on-peak days in a panel (diagnostic)."""
    f = panel["is_onpeak_day"].to_numpy(dtype=bool)
    return {"onpeak_days": int(f.sum()), "other_days": int((~f).sum())}


def dumps_json(obj) -> str:
    """JSON with numpy/pandas scalars and timestamps converted."""
    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (pd.Timestamp,)):
            return o.strftime("%Y-%m-%d")
        raise TypeError(type(o))
    return json.dumps(obj, indent=1, default=default)


# Verified event table, plan sec 8 (its '20-23 Jan' DA ranges only match 20-22 Jan; RT range matches 20-23 Jan): (event, dates, metric, expected value or (low, high) over the dates)
EVENT_TABLE: tuple[tuple[str, tuple[str, ...], str, float | tuple[float, float]], ...] = (
    ("Polar vortex 2014", ("2014-01-07",), "wh_da_on", 137.3),
    ("Polar vortex 2014", ("2014-01-07",), "wh_rt_on", 354.4),
    ("Polar vortex 2014", ("2014-01-07",), "dom_da_on", 224.8),
    ("Polar vortex 2014", ("2014-01-07",), "dom_rt_on", 509.5),
    ("Polar vortex 2014", ("2014-01-07",), "nyca_peak", 25737.8),
    ("Elliott 2022", ("2022-12-23",), "wh_da_on", 82.8),
    ("Elliott 2022", ("2022-12-23",), "wh_rt_on", 229.6),
    ("Elliott 2022", ("2022-12-23",), "dom_da_on", 141.6),
    ("Elliott 2022", ("2022-12-23",), "dom_rt_on", 568.1),
    ("Elliott 2022", ("2022-12-24",), "nyca_peak", 22003.9),
    ("Cold Jan 2025", ("2025-01-20", "2025-01-21", "2025-01-22"), "wh_da_on", (193.5, 227.9)),
    ("Cold Jan 2025", ("2025-01-20", "2025-01-21", "2025-01-22", "2025-01-23"), "wh_rt_on", (115.7, 200.1)),
    ("Cold Jan 2025", ("2025-01-20", "2025-01-21", "2025-01-22"), "dom_da_on", (301.0, 328.0)),
    ("Cold Jan 2025", ("2025-01-22",), "nyca_peak", 23521.3),
    ("Heat Jun 2025", ("2025-06-23",), "wh_da_on", 131.6),
    ("Heat Jun 2025", ("2025-06-24",), "wh_da_on", 144.5),
    ("Heat Jun 2025", ("2025-06-25",), "wh_da_on", 112.0),
    ("Heat Jun 2025", ("2025-06-23",), "wh_rt_on", 270.5),
    ("Heat Jun 2025", ("2025-06-24",), "wh_rt_on", 416.5),
    ("Heat Jun 2025", ("2025-06-25",), "wh_rt_on", 188.8),
    ("Heat Jun 2025", ("2025-06-24",), "dom_da_on", 181.8),
    ("Heat Jun 2025", ("2025-06-24",), "dom_rt_on", 625.5),
    ("Heat Jun 2025", ("2025-06-24",), "nyca_peak", 31857.2),
)


def event_metrics(hourly: pd.DataFrame) -> pd.DataFrame:
    """Per-date hour-beginning 7..22 means of wh_da, wh_rt, dom_da, dom_rt (columns *_on) and NYCA daily peak (nyca_peak).

    The 7..22 window is used regardless of weekday/holiday so event days can be compared as in the plan table.
    """
    h = hourly[onpeak_mask(hourly["hour"])]
    out = h.groupby("date")[["wh_da", "wh_rt", "dom_da", "dom_rt"]].mean().add_suffix("_on")
    out["nyca_peak"] = hourly.groupby("date")["load_mw"].max()
    return out


def validate_events(hourly: pd.DataFrame, table=EVENT_TABLE) -> pd.DataFrame:
    """Compare event metrics with the verified table; ranges give two rows (min and max over the dates).

    Columns: event, dates, metric, side, expected, actual, diff_pct (100*(actual/expected-1)); missing dates give NaN.
    """
    m = event_metrics(hourly)
    rows = []
    for event, dates, metric, exp in table:
        vals = [m[metric].get(pd.Timestamp(d), np.nan) for d in dates]
        if isinstance(exp, tuple):
            pairs = [("min", exp[0], np.nanmin(vals) if not np.isnan(vals).all() else np.nan),
                     ("max", exp[1], np.nanmax(vals) if not np.isnan(vals).all() else np.nan)]
        else:
            pairs = [("value", exp, vals[0])]
        for side, e, a in pairs:
            rows.append({"event": event, "dates": ",".join(dates), "metric": metric, "side": side, "expected": e,
                         "actual": float(a), "diff_pct": float(100 * (a / e - 1))})
    return pd.DataFrame(rows)
