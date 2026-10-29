"""Claude client wrapper: on-disk cache, retry on 429/5xx only, token accounting, and a fake client.

The API key is read from the ANTHROPIC_API_KEY environment variable only. Failures are returned in
ClaudeResponse.error, never raised. FakeClient makes no network calls. Cache keys include the client kind
('live' or 'fake') and max_tokens; fake entries are prefixed 'fake-' and flagged, and never served to a live client.
A circuit breaker (max_consecutive_errors) and an optional call cap (max_total_calls) bound live volume.
Everything FakeClient returns is scripted: scenarios and cache entries carry FAKE_CLIENT_LABEL and are never Claude results.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from revstress import config
from revstress.market import Market, get_market

FAKE_CLIENT_LABEL: str = "FAKE CLIENT - not Claude results"
DEFAULT_MAX_TOKENS: int = 8192  # a live call with three scenarios can use 4k+ tokens (reasoning counts toward the limit)
MAX_TOKENS_CAP: int = 16384  # a truncated reply (stop_reason max_tokens) is retried with a doubled limit up to this cap
FATAL_STATUS_CODES: tuple[int, ...] = (400, 401, 403)  # not retryable and not fixed by repeating the prompt
MAX_RETRY_AFTER_S: float = 120.0


@dataclass
class ClaudeResponse:
    """Result of one call. error is None on success; otherwise text is empty."""

    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    cache_key: str = ""
    model: str = ""
    prompt_version: str = ""
    attempts: int = 0
    error: str | None = None
    status_code: int | None = None
    stop_reason: str | None = None  # API stop reason of the returned text ('end_turn', 'max_tokens', ...); None for fake/cache

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cache_key(
    prompt_version: str,
    model: str,
    messages: Sequence[Mapping[str, str]],
    system: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    kind: str = "live",
) -> str:
    """sha256 hex digest of (prompt version, model, system, messages, max_tokens, client kind 'live'|'fake')."""
    payload = json.dumps([prompt_version, model, system, list(messages), max_tokens, kind], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def is_fatal(resp: "ClaudeResponse") -> bool:
    """True when repeating the call cannot succeed: bad request/key (400, 401, 403), missing key, dry-run miss,
    open circuit breaker or exhausted call cap."""
    if resp.error is None:
        return False
    if resp.status_code in FATAL_STATUS_CODES:
        return True
    return resp.error.startswith(("MissingApiKeyError", "dry_run_cache_miss", "circuit_open", "max_total_calls"))


def retry_after_s(exc: BaseException) -> float | None:
    """Seconds from a Retry-After header on the exception's response, if present and numeric."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = headers.get("retry-after") if headers is not None else None
        return None if value is None else max(0.0, float(value))
    except (TypeError, ValueError, AttributeError):
        return None


def is_retryable_status(status: int | None) -> bool:
    """Retry only HTTP 429 and 5xx."""
    return status is not None and (status == 429 or 500 <= status <= 599)


class MissingApiKeyError(RuntimeError):
    """ANTHROPIC_API_KEY is not set."""


