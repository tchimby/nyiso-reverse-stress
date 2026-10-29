"""Book-size selection rule (plan section 3: sizes are a starting calibration, re-set so the target loss is a meaningful
tail event at NYISO price scale). The rule is stated in the comment block of revstress/config.py and was written before
the size scan was run; this module is that rule as code, so the scan script, the tests and the report use one definition.

A candidate is a size vector (MW per position). Its statistics come from the conditional-Gaussian arm run at several rng
seeds (the three seasons of a seed pooled) and from the historical sizing check:
  min_breaches  the minimum over seeds of the number of distinct breaches                        (a) >= 5
  share         mean over seeds of the mean, over the 5 distinct breaches with the largest loss,
                of (largest single-position loss) / (net scenario loss)                           (b) <= 0.60
  n_channels, n_seasons   distinct largest-loss channels / seasons among all distinct breaches    (c) >= 2 each
  worst_30d_ratio  worst historical rolling-30d loss over the fit window / target                (d) in [0.5, 1.0]
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from .. import config
from . import metrics

MIN_BREACHES_PER_SEED = 5
MAX_LARGEST_POSITION_SHARE = 0.60
MIN_CHANNELS = 2
MIN_SEASONS = 2
WORST_30D_RANGE = (0.5, 1.0)
TOP_N_FOR_SHARE = 5


def largest_position_share(rec: Mapping) -> float:
    """Largest single-position loss (USD, positive) divided by the net scenario loss; NaN if no position loses.

    Can exceed 1: a position can lose more than the whole book when another position (e.g. the congestion hedge) gains.
    """
    by = (rec.get("engine") or {}).get("pnl_by_position") or {}
    loss = rec.get("loss_usd")
    if not by or not loss or loss <= 0:
        return float("nan")
    worst = max(-v for v in by.values())
    return float(worst / loss) if worst > 0 else float("nan")


def candidate_stats(
    records_by_seed: Mapping[int, Sequence[Mapping]],
    worst_30d_loss_usd: float,
    *,
    target_usd: float = config.LOSS_TARGET_USD,
    tau: float = config.DISTINCT_TAU_Z,
) -> dict:
    """Statistics of one candidate book from per-seed pooled conditional-Gaussian records (see module docstring)."""
    counts, shares, chans, seasons = [], [], set(), set()
    for recs in records_by_seed.values():
        br = metrics.distinct_breaches(recs, target_usd, tau)
        counts.append(len(br))
        top = sorted(br, key=lambda r: -r["loss_usd"])[:TOP_N_FOR_SHARE]
        vals = [largest_position_share(r) for r in top]
        vals = [v for v in vals if np.isfinite(v)]
        if vals:
            shares.append(float(np.mean(vals)))
        for r in br:
            chans.add(metrics.dominant_channel(r))
            seasons.add(r.get("season"))
    chans.discard(None)
    seasons.discard(None)
    return {
        "breaches_per_seed": counts,
        "min_breaches": int(min(counts)) if counts else 0,
        "share": float(np.mean(shares)) if shares else float("nan"),
        "n_channels": len(chans),
        "channels": sorted(chans),
        "n_seasons": len(seasons),
        "seasons": sorted(seasons),
        "worst_30d_loss_usd": float(worst_30d_loss_usd),
        "worst_30d_ratio": float(worst_30d_loss_usd) / target_usd,
    }


def failed_conditions(st: Mapping, relax: Sequence[str] = ()) -> list[str]:
    """Names of the conditions 'a', 'b', 'c', 'd' the statistics fail; conditions listed in `relax` are not checked."""
    failed = []
    if "a" not in relax and not st["min_breaches"] >= MIN_BREACHES_PER_SEED:
        failed.append("a")
    if "b" not in relax and not (st["share"] <= MAX_LARGEST_POSITION_SHARE):  # NaN fails
        failed.append("b")
    if "c" not in relax and not (st["n_channels"] >= MIN_CHANNELS and st["n_seasons"] >= MIN_SEASONS):
        failed.append("c")
    if "d" not in relax and not (WORST_30D_RANGE[0] <= st["worst_30d_ratio"] <= WORST_30D_RANGE[1]):
        failed.append("d")
    return failed


def is_admissible(st: Mapping, relax: Sequence[str] = ()) -> bool:
    """True if the candidate passes every condition not relaxed."""
    return not failed_conditions(st, relax)


def _gross_mw(sizes: Mapping[str, float]) -> float:
    return float(sum(sizes.values()))


def select_candidate(candidates: Sequence[Mapping]) -> tuple[int | None, tuple[str, ...]]:
    """Apply the pre-stated rule. candidates[i] = {'sizes': {...}, 'stats': candidate_stats(...)}.

    Among the admissible candidates take the highest minimum-over-seeds breach count; ties go to the lower largest-position
    share, then the smaller gross MW, then the first in the list. If none is admissible, condition (c) is relaxed first,
    then (b) as well, in that order. Returns (index or None, tuple of relaxed condition names).
    """
    for relax in ((), ("c",), ("c", "b")):
        ok = [i for i, c in enumerate(candidates) if is_admissible(c["stats"], relax)]
        if ok:
            def key(i: int) -> tuple:
                st = candidates[i]["stats"]
                share = st["share"] if np.isfinite(st["share"]) else np.inf
                return (-st["min_breaches"], share, _gross_mw(candidates[i]["sizes"]), i)

            return min(ok, key=key), relax
    return None, ("c", "b", "no_candidate")


# ---------------------------------------------------------------- multi-channel rule v2 (config.py, MULTI-CHANNEL BOOK RULE v2)
MIN_BREACHES_PER_CHANNEL = 3
MIN_BREACHES_PER_SEASON = 3
MAX_CHANNEL_SHARE = 0.75


def breach_mix(records_by_seed: Mapping[int, Sequence[Mapping]], *, target_usd: float = config.LOSS_TARGET_USD,
               tau: float = config.DISTINCT_TAU_Z) -> dict:
    """Pooled over seeds: distinct-breach counts by dominant channel and by season, and the largest channel share."""
    ch: dict[str, int] = {}
    se: dict[str, int] = {}
    for recs in records_by_seed.values():
        for r in metrics.distinct_breaches(recs, target_usd, tau):
            c, s = metrics.dominant_channel(r), r.get("season")
            if c is not None:
                ch[c] = ch.get(c, 0) + 1
            if s is not None:
                se[s] = se.get(s, 0) + 1
    tot = sum(ch.values())
    return {"channel_counts": ch, "season_counts": se, "max_channel_share": (max(ch.values()) / tot) if tot else float("nan")}


def failed_conditions_v2(st: Mapping, mix: Mapping) -> list[str]:
    """Names of the v2 conditions 'a', 'b', 'c2', 'd' that fail (no relaxation). NaN shares fail."""
    failed = []
    if not st["min_breaches"] >= MIN_BREACHES_PER_SEED:
        failed.append("a")
    if not (st["share"] <= MAX_LARGEST_POSITION_SHARE):
        failed.append("b")
    n_ch = sum(1 for v in mix["channel_counts"].values() if v >= MIN_BREACHES_PER_CHANNEL)
    n_se = sum(1 for v in mix["season_counts"].values() if v >= MIN_BREACHES_PER_SEASON)
    if not (n_ch >= MIN_CHANNELS and n_se >= MIN_SEASONS and mix["max_channel_share"] <= MAX_CHANNEL_SHARE):
        failed.append("c2")
    if not (WORST_30D_RANGE[0] <= st["worst_30d_ratio"] <= WORST_30D_RANGE[1]):
        failed.append("d")
    return failed


def select_candidate_v2(candidates: Sequence[Mapping]) -> tuple[int | None, list[str]]:
    """candidates[i] = {'sizes', 'stats', 'mix'}. Returns (index, failed conditions of that index).

    Admissible (no failed condition) candidates: highest min breaches, then lower share, then smaller gross MW, then first.
    If none is admissible: the candidate with the fewest failed conditions (ties: more channels with >= 3 breaches, then
    higher min breaches, then lower gross MW); the caller must report the failure and compare with the current book.
    """
    if not candidates:
        return None, ["no_candidate"]
    fails = [failed_conditions_v2(c["stats"], c["mix"]) for c in candidates]

    def n_ch(i: int) -> int:
        return sum(1 for v in candidates[i]["mix"]["channel_counts"].values() if v >= MIN_BREACHES_PER_CHANNEL)

    def share(i: int) -> float:
        v = candidates[i]["stats"]["share"]
        return v if np.isfinite(v) else np.inf

    ok = [i for i, f in enumerate(fails) if not f]
    if ok:
        i = min(ok, key=lambda i: (-candidates[i]["stats"]["min_breaches"], share(i), _gross_mw(candidates[i]["sizes"]), i))
    else:
        i = min(range(len(candidates)), key=lambda i: (len(fails[i]), -n_ch(i), -candidates[i]["stats"]["min_breaches"],
                                                       _gross_mw(candidates[i]["sizes"]), i))
    return i, fails[i]
