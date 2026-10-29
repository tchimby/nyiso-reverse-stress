"""NYISO loader tests: hand-made in-memory zips and CSVs only, no network."""
import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from revstress.data import fetch_nyiso, nyiso
from revstress.panel import PANEL_COLUMNS, validate_panel


def hours_for(day: pd.Timestamp) -> list[int]:
    """Hour-beginning stamps of a local day by row order (DST aware)."""
    if day == pd.Timestamp("2024-03-10"):
        return [h for h in range(24) if h != 2]
    if day == pd.Timestamp("2024-11-03"):
        return [0, 1, 1] + list(range(2, 24))
    return list(range(24))


def price_zip(days, fn, zones=("WEST", "N.Y.C.", "CAPITL"), next_day_row=False) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for d in days:
            d = pd.Timestamp(d)
            lines = ['"Time Stamp","Name","PTID","LBMP ($/MWHr)","Marginal Cost Losses ($/MWHr)","Marginal Cost Congestion ($/MWHr)"']
            hrs = hours_for(d)
            for zone in zones:
                for i, h in enumerate(hrs):
                    lines.append(f'"{d:%m/%d/%Y} {h:02d}:00","{zone}",1,{fn(zone, d, h, i)},0,0')
                if next_day_row:
                    lines.append(f'"{d + pd.Timedelta(days=1):%m/%d/%Y} 00:00","{zone}",1,9999,0,0')
            z.writestr(f"{d:%Y%m%d}rtlbmp_zone.csv", "\n".join(lines))
        z.writestr("readme.txt", "not parsed")
    buf.seek(0)
    return buf


def load_zip(days, fn, zones=nyiso.NYCA_LOAD_ZONES) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for d in days:
            d = pd.Timestamp(d)
            lines = ['"Time Stamp","Time Zone","Name","PTID","Integrated Load"']
            for zone in zones:
                for i, h in enumerate(hours_for(d)):
                    lines.append(f'"{d:%m/%d/%Y} {h:02d}:00:00","EST","{zone}",1,{fn(zone, d, h, i)}')
            z.writestr(f"{d:%Y%m%d}palIntegrated.csv", "\n".join(lines))
    buf.seek(0)
    return buf


def test_dst_row_counts_and_next_day_row_dropped():
    days = ["2024-03-09", "2024-03-10", "2024-11-02", "2024-11-03"]
    df = nyiso.read_zip_csv(price_zip(days, lambda z, d, h, i: 10.0, next_day_row=True))
    west = nyiso.parse_lbmp(df, "WEST")
    counts = west.groupby("date").size()
    assert counts[pd.Timestamp("2024-03-09")] == 24
    assert counts[pd.Timestamp("2024-03-10")] == 23
    assert counts[pd.Timestamp("2024-11-03")] == 25
    assert (west["price"] == 10.0).all()  # 9999 next-day rows gone
    fall = west[west["date"] == pd.Timestamp("2024-11-03")]
    assert sorted(fall.loc[fall["hour"] == 1, "occ"]) == [0, 1]


def test_csv_only_members_parsed():
    df = nyiso.read_zip_csv(price_zip(["2024-01-02"], lambda z, d, h, i: 1.0))
    assert set(df["file_date"]) == {pd.Timestamp("2024-01-02")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "x")
    with pytest.raises(ValueError):
        nyiso.read_zip_csv(buf)


def test_holiday_rule_mlk_is_not_nerc_holiday():
    s = nyiso.day_flag_series(pd.DatetimeIndex(["2025-01-20", "2025-01-01", "2025-07-04", "2025-12-25", "2023-01-01",
                                               "2023-01-02", "2025-05-26", "2025-09-01", "2025-11-27", "2025-06-24",
                                               "2025-06-28", "2025-11-28", "2026-07-03"]))
    assert s["2025-01-20"]  # MLK day: on-peak day
    assert not s["2025-01-01"] and not s["2025-07-04"] and not s["2025-12-25"]
    assert not s["2023-01-01"] and not s["2023-01-02"]  # Sunday holiday observed Monday
    assert not s["2025-05-26"] and not s["2025-09-01"] and not s["2025-11-27"]
    assert s["2025-06-24"] and s["2025-11-28"]
    assert not s["2025-06-28"]  # Saturday
    assert s["2026-07-03"]  # July 4 2026 is a Saturday: not observed on Friday