class ClaudeClient:
    """Wrapper around the anthropic SDK (SDK retries disabled; one retry layer lives here).

    max_consecutive_errors: after this many consecutive final errors complete() stops calling and returns
    'circuit_open'. max_total_calls: cap on live API attempts (None = no cap).
    """

    cache_kind: str = "live"

    def __init__(
        self,
        model: str = config.DEFAULT_MODEL,
        cache_dir: str | Path | None = None,
        max_retries: int = 4,
        base_delay_s: float = 1.0,
        max_delay_s: float = 30.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        dry_run: bool = False,
        seed: int = 0,
        sleep: Callable[[float], None] = time.sleep,
        max_consecutive_errors: int = 3,
        max_total_calls: int | None = None,
        grow_on_truncation: bool = True,
        max_tokens_cap: int = MAX_TOKENS_CAP,
    ) -> None:
        self.grow_on_truncation = grow_on_truncation
        self.max_tokens_cap = max_tokens_cap
        self._last_stop_reason: str | None = None
        self.max_consecutive_errors = max_consecutive_errors
        self.max_total_calls = max_total_calls
        self._consecutive_errors = 0
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.max_retries = max_retries
        self.base_delay_s = base_delay_s
        self.max_delay_s = max_delay_s
        self.max_tokens = max_tokens
        self.dry_run = dry_run
        self._rng = random.Random(seed)
        self._sleep = sleep
        self._sdk: Any = None
        self.totals: dict[str, int] = {"calls": 0, "cache_hits": 0, "errors": 0, "input_tokens": 0, "output_tokens": 0}

    def _backoff_s(self, attempt: int) -> float:
        """Exponential backoff with jitter for the given failed attempt number (1-based), seconds."""
        cap = min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 1))
        return cap / 2 + self._rng.uniform(0.0, cap / 2)

    def _cache_path(self, key: str) -> Path | None:
        prefix = "" if self.cache_kind == "live" else f"{self.cache_kind}-"
        return None if self.cache_dir is None else self.cache_dir / f"{prefix}{key}.json"

    def _cache_read(self, key: str) -> dict[str, Any] | None:
        path = self._cache_path(key)
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or data.get("cache_kind") != self.cache_kind:
            return None
        return {k: v for k, v in data.items() if k not in ("cache_kind", "synthetic", "label")}

    def _cache_write(self, key: str, resp: ClaudeResponse) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            entry = {**resp.to_dict(), "cache_kind": self.cache_kind, "synthetic": self.cache_kind != "live"}
            if self.cache_kind != "live":
                entry["label"] = FAKE_CLIENT_LABEL
            tmp.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass

    def _transport(self, system: str, messages: Sequence[Mapping[str, str]]) -> tuple[str, int, int]:
        """One live API call; returns (text, input_tokens, output_tokens). Raises on failure."""
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise MissingApiKeyError("ANTHROPIC_API_KEY is not set")
        if self._sdk is None:
            import anthropic

            self._sdk = anthropic.Anthropic(api_key=key, max_retries=0)
        msg = self._sdk.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=system, messages=list(messages)
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        self._last_stop_reason = getattr(msg, "stop_reason", None)
        return text, int(msg.usage.input_tokens), int(msg.usage.output_tokens)

    def complete(self, system: str, messages: Sequence[Mapping[str, str]], prompt_version: str) -> ClaudeResponse:
        """Return the cached response if present, else call the API with retry. Never raises."""
        key = cache_key(prompt_version, self.model, messages, system, self.max_tokens, self.cache_kind)
        cached = self._cache_read(key)
        if cached is not None:
            resp = ClaudeResponse(**{**cached, "cache_hit": True, "cache_key": key})
            self.totals["cache_hits"] += 1
            return resp
        if self.dry_run:
            return ClaudeResponse(
                cache_key=key, model=self.model, prompt_version=prompt_version, error="dry_run_cache_miss"
            )
        if self._consecutive_errors >= self.max_consecutive_errors:
            return ClaudeResponse(
                cache_key=key, model=self.model, prompt_version=prompt_version,
                error=f"circuit_open: {self._consecutive_errors} consecutive errors",
            )
        attempts = 0
        while True:
            if self.max_total_calls is not None and self.totals["calls"] >= self.max_total_calls:
                self.totals["errors"] += 1
                return ClaudeResponse(
                    cache_key=key, model=self.model, prompt_version=prompt_version, attempts=attempts,
                    error=f"max_total_calls reached ({self.max_total_calls})",
                )
            attempts += 1
            self.totals["calls"] += 1
            try:
                text, n_in, n_out = self._transport(system, messages)
            except Exception as exc:  # failures are returned as fields
                status = getattr(exc, "status_code", None)
                if is_retryable_status(status) and attempts <= self.max_retries:
                    wait = self._backoff_s(attempts)
                    hinted = retry_after_s(exc)
                    if hinted is not None:
                        wait = max(wait, min(hinted, MAX_RETRY_AFTER_S))
                    self._sleep(wait)
                    continue
                self.totals["errors"] += 1
                self._consecutive_errors += 1
                return ClaudeResponse(
                    cache_key=key,
                    model=self.model,
                    prompt_version=prompt_version,
                    attempts=attempts,
                    error=f"{type(exc).__name__}: {exc}",
                    status_code=status if isinstance(status, int) else None,
                )
            self._consecutive_errors = 0
            self.totals["input_tokens"] += n_in
            self.totals["output_tokens"] += n_out
            stop, self._last_stop_reason = self._last_stop_reason, None
            if stop == "max_tokens" and self.grow_on_truncation and self.max_tokens < self.max_tokens_cap:
                self.max_tokens = min(self.max_tokens * 2, self.max_tokens_cap)  # truncated JSON: spend more budget, retry
                key = cache_key(prompt_version, self.model, messages, system, self.max_tokens, self.cache_kind)
                continue
            resp = ClaudeResponse(
                text=text,
                input_tokens=n_in,
                output_tokens=n_out,
                cache_key=key,
                model=self.model,
                prompt_version=prompt_version,
                attempts=attempts,
                stop_reason=stop,
            )
            self._cache_write(key, resp)
            return resp


