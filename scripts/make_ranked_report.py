"""Assemble the course deliverable (handout example 6): a RANKED set of scenarios with narrative, shock vector,
P&L decomposition (position and channel), plausibility and the audit trail, from one or more audit logs.

Usage (from pjm_revstress): python -E -P scripts/make_ranked_report.py LOG [LOG ...] [--out FILE] [--target-usd 5e6] [--top 10]

Ranking = the reverse-stress question "most plausible scenarios that lose at least the target":
  eligible = engine ran, loss >= target, no hard-rule failure, severity not 'implausible', not a fabricated analogue;
  order    = D^2 ascending (most plausible first), ties by larger loss.
Everything else is listed in an exclusion table with the reason. q is a rank against about 250 non-overlapping
10-day windows, not a probability. Reads only audit logs (no network, no API key, no raw data).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

NEUTRAL = {"gas_hh_pct": 0, "ny_gas_basis_usd": 0, "load_peak_ratio": 1.0, "large_load_shock_mw": 0, "ref_onpeak_pct": 0,
           "pocket_minus_ref_usd": 0, "dart_pct": 0, "spike_days": 0, "spike_daily_avg_usd": 0}


def load_records(paths: list[Path]) -> list[dict]:
    recs: dict[str, dict] = {}
    for p in paths:
        for line in p.open(encoding="utf-8"):
            row = json.loads(line)
            for rec in row.get("scenarios") or []:
                rec = dict(rec, _model=row.get("model"), _client=row.get("client_kind"), _log=p.parent.name)
                recs[f"{p.parent.name}:{rec.get('scenario_id')}"] = rec
    return list(recs.values())


def exclusion_reason(r: dict, target: float) -> str | None:
    if r.get("engine_error") or not r.get("engine_output"):
        failed = [v["rule"] for v in r.get("hard_verdicts", []) if not v.get("passed")]
        return "rejected before the engine: " + (", ".join(failed) or str(r.get("engine_error") or "no engine output"))
    e = r["engine_output"]
    if r.get("fabricated_analogue"):
        return "fabricated analogue"
    if e.get("hard_rule_failures"):
        return "hard rule failed: " + ", ".join(e["hard_rule_failures"])
    if r["loss_usd"] < target:
        return f"loss {r['loss_usd'] / 1e6:.2f}M below target"
    if e.get("severity") == "implausible":
        return "implausible: marginal beyond " + ", ".join(e.get("marginals_exceeded") or ["limit"])
    if e.get("severity") == "ordinary":
        return f"ordinary world (q={e['q']:.3f} >= 0.05), not a tail event"
    return None


def fmt_pnl(d: dict) -> str:
    return " | ".join(f"{k} {v / 1e6:+.2f}M" for k, v in d.items())


def section(rank: int, r: dict) -> str:
    e, s = r["engine_output"], r["scenario"]
    shocks = {k: v for k, v in s["shocks"].items() if v not in (0, 0.0, 1.0) or k == "duration_days"}
    an = s.get("analogue") or {}
    stated = r.get("stated_loss_usd")
    return (
        f"### #{rank} {r['scenario_id']} ({s['driver_class']}, {s['season']}, {s['shocks'].get('duration_days')} days)\n\n"
        f"**Narrative.** {s['narrative']}\n\n"
        f"**Shock vector (non-neutral).** `{json.dumps(shocks)}`\n\n"
        f"**Loss** {r['loss_usd'] / 1e6:.2f}M (Claude stated {stated / 1e6:.2f}M)" if stated else
        f"### #{rank} {r['scenario_id']}\n\n**Narrative.** {s['narrative']}\n\n**Loss** {r['loss_usd'] / 1e6:.2f}M"
    ) + (
        f"  \n**Plausibility.** D2 {e['d2']:.1f}, rank q {e['q']:.3f}, class {e['severity']}, nearest past date {e.get('nearest_date')}, "
        f"marginal percentiles {json.dumps({k: round(v, 2) for k, v in e['marginals'].items()})}  \n"
        f"**P&L by position.** {fmt_pnl(e['pnl_by_position'])}  \n"
        f"**P&L by channel.** {fmt_pnl(e['pnl_by_channel'])}  \n"
        f"**Analogue.** {an.get('event') or 'none'} {an.get('dates') or ''}; **confidence** {s.get('confidence')}; "
        f"**soft penalty** {r.get('penalty')}\n"
    )


def build(recs: list[dict], target: float, top: int) -> str:
    ok, out = [], []
    for r in recs:
        why = exclusion_reason(r, target)
        (out.append((r, why)) if why else ok.append(r))
    ok.sort(key=lambda r: (r["engine_output"]["d2"], -r["loss_usd"]))
    models = sorted({str(r["_model"]) for r in recs})
    clients = sorted({str(r["_client"]) for r in recs})
    channels: dict[str, int] = {}
    for r in ok:
        ch = min(r["engine_output"]["pnl_by_channel"].items(), key=lambda kv: kv[1])[0]
        channels[ch] = channels.get(ch, 0) + 1
    lines = [
        "# Ranked reverse-stress scenarios (NYISO book)",
        "",
        f"Source logs: {', '.join(sorted({r['_log'] for r in recs}))}. Models: {', '.join(models)}. Client kinds: {', '.join(clients)}.  ",
        f"Target loss {target / 1e6:.1f}M. Scenarios read: {len(recs)}; ranked (eligible): {len(ok)}; excluded: {len(out)}.  ",
        "q is a rank against about 250 non-overlapping 10-day windows of 2019-2025, not a probability; fit window 2019-2025; "
        "daily averaging understates hourly spikes. A client kind other than the live API means scripted output, not Claude results.  ",
        f"Largest-loss channel across ranked scenarios: {json.dumps(channels)} "
        "(one channel for all of them means the book, not the search, limits diversity).",
        "",
        "Coherence grading by a human: [PENDING]. Scenarios are drafts for a risk manager to accept or hedge, not forecasts.",
        "",
        "## Ranked scenarios (most plausible first)",
        "",
    ]
    lines += [section(i, r) for i, r in enumerate(ok[:top], 1)] or ["_No eligible scenario in these logs._\n"]
    lines += ["## Excluded scenarios and why", "", "| scenario | loss (M) | reason |", "|---|---|---|"]
    for r, why in sorted(out, key=lambda t: t[0]["scenario_id"]):
        loss = f"{r['loss_usd'] / 1e6:.2f}" if r.get("loss_usd") is not None else "n/a"
        lines.append(f"| {r['scenario_id']} | {loss} | {why} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("outputs/RANKED_SCENARIOS.md"))
    ap.add_argument("--target-usd", type=float, default=5e6)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    text = build(load_records(a.logs), a.target_usd, a.top)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(f"wrote {a.out} ({len(text)} chars)")


if __name__ == "__main__":
    main()