def test_weekend_handling_daily_means():
    days = pd.date_range("2025-06-20", "2025-06-23")  # Fri, Sat, Sun, Mon
    rows = [(d, h, 100.0 if 7 <= h <= 22 else 20.0) for d in days for h in range(24)]
    hourly = pd.DataFrame(rows, columns=["date", "hour", "x"])
    flags = nyiso.day_flag_series(pd.DatetimeIndex(days))
    out = nyiso.daily_means(hourly, "x", flags)
    fri, sat = out.loc["2025-06-20"], out.loc["2025-06-21"]
    assert fri["on"] == pytest.approx(100.0) and fri["off"] == pytest.approx(20.0)
    assert sat["on"] == pytest.approx(100.0)  # informational window mean
    assert sat["off"] == pytest.approx((16 * 100 + 8 * 20) / 24)  # all 24 h


def test_fall_back_day_off_peak_rows():
    d = pd.Timestamp("2024-11-03")
    df = nyiso.read_zip_csv(price_zip([d], lambda z, dd, h, i: float(i)))
    west = nyiso.parse_lbmp(df, "WEST").assign(x=lambda t: t["price"])
    out = nyiso.daily_means(west, "x", pd.Series({d: True}))  # force an on-peak day to count off-peak rows
    assert out.loc[d, "n_rows"] == 25 and out.loc[d, "n_on_rows"] == 16
    assert out.loc[d, "off"] == pytest.approx(np.mean(list(range(8)) + [24]))


def test_load_sum_of_eleven_zones_and_incomplete_hour_nan():
    day = "2025-06-24"
    z = load_zip([day], lambda zone, d, h, i: 100.0 + (50.0 if zone == "N.Y.C." and h == 17 else 0.0))
    out = nyiso.parse_nyca_load(nyiso.read_zip_csv(z))
    assert len(out) == 24 and out["load_mw"].iloc[0] == pytest.approx(1100.0)
    assert out["load_mw"].max() == pytest.approx(1150.0)
    short = nyiso.parse_nyca_load(nyiso.read_zip_csv(load_zip([day], lambda *a: 1.0, zones=nyiso.NYCA_LOAD_ZONES[:10])))
    assert short["load_mw"].isna().all()
    fall = nyiso.parse_nyca_load(nyiso.read_zip_csv(load_zip(["2024-11-03"], lambda *a: 1.0)))
    assert len(fall) == 25


def make_noaa(tmp_path, name, tmax_c, tmin_c, dates):
    sid = nyiso.STATION_IDS[name]
    df = pd.DataFrame({"STATION": sid, "DATE": dates, "TMAX": int(tmax_c * 10), "TMIN": int(tmin_c * 10)})
    df.to_csv(tmp_path / f"{name}_{sid}.csv", index=False)


def test_degree_days_weights_and_units(tmp_path):
    dates = ["2025-01-01", "2025-01-02"]
    make_noaa(tmp_path, "NYC_CentralPark", 0, -10, dates)  # mean -5C = 23F -> hdd 42
    for n in ("ALB", "BUF", "SYR"):
        make_noaa(tmp_path, n, 10, 0, dates)  # mean 5C = 41F -> hdd 24
    dd = nyiso.weighted_degree_days(tmp_path)
    assert dd["hdd"].iloc[0] == pytest.approx(0.5 * 42 + 0.5 * 24)
    assert (dd["cdd"] == 0).all()


def test_henry_hub_forward_fill(tmp_path):
    p = tmp_path / "hh.csv"
    pd.DataFrame({"date": ["2025-01-02", "2025-01-03", "2025-01-06"], "hh_usd": [3.0, None, 4.0]}).to_csv(p, index=False)
    s = nyiso.load_henry_hub(p)
    assert s["2025-01-03"] == 3.0 and s["2025-01-05"] == 3.0 and s["2025-01-06"] == 4.0


def px(zone, d, h, i):
    return 50.0 + (30.0 if zone == "N.Y.C." else 0.0) + h


