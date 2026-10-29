"""The browser engine port must reproduce the Python engine on the stored reference cases (needs node and ui/data/engine.json)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None or not (ROOT / "ui" / "data" / "engine.json").exists(), reason="node or engine.json missing")
def test_js_port_matches_python_reference_cases():
    r = subprocess.run(["node", str(ROOT / "ui" / "check_engine.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 mismatches" in r.stdout