def dry_run_report(
    system: str,
    messages: Sequence[Mapping[str, str]],
    prompt_version: str,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    kind: str = "live",
) -> str:
    """Exact prompt text and cache key as a string; makes no call."""
    key = cache_key(prompt_version, model, messages, system, max_tokens, kind)
    parts = [f"cache_key: {key}", f"prompt_version: {prompt_version}", f"model: {model}", "--- system ---", system]
    for m in messages:
        parts += [f"--- {m['role']} ---", m["content"]]
    return "\n".join(parts)


# ---------------------------------------------------------------- fake client

_TEMPLATES: dict[str, dict[str, Any]] = {
    "cold_snap": dict(season="winter", gas=60.0, ratio=1.12, wh=15.0, dart=25.0, spike_days=3, spike_avg=1500.0, dur=7),
    "heat_wave": dict(season="summer", gas=15.0, ratio=1.15, wh=20.0, dart=30.0, spike_days=3, spike_avg=1200.0, dur=6),
    "gas_supply": dict(season="winter", gas=120.0, ratio=1.02, wh=10.0, dart=10.0, spike_days=0, spike_avg=0.0, dur=10),
    "transmission": dict(season="summer", gas=5.0, ratio=1.05, wh=0.0, dart=20.0, spike_days=2, spike_avg=800.0, dur=5),
    "demand_shock_datacenter": dict(
        season="shoulder", gas=10.0, ratio=1.03, wh=10.0, dart=10.0, spike_days=0, spike_avg=0.0, dur=20, dc=3000.0
    ),
    "generator_outage": dict(season="winter", gas=30.0, ratio=1.08, wh=25.0, dart=40.0, spike_days=4, spike_avg=2000.0, dur=8),
    "policy": dict(season="shoulder", gas=0.0, ratio=1.0, wh=30.0, dart=15.0, spike_days=0, spike_avg=0.0, dur=15),
}
_FILLER = (
    "A sustained physical driver tightens the regional supply stack, lifts gas and power prices together, and widens "
    "the gap between day-ahead and real-time settlement, which reduces the value of the long position and the "
    "hedges over the stated duration, with every shock below sized to match that chain of events."
)

