"""Run manifest: what exactly produced a result (plan sections 8 and 12).

write_run_manifest records, to outputs/<run>/manifest.json: data file sha256 and download dates (from the
data/raw MANIFEST.json files and the data/processed *manifest.json files), market/config, model ID, temperature and
seed, prompt version and hash, a git-less package version string, and python/numpy/pandas versions.
verify_manifest re-hashes the files named in a manifest and reports mismatches. No network access.
Hashes are sha256 hex digests; times are UTC ISO strings.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

import revstress
from revstress import config
from revstress.agent import prompts
from revstress.market import get_market

PACKAGE_DIR = Path(revstress.__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DEFAULT_DATA_ROOT = PROJECT_DIR / "data"
DEFAULT_OUTPUTS_ROOT = PROJECT_DIR / "outputs"
MANIFEST_NAME = "manifest.json"
CONFIG_KEYS: tuple[str, ...] = (
    "MARKET", "LOSS_TARGET_USD", "ALLOCATED_CAPITAL_USD", "Q_ADVERSE_MAX", "Q_SEVERE_MAX", "WINDOW_DAYS",
    "ITERATIONS_PER_SEED", "N_SEEDS", "SCENARIOS_PER_CALL", "EARLY_STOP_BREACHES", "DISTINCT_TAU_Z", "FALLBACK_BOOK",
)

EXTRA_RAW_INPUTS: dict[str, str] = {
    "eia_gas_ice/hh_daily_2013-12_onward_parsed.csv": "https://www.eia.gov/dnav/ng/hist/rngwhhdD.htm (parsed from RNGWHHDd.xls)",
}


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    """sha256 hex digest of a file, streamed."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def package_version(package_dir: str | Path = PACKAGE_DIR) -> str:
    """Git-less version string '<__version__>+src.<12 hex>': sha256 over the relative names and bytes of all .py files."""
    root = Path(package_dir)
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(p.read_bytes())
    return f"{revstress.__version__}+src.{h.hexdigest()[:12]}"


def _raw_candidates(raw: Path, mdir: Path, rel: str) -> list[Path]:
    name = Path(rel).name
    return [
        mdir / rel,
        raw / rel,
        raw / "nyiso_gas_weather" / rel,
        mdir / name,
        raw / "nyiso_load" / name,
        raw / "nyiso_prices" / name,
    ]


def _resolve_raw(raw: Path, mdir: Path, rel: str) -> Path | None:
    for c in _raw_candidates(raw, mdir, rel):
        if c.is_file():
            return c
    return None


