"""Build data/processed/nyiso_panel.csv (2019-01 onward) and nyiso_panel_2014_replay.csv from local raw files.

Run: python -E -P scripts/build_nyiso_panel.py [--end 2026-09-30]. No network. Real data: NYISO MIS public files
(WEST, N.Y.C. LBMP; NYCA load), EIA Henry Hub, NOAA GHCN-Daily. The 2014 file is a flagged replay event only.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revstress.data import nyiso  # noqa: E402
from revstress.panel import validate_panel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-09-30")
    a = ap.parse_args()
    prices, load = RAW / "nyiso_prices", RAW / "nyiso_load"
    hourly = nyiso.build_hourly(prices, load, a.start, a.end, include=["20140101"])
    hh = nyiso.load_henry_hub()
    dd = nyiso.weighted_degree_days(RAW / "nyiso_gas_weather" / "noaa")
    panel_all, dropped = nyiso.build_daily_panel(hourly, hh, dd)
    main_p = panel_all[panel_all["date"] >= pd.Timestamp(a.start)].reset_index(drop=True)
    p2014 = panel_all[panel_all["date"] < pd.Timestamp("2015-01-01")].reset_index(drop=True)
    validate_panel(main_p, fallback=False)
    validate_panel(p2014, fallback=False)
    OUT.mkdir(parents=True, exist_ok=True)
    main_p.to_csv(OUT / "nyiso_panel.csv", index=False, float_format="%.6f")
    p2014.to_csv(OUT / "nyiso_panel_2014_replay.csv", index=False, float_format="%.6f")

    val = nyiso.validate_events(hourly)
    val.to_csv(OUT / "nyiso_event_validation.csv", index=False, float_format="%.4f")

    cal = pd.date_range(a.start, a.end, freq="D")
    dropped_main = dropped[(dropped["date"] >= pd.Timestamp(a.start)) & (dropped["date"] <= pd.Timestamp(a.end))]
    present = set(hourly["date"].unique())
    months_missing = sorted({d.strftime("%Y-%m") for d in cal if d not in present} - {d.strftime("%Y-%m") for d in present})
    man = json.loads((prices / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest = {
        "label": "REAL DATA - NYISO MIS public files (WEST, N.Y.C. LBMP; NYCA load), EIA Henry Hub, NOAA GHCN-Daily",
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": list(main_p.columns),
        "mapping": "wh_* = WEST (reference zone), dom_* = N.Y.C. (load pocket); wh_on/wh_off = RT settlement means",
        "weather_weights": nyiso.WEATHER_WEIGHTS,
        "panel": {"file": "nyiso_panel.csv", "sha256": sha(OUT / "nyiso_panel.csv"), "rows": len(main_p),
                  "date_min": main_p["date"].min(), "date_max": main_p["date"].max(),
                  "onpeak_days": int(main_p["is_onpeak_day"].sum()), "other_days": int((~main_p["is_onpeak_day"]).sum())},
        "replay_2014": {"file": "nyiso_panel_2014_replay.csv", "sha256": sha(OUT / "nyiso_panel_2014_replay.csv"),
                        "rows": len(p2014), "date_min": p2014["date"].min(), "date_max": p2014["date"].max(),
                        "note": "flagged replay event only, not in the fit window"},
        "calendar_days_requested": len(cal),
        "missing_data_share": 1 - len(main_p) / len(cal),
        "dropped_days": [{"date": r.date, "reason": r.reason} for r in dropped_main.itertuples()],
        "months_with_no_hourly_data": months_missing,
        "download_failures": man.get("failures", {}),
        "raw_files": {k: {"sha256": v["sha256"], "downloaded_utc": v["downloaded_utc"]} for k, v in sorted(man["files"].items())},
        "validation": json.loads(val.to_json(orient="records")),
    }
    (OUT / "nyiso_panel_manifest.json").write_text(nyiso.dumps_json(manifest), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(f"REAL DATA panel {main_p['date'].min().date()}..{main_p['date'].max().date()} rows={len(main_p)} "
          f"dropped={len(dropped_main)} missing share={manifest['missing_data_share']:.4f}")
    print(val.round(2).to_string())


if __name__ == "__main__":
    main()
