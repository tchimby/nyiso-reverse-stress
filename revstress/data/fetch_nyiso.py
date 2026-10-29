"""Polite, resumable downloader for the public NYISO MIS monthly zips and NOAA GHCN-Daily station files.

Network access happens ONLY when main() / download_* are called (never at import, never in tests).
Rules: at most 1 request per second, no registration, retries with exponential backoff, existing valid files are
skipped, every file gets sha256 + UTC download timestamp in data/raw/nyiso_prices/MANIFEST.json. Downloaded
files are untrusted: they are only checked as zip archives and parsed later, never executed.

Products (month-start file names): damlbmp/YYYYMM01damlbmp_zone_csv.zip, rtlbmp/YYYYMM01rtlbmp_zone_csv.zip
(hourly integrated real time), palIntegrated/YYYYMM01palIntegrated_csv.zip (hourly load by zone).
The 5-minute 'realtime' product is deliberately not downloaded.

Usage: python -E -P -m revstress.data.fetch_nyiso [--start 2019-01] [--end 2026-09] [--no-noaa]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
PRICES_DIR = RAW / "nyiso_prices"
LOAD_DIR = RAW / "nyiso_load"
NOAA_DIR = RAW / "nyiso_gas_weather" / "noaa"
MANIFEST = PRICES_DIR / "MANIFEST.json"
BASE_URL = "http://mis.nyiso.com/public/csv"
NOAA_URL = "https://www.ncei.noaa.gov/data/daily-summaries/access/{sid}.csv"
PRODUCTS: dict[str, tuple[str, str, Path]] = {
    "damlbmp": ("damlbmp", "damlbmp_zone_csv", PRICES_DIR),
    "rtlbmp": ("rtlbmp", "rtlbmp_zone_csv", PRICES_DIR),
    "palIntegrated": ("palIntegrated", "palIntegrated_csv", LOAD_DIR),
}
NOAA_STATIONS = {"NYC_CentralPark": "USW00094728", "LGA": "USW00014732", "JFK": "USW00094789",
                 "ALB": "USW00014735", "BUF": "USW00014733", "SYR": "USW00014771"}
MIN_INTERVAL_S = 1.0
MAX_RETRIES = 4
USER_AGENT = "revstress-research-prototype/0.1 (academic coursework; polite 1 req/s)"
_last_request = [0.0]


def month_starts(start: str, end: str) -> list[str]:
    """Month-start stamps 'YYYYMM01' from 'YYYY-MM' start to end inclusive."""
    y, m = int(start[:4]), int(start[5:7])
    ye, me = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ye, me):
        out.append(f"{y:04d}{m:02d}01")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def product_url(product: str, stamp: str) -> tuple[str, Path]:
    """URL and local path for one monthly product file."""
    folder, suffix, directory = PRODUCTS[product]
    name = f"{stamp}{suffix}.zip"
    return f"{BASE_URL}/{folder}/{name}", directory / name


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None and len(z.namelist()) > 0
    except (zipfile.BadZipFile, OSError):
        return False


def _throttle() -> None:
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def http_get(url: str, timeout: float = 120.0) -> bytes:
    """GET with the 1 request/second throttle and exponential backoff; raises on final failure (404 is not retried)."""
    delay = 2.0
    for attempt in range(MAX_RETRIES + 1):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or attempt == MAX_RETRIES:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == MAX_RETRIES:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def load_manifest(path: Path = MANIFEST) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"files": {}, "failures": {}}


def save_manifest(man: dict, path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, indent=1, sort_keys=True), encoding="utf-8")


def _record(man: dict, rel: str, url: str, path: Path, preexisting: bool) -> None:
    ts = datetime.fromtimestamp(path.stat().st_mtime if preexisting else time.time(), tz=timezone.utc)
    man["files"][rel] = {"url": url, "sha256": sha256_file(path), "bytes": path.stat().st_size,
                         "downloaded_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "note": "preexisting file, time = file mtime" if preexisting else "downloaded by fetch_nyiso"}
    man["failures"].pop(rel, None)


def download_months(stamps: list[str], products=("damlbmp", "rtlbmp", "palIntegrated"), manifest_path: Path = MANIFEST,
                    log=print) -> dict:
    """Download missing/invalid monthly zips; returns the manifest. Failures are logged and recorded, never raised."""
    man = load_manifest(manifest_path)
    todo = [(p, s) for s in stamps for p in products]
    for i, (prod, stamp) in enumerate(todo, 1):
        url, path = product_url(prod, stamp)
        rel = f"{path.parent.name}/{path.name}"
        if path.exists() and is_valid_zip(path):
            if rel not in man["files"]:
                _record(man, rel, url, path, preexisting=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = http_get(url)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            if not is_valid_zip(tmp):
                tmp.unlink()
                raise ValueError("response is not a valid zip")
            tmp.replace(path)
            _record(man, rel, url, path, preexisting=False)
            log(f"[{i}/{len(todo)}] ok   {rel} ({len(data)} bytes)")
        except Exception as e:  # logged and recorded; the run continues
            man["failures"][rel] = {"url": url, "error": f"{type(e).__name__}: {e}",
                                    "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            log(f"[{i}/{len(todo)}] FAIL {rel}: {e}")
        if i % 10 == 0:
            save_manifest(man, manifest_path)
    save_manifest(man, manifest_path)
    return man


def download_noaa(stations: dict[str, str] = NOAA_STATIONS, out_dir: Path = NOAA_DIR, refresh: bool = False,
                  manifest_path: Path = MANIFEST, log=print) -> None:
    """Download GHCN-Daily station CSVs that are missing (or all if refresh); hashes go into the manifest."""
    man = load_manifest(manifest_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, sid in stations.items():
        path = out_dir / f"{name}_{sid}.csv"
        rel = f"noaa/{path.name}"
        if path.exists() and not refresh:
            if rel not in man["files"]:
                _record(man, rel, NOAA_URL.format(sid=sid), path, preexisting=True)
            continue
        try:
            data = http_get(NOAA_URL.format(sid=sid), timeout=300)
            if not data.startswith(b'"STATION"'):
                raise ValueError("unexpected NOAA response")
            path.write_bytes(data)
            _record(man, rel, NOAA_URL.format(sid=sid), path, preexisting=False)
            log(f"ok   {rel} ({len(data)} bytes)")
        except Exception as e:
            man["failures"][rel] = {"url": NOAA_URL.format(sid=sid), "error": f"{type(e).__name__}: {e}"}
            log(f"FAIL {rel}: {e}")
    save_manifest(man, manifest_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2019-01")
    ap.add_argument("--end", default="2026-09", help="last complete month")
    ap.add_argument("--no-noaa", action="store_true")
    a = ap.parse_args(argv)
    stamps = ["20140101"] + month_starts(a.start, a.end)
    man = download_months(stamps)
    if not a.no_noaa:
        download_noaa()
    print(f"files in manifest: {len(man['files'])}; failures: {len(man['failures'])}")
    for rel, f in sorted(man["failures"].items()):
        print("  FAILED", rel, f["error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
