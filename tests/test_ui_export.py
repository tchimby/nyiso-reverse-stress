"""UI data export: writes the five JSON files with the expected keys (skipped when no run outputs are present)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not (ROOT / "outputs" / "live_daily_sonnet" / "comparison_table.csv").exists(), reason="run outputs not present")
def test_export_writes_contract_files(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("export_ui_data", ROOT / "scripts" / "export_ui_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(tmp_path)])
    mod.main()
    for name in ("runs", "scenarios", "factors", "ablations", "meta"):
        assert (tmp_path / f"{name}.json").exists()
    sc = json.loads((tmp_path / "scenarios.json").read_text(encoding="utf-8"))
    assert sc and {"narrative", "shocks", "pnl_by_position", "pnl_by_channel", "d2", "q"} <= set(sc[0])
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["caveats"]
