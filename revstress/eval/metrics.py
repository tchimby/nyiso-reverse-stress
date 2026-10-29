"""Evaluation metrics and the arm comparison table (plan section 8D).

Works on scenario records (see baselines.common for the schema; the agent loop uses the same fields).
Factor-space position of a scenario = engine['z'] (standardized core factors, see revstress.factorspace);
records without it are not counted as breaches. Distances are Euclidean in z units. tau is a PLACEHOLDER
(config.DISTINCT_TAU_Z = 1.0 z-unit) until chosen on real data, and is the same threshold the agent loop uses.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .. import config
from ..factorspace import z_vector

FACTORS = config.GAUSSIAN_CORE_FACTORS
DEFAULT_TAU = config.DISTINCT_TAU_Z
RESCALING_COSINE = 0.95

METRIC_COLUMNS: tuple[str, ...] = (
    "n_breaches",
    "median_q",
    "median_d2",
    "driver_coverage",
    "channel_coverage",
    "rule_pass_share",
    "median_replay_distance",
    "rescaling_share",
    "coherence",
)


def factor_vector(rec: Mapping) -> np.ndarray | None:
    """Factor-space z-vector of a record (None if the engine result or its 'z' is missing)."""
    return z_vector(rec.get("engine"))


def engine_implausible(eng: Mapping | None) -> bool:
    """True if the engine output is severity 'implausible' or lists hard-rule failures (counts as a failed hard rule)."""
    return bool(eng) and (eng.get("severity") == "implausible" or bool(eng.get("hard_rule_failures")))


def is_breaching(rec: Mapping, target_usd: float = config.LOSS_TARGET_USD, q_max: float = config.Q_ADVERSE_MAX) -> bool:
    """loss >= target, q < q_max, all hard rules passed and engine severity not 'implausible' (distinctness is separate)."""
    eng = rec.get("engine")
    if not eng or engine_implausible(eng):
        return False
    return bool(-eng["pnl_total"] >= target_usd and eng["q"] < q_max and not rec.get("rules_failed"))


def distinct_breaches(
    records: Sequence[Mapping],
    target_usd: float = config.LOSS_TARGET_USD,
    tau: float = DEFAULT_TAU,
    q_max: float = config.Q_ADVERSE_MAX,
) -> list[Mapping]:
    """Greedy, in record order: keep breaching scenarios whose factor distance to every kept one exceeds tau."""
    kept: list[Mapping] = []
    vecs: list[np.ndarray] = []
    for r in records:
        if not is_breaching(r, target_usd, q_max):
            continue
        v = factor_vector(r)
        if v is None:
            continue
        if all(np.linalg.norm(v - w) > tau for w in vecs):
            kept.append(r)
            vecs.append(v)
    return kept


def primary_metric(records: Sequence[Mapping], target_usd: float = config.LOSS_TARGET_USD, tau: float = DEFAULT_TAU) -> int:
    """Number of distinct breaching scenarios (loss >= target, q < 5%, pairwise distance > tau, rules passed)."""
    return len(distinct_breaches(records, target_usd, tau))


def dominant_channel(rec: Mapping) -> str | None:
    """Channel with the largest loss (most negative P&L) in the record; None if no channel loses."""
    by = (rec.get("engine") or {}).get("pnl_by_channel") or {}
    if not by:
        return None
    ch = min(by, key=lambda k: by[k])
    return ch if by[ch] < 0 else None


def novelty(breaches: Sequence[Mapping], replay_vectors: Mapping[str, np.ndarray]) -> tuple[float, float]:
    """(median distance to nearest replay event in z units, share that are rescalings of a replay event).

    A breach is a rescaling if its z-vector has cosine similarity >= 0.95 with some replay vector (same
    direction, different size); otherwise it is a new combination. NaN if there are no breaches or events.
    """
    if not breaches or not replay_vectors:
        return float("nan"), float("nan")
    dists, resc = [], []
    for r in breaches:
        v = factor_vector(r)
        if v is None:
            continue
        dists.append(min(np.linalg.norm(v - np.asarray(w)) for w in replay_vectors.values()))
        cos = [
            float(v @ np.asarray(w) / (np.linalg.norm(v) * np.linalg.norm(w)))
            for w in replay_vectors.values()
            if np.linalg.norm(v) > 0 and np.linalg.norm(w) > 0
        ]
        resc.append(bool(cos) and max(cos) >= RESCALING_COSINE)
    if not dists:
        return float("nan"), float("nan")
    return float(np.median(dists)), float(np.mean(resc))


def run_metrics(
    records: Sequence[Mapping],
    *,
    target_usd: float = config.LOSS_TARGET_USD,
    tau: float = DEFAULT_TAU,
    replay_vectors: Mapping[str, np.ndarray] | None = None,
    coherence: float | None = None,
) -> dict[str, float]:
    """Primary and secondary metrics of one run (one arm, one repeat). Keys follow METRIC_COLUMNS.

    driver_coverage = distinct driver classes among distinct breaches / 7; channel_coverage = distinct
    dominant loss channels among distinct breaches / 6; rule_pass_share over all records; median_q and
    median_d2 over distinct breaches (NaN if none); coherence is passed in (mean rubric score).
    """
    br = distinct_breaches(records, target_usd, tau)
    nan = float("nan")
    med_dist, resc = novelty(br, replay_vectors or {})
    return {
        "n_breaches": float(len(br)),
        "median_q": float(np.median([r["engine"]["q"] for r in br])) if br else nan,
        "median_d2": float(np.median([r["engine"]["d2"] for r in br])) if br else nan,
        "driver_coverage": len({r["driver_class"] for r in br}) / len(config.DRIVER_CLASSES),
        "channel_coverage": len({c for c in map(dominant_channel, br) if c}) / len(config.CHANNELS),
        "rule_pass_share": float(np.mean([bool(r.get("rules_passed", not r.get("rules_failed"))) for r in records])) if records else nan,
        "median_replay_distance": med_dist,
        "rescaling_share": resc,
        "coherence": nan if coherence is None else float(coherence),
    }


def compare_arms(
    runs: Mapping[str, Iterable[Sequence[Mapping]]],
    *,
    target_usd: float = config.LOSS_TARGET_USD,
    tau: float = DEFAULT_TAU,
    replay_vectors: Mapping[str, np.ndarray] | None = None,
    coherence: Mapping[str, Sequence[float]] | None = None,
) -> pd.DataFrame:
    """Comparison table across arms: runs[arm] is a list of repeats, each a list of records.

    Returns one row per arm with columns '<metric>_mean', '<metric>_sd' (over repeats, NaN-skipping) and
    n_repeats. coherence[arm] optionally gives one mean rubric score per repeat.
    """
    rows = []
    for arm, repeats in runs.items():
        repeats = list(repeats)
        coh = (coherence or {}).get(arm)
        per = pd.DataFrame(
            [
                run_metrics(
                    rec,
                    target_usd=target_usd,
                    tau=tau,
                    replay_vectors=replay_vectors,
                    coherence=None if coh is None else coh[i],
                )
                for i, rec in enumerate(repeats)
            ],
            columns=list(METRIC_COLUMNS),
        )
        row: dict[str, float | str | int] = {"arm": arm, "n_repeats": len(repeats)}
        for m in METRIC_COLUMNS:
            row[f"{m}_mean"] = float(per[m].mean()) if per[m].notna().any() else float("nan")
            row[f"{m}_sd"] = float(per[m].std(ddof=1)) if per[m].notna().sum() > 1 else float("nan")
        rows.append(row)
    return pd.DataFrame(rows).set_index("arm")


# ------------------------------------------------------------------ loop-log diagnostics (plan sections 5 and 8)

ANCHOR_TOL = 0.20
DISPERSION_METRICS: tuple[str, ...] = ("n_breaches", "median_q", "driver_coverage", "channel_coverage")


def records_from_loop(scenario_records: Iterable[Mapping]) -> list[dict]:
    """Agent-loop scenario dicts (LoopResult.scenario_records / audit-log 'scenarios') to the baseline record schema.

    engine = engine_output, rules_failed = names of failed hard rules ('schema' for schema errors, 'engine_error' for
    an engine failure), rules_passed = accepted. Lets run_metrics / compare_arms score Claude runs like the baselines.
    """
    out = []
    for s in scenario_records:
        failed = [v["rule"] for v in s.get("hard_verdicts", []) if not v.get("passed", True)]
        if s.get("schema_errors"):
            failed.append("schema")
        if s.get("engine_error"):
            failed.append("engine_error")
        if engine_implausible(s.get("engine_output")):
            failed.append("implausible_severity")
        sc = s.get("scenario")
        out.append(
            {
                "scenario_id": s.get("scenario_id"),
                "driver_class": s.get("driver_class"),
                "season": sc.get("season") if isinstance(sc, Mapping) else None,
                "engine": s.get("engine_output"),
                "loss_usd": s.get("loss_usd"),
                "rules_failed": sorted(set(failed)),
                "rules_passed": bool(s.get("accepted")),
                "breach": bool(s.get("breach")),
            }
        )
    return out


def _stated(rec: Mapping) -> float | None:
    v = rec.get("stated_loss_usd")
    if v is None and isinstance(rec.get("scenario"), Mapping):
        v = rec["scenario"].get("stated_loss_usd")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v):
        return None
    return float(v)


def _eng_loss(rec: Mapping) -> float | None:
    v = rec.get("loss_usd")
    if v is None and rec.get("engine"):
        v = -rec["engine"]["pnl_total"]
    if v is None or not np.isfinite(v):
        return None
    return float(v)


def stated_vs_implied(scenario_records: Iterable[Mapping], group_key: str = "prompt_version") -> pd.DataFrame:
    """Error between Claude's stated_loss_usd and the engine loss (USD), one row per group (default prompt version).

    Uses scenarios with both a numeric stated loss and an engine loss. abs_err = |stated - engine|;
    rel_err = (stated - engine) / |engine| (signed, so the median shows bias; NaN where engine loss is 0).
    Columns: n, n_stated, n_scored, abs_err_mean/median/p90 (USD), rel_abs_median/rel_abs_p90 (|rel_err|),
    rel_err_median (signed), share_within_20pct (|rel_err| <= 0.20). Scored = stated and engine loss both present.
    """
    groups: dict[str, list[tuple[float, float]]] = {}
    counts: dict[str, list[int]] = {}
    for r in scenario_records:
        g = str(r.get(group_key, "all"))
        c = counts.setdefault(g, [0, 0])
        c[0] += 1
        st, loss = _stated(r), _eng_loss(r)
        c[1] += int(st is not None)
        if st is not None and loss is not None:
            groups.setdefault(g, []).append((st, loss))
    rows = []
    nan = float("nan")
    for g, (n, n_st) in sorted(counts.items()):
        pairs = np.array(groups.get(g, []), dtype=float).reshape(-1, 2)
        st, loss = pairs[:, 0], pairs[:, 1]
        ae = np.abs(st - loss)
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.where(loss != 0, (st - loss) / np.abs(loss), np.nan)
        ok = ~np.isnan(rel)
        rows.append(
            {
                group_key: g,
                "n": n,
                "n_stated": n_st,
                "n_scored": len(pairs),
                "abs_err_mean": float(ae.mean()) if len(ae) else nan,
                "abs_err_median": float(np.median(ae)) if len(ae) else nan,
                "abs_err_p90": float(np.quantile(ae, 0.9)) if len(ae) else nan,
                "rel_abs_median": float(np.median(np.abs(rel[ok]))) if ok.any() else nan,
                "rel_abs_p90": float(np.quantile(np.abs(rel[ok]), 0.9)) if ok.any() else nan,
                "rel_err_median": float(np.median(rel[ok])) if ok.any() else nan,
                "share_within_20pct": float(np.mean(np.abs(rel[ok]) <= ANCHOR_TOL)) if ok.any() else nan,
            }
        )
    cols = [group_key, "n", "n_stated", "n_scored", "abs_err_mean", "abs_err_median", "abs_err_p90",
            "rel_abs_median", "rel_abs_p90", "rel_err_median", "share_within_20pct"]
    return pd.DataFrame(rows, columns=cols).set_index(group_key)


def target_anchoring_report(
    arms: Mapping[str, Iterable[Mapping]],
    target_usd: float = config.LOSS_TARGET_USD,
    tol: float = ANCHOR_TOL,
) -> pd.DataFrame:
    """Severity-anchoring ablation table: per arm (target shown / not shown) the engine-loss distribution.

    arms[arm] = scenario dicts of the agent loop (e.g. LoopResult.scenario_records). Scenarios without an engine
    loss (rejected) count in n_scenarios only. Columns: n_scenarios, n_engine, loss_mean/median/p10/p90 (USD),
    share_within_tol (|loss - target| <= tol*target, share of n_engine), share_above_target, n_breaches.
    """
    rows = []
    nan = float("nan")
    for arm, recs in arms.items():
        recs = list(recs)
        loss = np.array([x for x in map(_eng_loss, recs) if x is not None], dtype=float)
        rows.append(
            {
                "arm": arm,
                "n_scenarios": len(recs),
                "n_engine": len(loss),
                "loss_mean": float(loss.mean()) if len(loss) else nan,
                "loss_median": float(np.median(loss)) if len(loss) else nan,
                "loss_p10": float(np.quantile(loss, 0.1)) if len(loss) else nan,
                "loss_p90": float(np.quantile(loss, 0.9)) if len(loss) else nan,
                "share_within_tol": float(np.mean(np.abs(loss - target_usd) <= tol * target_usd)) if len(loss) else nan,
                "share_above_target": float(np.mean(loss >= target_usd)) if len(loss) else nan,
                "n_breaches": int(sum(bool(r.get("breach")) and not engine_implausible(r.get("engine_output")) for r in recs)),
            }
        )
    return pd.DataFrame(rows).set_index("arm")


def gate_rejection_stats(scenario_records: Iterable[Mapping]) -> dict:
    """Gate statistics of a run: per-rule counts and rates of hard-rule rejections and soft penalties.

    Input: agent-loop scenario dicts (hard_verdicts, soft_verdicts, schema_errors, engine_error, accepted).
    Returns {'n_scenarios', 'n_accepted', 'n_rejected', 'rejection_rate',
    'hard': {rule: {'count', 'rate'}} (rate over all scenarios; a scenario can fail several rules; 'schema' and
    'engine_error' are listed like rules), 'n_soft_scored' (accepted scenarios), 'soft': {rule: {'count', 'rate',
    'penalty_sum'}} (rate over accepted), 'mean_penalty' (per accepted scenario)}.
    """
    recs = list(scenario_records)
    n = len(recs)
    hard: dict[str, int] = {}
    soft: dict[str, list[float]] = {}
    n_acc = 0
    total_pen = 0.0
    for r in recs:
        for name in {v["rule"] for v in r.get("hard_verdicts", []) if not v.get("passed", True)}:
            hard[name] = hard.get(name, 0) + 1
        if r.get("schema_errors"):
            hard["schema"] = hard.get("schema", 0) + 1
        if r.get("engine_error"):
            hard["engine_error"] = hard.get("engine_error", 0) + 1
        if r.get("accepted"):
            n_acc += 1
            total_pen += float(r.get("penalty") or 0.0)
            for v in r.get("soft_verdicts", []):
                if not v.get("passed", True):
                    c = soft.setdefault(v["rule"], [0, 0.0])
                    c[0] += 1
                    c[1] += float(v.get("penalty") or 0.0)
    nan = float("nan")
    return {
        "n_scenarios": n,
        "n_accepted": n_acc,
        "n_rejected": n - n_acc,
        "rejection_rate": (n - n_acc) / n if n else nan,
        "hard": {k: {"count": c, "rate": c / n} for k, c in sorted(hard.items())},
        "n_soft_scored": n_acc,
        "soft": {k: {"count": int(c), "rate": c / n_acc, "penalty_sum": p} for k, (c, p) in sorted(soft.items())},
        "mean_penalty": total_pen / n_acc if n_acc else nan,
    }


def repeat_dispersion(
    repeats: Sequence[Sequence[Mapping]],
    *,
    target_usd: float = config.LOSS_TARGET_USD,
    tau: float = DEFAULT_TAU,
) -> pd.DataFrame:
    """Dispersion across repeats of one arm: repeats[i] is the list of records of repeat i (baseline schema).

    One row per metric in DISPERSION_METRICS (distinct breach count, median q, driver and channel coverage), columns
    n (repeats with a value), mean, sd (ddof=1, NaN if n < 2), min, max. A repeat with no breach has median_q NaN
    and is skipped for that row.
    """
    per = pd.DataFrame(
        [run_metrics(rec, target_usd=target_usd, tau=tau) for rec in repeats], columns=list(METRIC_COLUMNS)
    )
    rows = []
    for m in DISPERSION_METRICS:
        v = per[m].dropna()
        rows.append(
            {
                "metric": m,
                "n": len(v),
                "mean": float(v.mean()) if len(v) else float("nan"),
                "sd": float(v.std(ddof=1)) if len(v) > 1 else float("nan"),
                "min": float(v.min()) if len(v) else float("nan"),
                "max": float(v.max()) if len(v) else float("nan"),
            }
        )
    return pd.DataFrame(rows).set_index("metric")


# ------------------------------------------------------------------ sensitivity of the breach count to window length and tau

SENS_WINDOW_DAYS: tuple[int, ...] = (5, 10, 14)
SENS_TAUS: tuple[float, ...] = (0.5, 1.0, 2.0)
SENSITIVITY_COLUMNS: tuple[str, ...] = (
    "arm", "window_days", "tau", "n_repeats", "n_breaches_mean", "n_breaches_sd", "n_breaches_min", "n_breaches_max",
    "repeats_with_breach", "weakest_q_mean", "weakest_q_max",
)


def requantile(records: Sequence[Mapping], window_d2: Sequence[float]) -> list[dict]:
    """Copies of the records whose engine rank q is recomputed against another set of historical windows.

    q = share of the windows with D^2 >= the scenario's engine D^2 (the same definition as risk.score_scenario). The
    engine output is otherwise unchanged; records without an engine result are returned as they are.
    """
    w = np.asarray(window_d2, dtype=float)
    out = []
    for r in records:
        eng = r.get("engine")
        if not eng or "d2" not in eng or not len(w):
            out.append(dict(r))
            continue
        out.append({**r, "engine": {**eng, "q": float(np.mean(w >= float(eng["d2"])))}})
    return out


def sensitivity_table(
    runs: Mapping[str, Iterable[Sequence[Mapping]]],
    window_d2_by_days: Mapping[int, Sequence[float]],
    *,
    target_usd: float = config.LOSS_TARGET_USD,
    taus: Sequence[float] = SENS_TAUS,
    q_max: float = config.Q_ADVERSE_MAX,
) -> pd.DataFrame:
    """Breach count and weakest-breach q under other plausibility window lengths and distinctness thresholds tau.

    runs[arm] is a list of repeats (lists of baseline-schema records). window_d2_by_days[n] holds the max-daily-D^2 of the
    historical non-overlapping n-day windows (eval.diagnostics.window_d2_by_length); the engine q of every record is
    recomputed against them (requantile), then a breach is loss >= target, q < q_max, rules passed and severity not
    implausible, counted greedily with distinctness threshold tau in z units (distinct_breaches). One row per
    (arm, window length, tau): over repeats the mean / sd / min / max of the distinct-breach count, the number of repeats
    with at least one breach, and the WEAKEST breach q (the largest q among the distinct breaches of a repeat: the least
    extreme world that still counts) as mean over repeats with a breach and as the maximum over repeats. NaN if none.
    """
    rows = []
    for arm, repeats in runs.items():
        repeats = list(repeats)
        for n_days, w in window_d2_by_days.items():
            req = [requantile(rec, w) for rec in repeats]
            for tau in taus:
                counts, weakest = [], []
                for rec in req:
                    br = distinct_breaches(rec, target_usd, tau, q_max)
                    counts.append(len(br))
                    if br:
                        weakest.append(max(float(b["engine"]["q"]) for b in br))
                c = np.asarray(counts, dtype=float)
                rows.append(
                    {
                        "arm": arm,
                        "window_days": int(n_days),
                        "tau": float(tau),
                        "n_repeats": len(repeats),
                        "n_breaches_mean": float(c.mean()) if len(c) else float("nan"),
                        "n_breaches_sd": float(c.std(ddof=1)) if len(c) > 1 else float("nan"),
                        "n_breaches_min": float(c.min()) if len(c) else float("nan"),
                        "n_breaches_max": float(c.max()) if len(c) else float("nan"),
                        "repeats_with_breach": int((c > 0).sum()),
                        "weakest_q_mean": float(np.mean(weakest)) if weakest else float("nan"),
                        "weakest_q_max": float(np.max(weakest)) if weakest else float("nan"),
                    }
                )
    return pd.DataFrame(rows, columns=list(SENSITIVITY_COLUMNS))
