"""Export run outputs to compact JSON for a front end (static, no server): ui/data/*.json.

Usage (from the repo root): python -E -P scripts/export_ui_data.py [--out ui/data]
Reads only files under outputs/ and data/processed/ (aggregates); writes runs.json (arms tables per run), scenarios.json (ranked
scenarios with narrative, shock vector, P&L by position and channel, plausibility, coherence grade), factors.json (daily-model
walk-forward table, factor correlations by season), ablations.json (anchoring, coherence agreement) and meta.json (labels, caveats).
No network, no API key.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

RUNS = {
    "live_daily_sonnet": {"label": "Sonnet 5.5, daily-model engine (final)", "judge": "coherence_opus_daily_sonnet"},
    "live_full_sonnet": {"label": "Sonnet 5.5, earlier engine", "judge": "coherence_llm_sonnet"},
    "live_full": {"label": "Haiku 5.5, earlier engine", "judge": "coherence_opus_haiku"},
}


def rows(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []


def num(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def load_mrr():
    spec = importlib.util.spec_from_file_location("mrr", ROOT / "scripts" / "make_ranked_report.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_table(d: Path) -> list[dict]:
    out = []
    for r in rows(d / "comparison_table.csv"):
        out.append({"arm": r["arm"], "breaches_mean": num(r["n_breaches_mean"]), "breaches_sd": num(r["n_breaches_sd"]),
                    "median_d2": num(r["median_d2_mean"]), "median_q": num(r["median_q_mean"]),
                    "driver_coverage": num(r["driver_coverage_mean"]), "channel_coverage": num(r["channel_coverage_mean"]),
                    "engine_calls": num(r["engine_calls"])})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "ui" / "data")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    mrr = load_mrr()
    runs, scenarios = {}, []
    for rid, meta in RUNS.items():
        d = OUT / rid
        if not d.exists():
            continue
        coh = {r["scenario"]: r for r in rows(OUT / meta["judge"] / "coherence_llm.csv")}
        logs = sorted(d.glob("audit_log*.jsonl"))
        recs = mrr.load_records(logs)
        ok = [r for r in recs if mrr.exclusion_reason(r, 5e6) is None]
        ok.sort(key=lambda r: (r["engine_output"]["d2"], -r["loss_usd"]))
        runs[rid] = {"label": meta["label"], "arms": run_table(d), "n_scenarios": len(recs), "n_ranked": len(ok)}
        for rank, r in enumerate(ok, 1):
            e, s = r["engine_output"], r["scenario"]
            g = coh.get(f"{r['_log']}:{r['scenario_id']}", {})
            scenarios.append({
                "run": rid, "rank": rank, "id": r["scenario_id"], "driver_class": s["driver_class"], "season": s["season"],
                "narrative": s["narrative"], "confidence": s.get("confidence"),
                "shocks": {k: v for k, v in s["shocks"].items() if v not in (0, 0.0, 1.0) or k == "duration_days"},
                "loss_usd": r["loss_usd"], "stated_loss_usd": r.get("stated_loss_usd"),
                "d2": e["d2"], "q": e["q"], "severity": e["severity"], "nearest_date": e.get("nearest_date"),
                "pnl_by_position": e["pnl_by_position"], "pnl_by_channel": e["pnl_by_channel"],
                "analogue": s.get("analogue") or {},
                "coherence": {k: (int(g[k]) if g.get(k) not in (None, "") else None) for k in
                              ("causal_chain", "shocks_explained", "duration_matches", "analogue_correct_relevant", "no_contradiction")} if g else None,
                "coherence_note": g.get("note") if g else None})
    anchoring = {}
    for name, d in (("sonnet", OUT / "live_anchoring_sonnet"), ("haiku", OUT / "live_anchoring")):
        anchoring[name] = rows(d / "ablation_anchoring.csv")
    factors = {"walk_forward": rows(OUT / "daily_model" / "walk_forward.csv")}
    meta = {
        "title": "NYISO reverse stress testing agent",
        "objective": "Start from a loss of at least $5M (25% of $20M) and find the most plausible scenarios that cause it; Claude proposes typed shock vectors, an engine computes P&L, plausibility is D^2 and rank q against 2019-2025.",
        "caveats": ["q is a rank against about 250 windows, not a probability", "single-channel book: every ranked scenario loses mostly on zone_volume",
                    "sizing rule v1 is not met on the daily-model engine (4 of 5 breaches)", "coherence grades come from an LLM judge, human grading pending",
                    "one seed per run; Claude arm uses fewer engine calls than baselines"],
        "data": "NYISO public data, aggregated daily; raw files are not distributed",
    }
    for name, obj in (("runs", runs), ("scenarios", scenarios), ("factors", factors), ("ablations", {"anchoring": anchoring}), ("meta", meta)):
        (a.out / f"{name}.json").write_text(json.dumps(obj, indent=1, default=float), encoding="utf-8")
    print(f"wrote {len(runs)} runs, {len(scenarios)} scenarios to {a.out}")


if __name__ == "__main__":
    main()