# NYISO-scale templates (WEST / N.Y.C., NYCA about 30 GW). Keys: gas = Henry Hub pct, basis = New York basis $/MMBtu,
# ratio = load multiplier, ll = large-load MW, ref = WEST on-peak pct, spread = N.Y.C. minus WEST $/MWh,
# spike_avg = daily on-peak average $/MWh. SCRIPTED numbers, not analysis.
_NYISO_TEMPLATES: dict[str, dict[str, Any]] = {
    "cold_snap": dict(season="winter", gas=60.0, basis=10.0, ratio=1.08, ll=0.0, ref=60.0, spread=30.0, dart=25.0, spike_days=2, spike_avg=450.0, dur=5),
    "heat_wave": dict(season="summer", gas=5.0, basis=0.0, ratio=1.10, ll=0.0, ref=50.0, spread=40.0, dart=40.0, spike_days=3, spike_avg=600.0, dur=5),
    "gas_supply": dict(season="winter", gas=80.0, basis=15.0, ratio=1.02, ll=0.0, ref=20.0, spread=15.0, dart=10.0, spike_days=0, spike_avg=0.0, dur=10),
    "transmission": dict(season="summer", gas=0.0, basis=0.0, ratio=1.04, ll=0.0, ref=0.0, spread=50.0, dart=25.0, spike_days=2, spike_avg=400.0, dur=5),
    "large_load_shortfall": dict(season="summer", gas=0.0, basis=0.0, ratio=1.0, ll=-1000.0, ref=-5.0, spread=0.0, dart=0.0, spike_days=0, spike_avg=0.0, dur=20),
    "generator_outage": dict(season="summer", gas=10.0, basis=0.0, ratio=1.05, ll=0.0, ref=40.0, spread=30.0, dart=40.0, spike_days=3, spike_avg=800.0, dur=6),
    "reserve_shortage": dict(season="summer", gas=0.0, basis=0.0, ratio=1.08, ll=0.0, ref=30.0, spread=20.0, dart=50.0, spike_days=3, spike_avg=1200.0, dur=4),
}
_NYISO_FILLER = (
    "A sustained physical driver tightens the NYCA supply stack, lifts WEST and N.Y.C. prices together, widens "
    "the N.Y.C. premium over WEST and the gap between day-ahead and real-time settlement, which reduces the value of "
    "the long positions and the hedges over the stated duration, with every shock sized to match that chain of events."
)


def _canned_nyiso(m: Market, driver_class: str, iteration: int, n: int, version: str) -> list[dict[str, Any]]:
    t = _NYISO_TEMPLATES.get(driver_class, _NYISO_TEMPLATES[m.default_driver_class])
    out = []
    for j in range(n):
        scale = 1.0 + 0.25 * iteration + 0.1 * j
        spikes = int(t["spike_days"])
        out.append(
            {
                "scenario_id": f"F-{driver_class[:4]}-{iteration:02d}-{j}",
                "prompt_version": version,
                "narrative": f"Fake scenario {iteration}.{j} for {driver_class} ({FAKE_CLIENT_LABEL}). {_NYISO_FILLER}",
                "horizon_days": 30,
                "season": t["season"],
                "driver_class": driver_class,
                "shocks": {
                    "gas_hh_pct": round(t["gas"] * scale, 3),
                    "ny_gas_basis_usd": round(t["basis"] * scale, 3),
                    "load_peak_ratio": round(1.0 + (t["ratio"] - 1.0) * scale, 4),
                    "large_load_shock_mw": round(t["ll"] * scale, 3),
                    "ref_onpeak_pct": round(t["ref"] * scale, 3),
                    "pocket_minus_ref_usd": round(t["spread"] * scale, 3),
                    "dart_pct": round(t["dart"] * scale, 3),
                    "spike_days": spikes,
                    "spike_daily_avg_usd": round(min(t["spike_avg"] * scale, m.energy_cap_usd), 3) if spikes else 0.0,
                    "duration_days": int(t["dur"]),
                },
                "stated_loss_usd": config.LOSS_TARGET_USD,
                "analogue": {"event": "", "dates": "", "claimed": {}, "source": ""},
                "confidence": "low",
            }
        )
    return out