def build_fixture(days):
    rt = nyiso.read_zip_csv(price_zip(days, px))
    da = nyiso.read_zip_csv(price_zip(days, lambda z, d, h, i: px(z, d, h, i) - 5.0))
    ld = nyiso.read_zip_csv(load_zip(days, lambda zone, d, h, i: 1000.0 + 10 * h))
    key = ["date", "hour", "occ"]
    parts = []
    for pref, zone in (("wh", "WEST"), ("dom", "N.Y.C.")):
        parts.append(nyiso.parse_lbmp(da, zone).rename(columns={"price": f"{pref}_da"}).set_index(key))
        parts.append(nyiso.parse_lbmp(rt, zone).rename(columns={"price": f"{pref}_rt"}).set_index(key))
    parts.append(nyiso.parse_nyca_load(ld).set_index(key))
    return pd.concat(parts, axis=1).sort_index().reset_index()


def test_panel_column_contract_and_settlement():
    days = pd.date_range("2025-06-20", "2025-06-30")
    hourly = build_fixture(days)
    hh = pd.Series(3.5, index=pd.date_range("2025-06-01", "2025-06-30"))
    dd = pd.DataFrame({"hdd": 0.0, "cdd": 10.0}, index=hh.index)
    panel, dropped = nyiso.build_daily_panel(hourly, hh, dd)
    assert dropped.empty
    assert list(panel.columns) == [*PANEL_COLUMNS, "is_onpeak_day"]
    validate_panel(panel, fallback=False)
    assert (panel["wh_on"] == panel["rt_wh_on"]).all() and (panel["wh_off"] == panel["rt_wh_off"]).all()
    fri = panel[panel["date"] == "2025-06-20"].iloc[0]
    assert fri["wh_on"] == pytest.approx(50 + np.mean(range(7, 23)))
    assert fri["wh_off"] == pytest.approx(50 + np.mean(list(range(7)) + [23]))
    assert fri["dom_on"] - fri["wh_on"] == pytest.approx(30.0)
    assert fri["da_wh_on"] == pytest.approx(fri["rt_wh_on"] - 5.0)
    assert fri["load_peak_mw"] == pytest.approx(11 * (1000 + 230))
    sat = panel[panel["date"] == "2025-06-21"].iloc[0]
    assert not sat["is_onpeak_day"] and sat["wh_off"] == pytest.approx(50 + 11.5)  # all-24-h mean


def test_short_day_is_dropped_and_reported():
    days = pd.date_range("2025-06-23", "2025-06-24")
    hourly = build_fixture(days)
    hourly = hourly[~((hourly["date"] == "2025-06-24") & (hourly["hour"] < 10))]
    hh = pd.Series(3.5, index=pd.date_range("2025-06-01", "2025-06-30"))
    dd = pd.DataFrame({"hdd": 0.0, "cdd": 1.0}, index=hh.index)
    panel, dropped = nyiso.build_daily_panel(hourly, hh, dd)
    assert list(panel["date"]) == [pd.Timestamp("2025-06-23")]
    assert dropped.iloc[0]["date"] == pd.Timestamp("2025-06-24")


def test_validate_events_structure():
    hourly = build_fixture(pd.date_range("2025-06-23", "2025-06-25"))
    val = nyiso.validate_events(hourly)
    assert {"event", "metric", "expected", "actual", "diff_pct"} <= set(val.columns)
    row = val[(val["event"] == "Heat Jun 2025") & (val["metric"] == "wh_rt_on") & (val["dates"] == "2025-06-24")].iloc[0]
    assert row["actual"] == pytest.approx(50 + np.mean(range(7, 23)))
    assert val["actual"].isna().any()  # dates not in the fixture


def test_fetch_helpers_offline(tmp_path):
    assert fetch_nyiso.month_starts("2019-11", "2020-02") == ["20191101", "20191201", "20200101", "20200201"]
    url, path = fetch_nyiso.product_url("palIntegrated", "20250601")
    assert url == "http://mis.nyiso.com/public/csv/palIntegrated/20250601palIntegrated_csv.zip"
    url, path = fetch_nyiso.product_url("rtlbmp", "20250601")
    assert url.endswith("/rtlbmp/20250601rtlbmp_zone_csv.zip") and path.parent.name == "nyiso_prices"
    bad = tmp_path / "x.zip"
    bad.write_text("<html>")
    assert not fetch_nyiso.is_valid_zip(bad)
    good = tmp_path / "y.zip"
    good.write_bytes(price_zip(["2025-01-02"], lambda *a: 1.0).getvalue())
    assert fetch_nyiso.is_valid_zip(good) and len(fetch_nyiso.sha256_file(good)) == 64