def collect_data_records(data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    """Data file hashes and download dates as recorded by the loaders' manifests under data_root.

    {'raw': {rel: {sha256, downloaded_utc, source}}, 'processed': {rel: {sha256, built_utc, source}},
    'processed_labels': {manifest: label}, 'panel_date_range': {manifest: [min, max]}}. Nothing is re-hashed here.
    Missing directories give empty sections.
    """
    root = Path(data_root)
    out: dict[str, Any] = {"raw": {}, "processed": {}, "processed_labels": {}, "panel_date_range": {}}
    raw = root / "raw"
    if raw.is_dir():
        for mpath in sorted(raw.rglob("MANIFEST.json")):
            man = json.loads(mpath.read_text(encoding="utf-8"))
            for rel, rec in sorted(man.get("files", {}).items()):
                out["raw"][rel] = {
                    "sha256": rec.get("sha256"),
                    "downloaded_utc": rec.get("downloaded_utc"),
                    "source": mpath.relative_to(root).as_posix(),
                }
    for rel, url in EXTRA_RAW_INPUTS.items():
        p = raw / rel
        if p.is_file() and rel not in out["raw"]:
            out["raw"][rel] = {
                "sha256": sha256_file(p),
                "downloaded_utc": None,
                "file_mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_url": url,
            }
    proc = root / "processed"
    if proc.is_dir():
        for mpath in sorted(proc.glob("*manifest.json")):
            man = json.loads(mpath.read_text(encoding="utf-8"))
            src = mpath.relative_to(root).as_posix()
            out["processed_labels"][src] = man.get("label")
            for key in ("panel", "replay_2014"):
                ent = man.get(key)
                if isinstance(ent, Mapping) and ent.get("file"):
                    out["processed"][ent["file"]] = {"sha256": ent.get("sha256"), "built_utc": man.get("built_utc"), "source": src}
                    if key == "panel":
                        out["panel_date_range"][src] = [ent.get("date_min"), ent.get("date_max")]
    return out


def write_run_manifest(
    run: str,
    *,
    model: str,
    temperature: float | None,
    seed: int | None,
    prompt_version: str,
    prompt_hash: str | None = None,
    system: str | None = None,
    messages: Sequence[Mapping[str, str]] | None = None,
    market: str | None = None,
    label: str | None = None,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    outputs_root: str | Path = DEFAULT_OUTPUTS_ROOT,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write outputs_root/<run>/manifest.json and return its path.

    prompt_hash is given, or computed from system and messages (prompts.prompt_hash). market=None is the active market.
    label is a free text provenance label (e.g. 'FAKE CLIENT - not Claude results', 'SYNTHETIC', or the real data range);
    it must be given for any non-real run. temperature None means the API default was used (not set by this code).
    """
    if prompt_hash is None:
        if system is None or messages is None:
            raise ValueError("give prompt_hash, or both system and messages")
        prompt_hash = prompts.prompt_hash(system, messages)
    mkt = get_market(config.MARKET if market is None else market)
    data = collect_data_records(data_root)
    manifest: dict[str, Any] = {
        "run": run,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label": label,
        "market": {
            "name": mkt.name,
            "reference_zone": mkt.reference_zone,
            "pocket_zone": mkt.pocket_zone,
            "energy_cap_usd": mkt.energy_cap_usd,
            "cap_is_assumption": mkt.cap_is_assumption,
        },
        "config": {**{k: getattr(config, k) for k in CONFIG_KEYS if hasattr(config, k)}, "MARKET": mkt.name},
        "model": {"id": model, "temperature": temperature, "seed": seed},
        "prompt": {"version": prompt_version, "sha256": prompt_hash},
        "package": {"name": "revstress", "version": package_version()},
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "platform": platform.platform(),
        },
        "data": data,
        "extra": dict(extra) if extra else {},
    }
    path = Path(outputs_root) / run / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True, default=str), encoding="utf-8")
    return path


def verify_manifest(
    manifest_path: str | Path,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    check_raw: bool = True,
    check_package: bool = True,
) -> dict[str, Any]:
    """Compare a written manifest with the current files; returns a report dict (no exception on mismatch).

    {'ok': bool, 'checked': int, 'mismatched': [rel], 'missing': [rel], 'package_ok': bool | None,
    'prompt_hash': recorded hash (informational)}. Processed files are looked up in data_root/processed, raw files via
    the loader layout (data_root/raw/..., see _resolve_raw); a raw file with no recorded hash is unchecked. check_raw=False
    skips hashing the (large) raw files; check_package=False skips the package source digest.
    """
    man = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    root = Path(data_root)
    mismatched: list[str] = []
    missing: list[str] = []
    checked = 0
    for rel, rec in man.get("data", {}).get("processed", {}).items():
        p = root / "processed" / rel
        if not p.is_file():
            missing.append(f"processed/{rel}")
        elif rec.get("sha256") and sha256_file(p) != rec["sha256"]:
            mismatched.append(f"processed/{rel}")
            checked += 1
        else:
            checked += 1
    if check_raw:
        raw = root / "raw"
        for rel, rec in man.get("data", {}).get("raw", {}).items():
            mdir = (root / rec.get("source", "")).parent if rec.get("source") else raw
            p = _resolve_raw(raw, mdir, rel)
            if p is None:
                missing.append(f"raw/{rel}")
            elif rec.get("sha256"):
                checked += 1
                if sha256_file(p) != rec["sha256"]:
                    mismatched.append(f"raw/{rel}")
    package_ok: bool | None = None
    if check_package:
        package_ok = man.get("package", {}).get("version") == package_version()
    ok = not mismatched and not missing and package_ok is not False
    return {
        "ok": ok,
        "checked": checked,
        "mismatched": sorted(mismatched),
        "missing": sorted(missing),
        "package_ok": package_ok,
        "prompt_hash": man.get("prompt", {}).get("sha256"),
    }