def canned_scenarios(
    driver_class: str, iteration: int, n: int, version: str = "v3", market: "str | Market | None" = None
) -> list[dict[str, Any]]:
    """Deterministic scenarios for FakeClient; scale grows with the iteration index. Not real analysis.

    Every narrative carries FAKE_CLIENT_LABEL. market=None means the active market (config.MARKET); NYISO scenarios use
    the agent keys of plan section 5 at NYISO scale (WEST, N.Y.C., about 30 GW), PJM scenarios the PJM keys.
    """
    m = get_market(config.MARKET if market is None else market)
    if m.name != "PJM":
        return _canned_nyiso(m, driver_class, iteration, n, version)
    t = _TEMPLATES.get(driver_class, _TEMPLATES["policy"])
    out = []
    for j in range(n):
        scale = 1.0 + 0.25 * iteration + 0.1 * j
        spikes = int(t["spike_days"])
        out.append(
            {
                "scenario_id": f"F-{driver_class[:4]}-{iteration:02d}-{j}",
                "prompt_version": version,
                "narrative": f"Fake scenario {iteration}.{j} for {driver_class} ({FAKE_CLIENT_LABEL}). {_FILLER}",
                "horizon_days": 30,
                "season": t["season"],
                "driver_class": driver_class,
                "shocks": {
                    "gas_hh_pct": round(t["gas"] * scale, 3),
                    "load_peak_ratio": round(1.0 + (t["ratio"] - 1.0) * scale, 4),
                    "dc_load_shock_mw": round(t.get("dc", 0.0) * scale, 3),
                    "wh_onpeak_pct": round(t["wh"] * scale, 3),
                    "dom_minus_wh_usd": round(5.0 * scale, 3),
                    "dart_pct": round(t["dart"] * scale, 3),
                    "spike_days": spikes,
                    "spike_daily_avg_usd": round(min(t["spike_avg"] * scale, m.energy_cap_usd), 3) if spikes else 0.0,
                    "duration_days": int(t["dur"]),
                },
                "analogue": {"event": "", "dates": "", "claimed": {}, "source": ""},
                "confidence": "low",
            }
        )
    return out


class FakeClient(ClaudeClient):
    """Deterministic client with no network access (tests, dry runs).

    responses: optional sequence of strings or callables(system, messages) -> str, consumed one per live call;
    when exhausted (or None) canned scenarios for the driver family named in the first user message are used.
    Its cache entries are kept apart from live ones (kind 'fake': distinct key, 'fake-' file prefix, flagged).
    market: Market or name for the canned scenarios (None: the active market, config.MARKET, read at call time).
    Everything it returns is labelled FAKE_CLIENT_LABEL ('FAKE CLIENT - not Claude results').
    """

    cache_kind = "fake"

    def __init__(
        self,
        responses: Sequence[str | Callable[[str, Sequence[Mapping[str, str]]], str]] | None = None,
        scenarios_per_call: int = config.SCENARIOS_PER_CALL,
        market: "str | Market | None" = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("sleep", lambda s: None)
        kwargs.setdefault("model", "fake-client")
        super().__init__(**kwargs)
        self._responses = list(responses) if responses is not None else []
        self._n = scenarios_per_call
        self._market = market
        self.live_calls = 0
        self.label = FAKE_CLIENT_LABEL

    def _transport(self, system: str, messages: Sequence[Mapping[str, str]]) -> tuple[str, int, int]:
        self.live_calls += 1
        if self._responses:
            r = self._responses.pop(0)
            text = r(system, messages) if callable(r) else r
        else:
            first = messages[0]["content"]
            driver = "policy"
            for line in first.splitlines():
                if line.startswith("Driver family:"):
                    driver = line.split(":", 1)[1].strip()
            iteration = sum(1 for m in messages if m["role"] == "assistant")
            version = next((v for v in ("v3", "v2") if f'Set prompt_version to "{v}"' in first), "v1")
            text = json.dumps({"scenarios": canned_scenarios(driver, iteration, self._n, version, self._market)}, sort_keys=True)
        n_in = len(system + "".join(m["content"] for m in messages)) // 4
        return text, n_in, len(text) // 4
