"""Blind LLM coherence grading of ranked scenarios with a DIFFERENT model than the generator (default Sonnet 5.5 vs Haiku 5.5).

Usage (from pjm_revstress): python -E -P scripts/grade_coherence_llm.py LOG [LOG ...] --i-understand-cost [--model claude-sonnet-5-5] [--target-usd 5e6]
Grades the scenarios the ranked report keeps (same eligibility). The judge sees narrative, non-neutral shocks, season, driver class,
horizon and analogue; never the arm, the loss or the D2. Rubric = plan 8B (5 items, 0/1), combined with the mechanical checks
(a mechanical 0 caps the item). This is an LLM rater, not the pre-registered human rater: report it as such.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from revstress import envfile  # noqa: E402
from revstress.agent import client as client_mod  # noqa: E402
from revstress.eval import rubric  # noqa: E402

spec = importlib.util.spec_from_file_location("mrr", ROOT / "scripts" / "make_ranked_report.py")
mrr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mrr)

SYSTEM = (
    "You are a strict risk-management reviewer grading the INTERNAL COHERENCE of stress-scenario write-ups for a NYISO power book "
    "(reference zone WEST, load pocket N.Y.C.). You do not judge likelihood or P&L. For each scenario give 0 or 1 on: "
    "causal_chain (narrative states a causal chain from driver to the price effects); shocks_explained (every non-zero shock is "
    "explained by the narrative); duration_matches (duration_days consistent with the narrative); analogue_correct_relevant "
    "(the cited analogue is relevant to the story; an empty analogue with low confidence counts as 1; you cannot verify numbers, "
    "grade relevance and internal consistency only); no_contradiction (no two channels or shocks contradict each other or the narrative). "
    'Reply with ONLY a JSON list: [{"blind_id": "...", "causal_chain": 0|1, "shocks_explained": 0|1, "duration_matches": 0|1, '
    '"analogue_correct_relevant": 0|1, "no_contradiction": 0|1, "note": "<=15 words"}], one object per scenario.'
)


def view(r: dict, bid: str) -> dict:
    s = r["scenario"]
    shocks = {k: v for k, v in s["shocks"].items() if v not in (0, 0.0, 1.0) or k == "duration_days"}
    return {"blind_id": bid, "driver_class": s["driver_class"], "season": s["season"], "narrative": s["narrative"],
            "shocks": shocks, "analogue": s.get("analogue") or {}, "confidence": s.get("confidence")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--target-usd", type=float, default=5e6)
    ap.add_argument("--batch", type=int, default=7)
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "coherence_llm")
    ap.add_argument("--env-file", default=str(ROOT.parent / ".env"))
    ap.add_argument("--i-understand-cost", action="store_true")
    a = ap.parse_args()
    if not a.i_understand_cost:
        print("REFUSED: pass --i-understand-cost", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        envfile.load_api_key(a.env_file)
    recs = [r for r in mrr.load_records(a.logs) if mrr.exclusion_reason(r, a.target_usd) is None]
    views, key = rubric.blind_order([dict(r["scenario"], scenario_id=f"{r['_log']}:{r['scenario_id']}") for r in recs], seed=0)
    by_sid = {f"{r['_log']}:{r['scenario_id']}": r for r in recs}
    a.out.mkdir(parents=True, exist_ok=True)
    cl = client_mod.ClaudeClient(model=a.model, cache_dir=a.out / "cache", max_tokens=4000, max_total_calls=len(views) // a.batch + 5)
    graded: dict[str, dict] = {}
    for i in range(0, len(views), a.batch):
        chunk = [view(by_sid[key[v["blind_id"]]], v["blind_id"]) for v in views[i:i + a.batch]]
        resp = cl.complete(SYSTEM, [{"role": "user", "content": json.dumps(chunk)}], "coherence_judge_v1")
        m = re.search(r"\[.*\]", resp.text or "", re.S)
        try:
            for g in json.loads(m.group(0)) if m else []:
                graded[g["blind_id"]] = g
        except (json.JSONDecodeError, KeyError):
            print(f"batch {i // a.batch}: unparseable reply (error={resp.error})", file=sys.stderr)
    rows = []
    for bid, sid in key.items():
        g = graded.get(bid)
        if not g:
            continue
        r = by_sid[sid]
        res = rubric.score_scenario(r["scenario"], {k: g.get(k) for k in rubric.ITEMS})
        rows.append({"scenario": sid, "judge_model": a.model, **{k: res.items[k] for k in rubric.ITEMS}, "total": res.total,
                     "mech_zero": [k for k, v in res.mechanical.items() if v == 0], "note": g.get("note", "")})
    with (a.out / "coherence_llm.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["scenario"])
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    print(f"graded {n} of {len(views)} scenarios with {a.model}; tokens {cl.totals['input_tokens']} in / {cl.totals['output_tokens']} out")
    for k in rubric.ITEMS:
        vals = [r[k] for r in rows if r[k] is not None]
        print(f"  {k}: {sum(vals)}/{len(vals)}")
    tot = [r["total"] for r in rows if r["total"] is not None]
    print(f"  mean total: {sum(tot) / len(tot):.3f}" if tot else "  no totals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
