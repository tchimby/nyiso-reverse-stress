"""Load ANTHROPIC_API_KEY from a .env file into the process environment without ever exposing the value.

The key is never returned, printed or logged; callers only learn whether it is available and a masked status.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import MutableMapping

KEY_NAME: str = "ANTHROPIC_API_KEY"


def parse_env_line(line: str) -> tuple[str, str] | None:
    """(name, value) for a KEY=VALUE line (optional 'export ' prefix and quotes), else None for blanks and comments."""
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    name, _, value = line.partition("=")
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return name.strip(), value


def load_api_key(path: str | Path, environ: MutableMapping[str, str] | None = None, name: str = KEY_NAME) -> bool:
    """Put the key from the .env file into environ[name] unless it is already set; True if it is set afterwards.

    An existing environment variable wins over the file. A missing or unreadable file is not an error (returns the
    current availability). Only the requested variable is read from the file.
    """
    env = os.environ if environ is None else environ
    if env.get(name):
        return True
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        parsed = parse_env_line(line)
        if parsed and parsed[0] == name and parsed[1]:
            env[name] = parsed[1]
            return True
    return False


def key_status(environ: MutableMapping[str, str] | None = None, name: str = KEY_NAME) -> dict[str, object]:
    """Masked status: presence, length and expected prefix only (never the value)."""
    env = os.environ if environ is None else environ
    value = env.get(name, "")
    return {"present": bool(value), "length": len(value), "prefix_ok": value.startswith("sk-ant-")}
