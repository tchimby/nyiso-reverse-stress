"""Optimizer baseline (plan section 8D c): SLSQP minimising D^2 subject to loss >= target and plausibility constraints.

Version 2 (fair competitor at equal engine budget). The original version used random starts, finite-difference
gradients that cost one engine call per variable and per iteration, a 50-iteration cap and no plausibility terms, so
with the demo's per-seed budget (about 9 engine calls per start) it could not converge, and its high-loss points were mostly
implausible. Changes:

1. Warm start. The first start is the closed-form linearised most-likely point of the conditional-Gaussian arm
   (forward-difference gradient, x = mu + lam * Sigma g, damped Newton/secant correction of lam), found with this arm's
   own engine calls (about 1 + 5 + a few). It is then polished by SLSQP.
2. Cheap derivatives. The engine returns, for every evaluated point, the loss, the plausibility distance D^2 (engine
   value, from the shocked path) and the robust z of the five core factors. These seven quantities (loss, sqrt of D^2, five z) are linearised once
   from the forward differences and updated by Broyden rank-one steps after every new engine call, so an SLSQP
   iteration costs about one engine call (not one per variable).
3. Constraints inside the optimisation (all taken from the same engine call, no extra budget):
   * loss >= target (small margin);
   * tail: engine D^2 above the value that gives rank q < Q_ADVERSE_MAX against the fitted historical windows
     (argument `tail_d2`, from `pipeline.plausibility_kwargs`), so the point is a tail point, not just a lossy one;
   * marginal limits: each core factor's robust z inside the fitted season limits (`z_limits`), i.e. not implausible;
   * temperature factor T: it is derived from the load shock and is not in the z vector, so it is handled by an
     adaptive cap on the load factor l: when the engine lists 'T' among the exceeded marginals the cap moves to the midpoint between
     the largest feasible l seen and the smallest exceeding l (bisection from the safe side; symmetric below);
   * sign consistency (hard rule): a load factor classed cold_snap (l >= ln 1.05 in winter) needs gas g >= 0, imposed as a
     bound on g or as a cap on l below the cold_snap class, chosen from the warm-start point;
   * duration <= horizon (by construction) and spike days <= duration (no spike overlay in this version).
4. Random restarts. After the warm-started polish the remaining engine budget is spent on restarts from the warm point
   plus Gaussian noise (restart durations drawn uniformly from the warm duration up to the top of `duration_range`: a shorter
   shock needs a more extreme factor vector for the same loss; the loss row of the linear model is kept in warm-duration
   units and rescaled by the duration ratio), each with an equal share, until the budget is used. The total number of engine calls is the same `budget` as
   for the other arms (cache hits are free); nothing is tuned with extra budget.
5. SLSQP iteration cap raised from 50 to 200 (the budget is the binding limit).

`warm_start=False` runs the original version (random starts, analytic D^2, loss constraint only, finite differences).
D^2 in the objective is analytic from the injected FactorSpec; the plausibility terms use engine outputs. Without
`tail_d2` / `z_limits` (e.g. a stub engine) only the loss constraint and the adaptive T cap are active. The spike
overlay is used only by the legacy version.

Caveat on fairness: the budget is equal (engine calls), but this version is given the fitted risk model's tail threshold and
marginal limits (`pipeline.plausibility_kwargs`), which the conditional-Gaussian arm does not use; that is the information a
tail-aware optimizer would have, and it is why this arm finds more breaches than the plain minimum-D^2 point.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
from scipy.optimize import minimize

from .. import config
from .common import BudgetExhausted, EngineFn, Evaluator, FactorSpec, RulesFn, SpikeOverlay, default_hard_rules, factors_to_shock

LOSS_SCALE_USD = 1e6
LOAD_INDEX = 1  # position of the load factor l in FACTOR_ORDER (g, l, s, c, d)
GAS_INDEX = 0
CAP_SAFETY = 0.98  # the load cap sits 2% inside the midpoint between the feasible and the exceeding load, so SLSQP's tolerance cannot flip it


class _Linear:
    """Broyden-updated linear model v(u) ~ v0 + J (u - u0) of the measured quantities."""

    def __init__(self, n_q: int, n: int) -> None:
        self.J = np.zeros((n_q, n))
        self.u_prev: np.ndarray | None = None
        self.v_prev: np.ndarray | None = None

    def update(self, u: np.ndarray, v: np.ndarray) -> None:
        if self.u_prev is not None:
            du = u - self.u_prev
            nn = float(du @ du)
            if nn > 1e-12:
                self.J += np.outer(v - self.v_prev - self.J @ du, du) / nn
        self.u_prev, self.v_prev = u.copy(), v.copy()


def optimizer_search(
    engine_fn: EngineFn,
    spec: FactorSpec,
    *,
    budget: int,
    seed: int,
    season: str = "winter",
    horizon_days: int = 30,
    duration_range: tuple[int, int] = (3, 14),
    n_starts: int = 4,
    bound_sd: float = 6.0,
    sigma_mult: float = 1.0,
    spike: SpikeOverlay | None = None,
    target_usd: float = config.LOSS_TARGET_USD,
    rules_fn: RulesFn = default_hard_rules,
    max_iter: int = 200,
    warm_start: bool = True,
    warm_duration: int = 7,
    tail_d2: float | None = None,
    z_limits: Mapping[str, tuple[float, float]] | None = None,
    margin_loss: float = 0.01,
    margin_tail: float = 0.05,
    margin_z: float = 0.5,
    fd_step_sd: float = 0.25,
    max_newton: int = 5,
    damping: float = 0.9,
    overshoot: float = 0.02,
    restart_scale: float = 0.5,
) -> list[dict]:
    """Run SLSQP within an equal engine-evaluation budget; return all evaluated scenarios as records (arm 'optimizer').

    Variables u = (x - mu)/sd for the five core factors within +/- bound_sd. Objective u' A u (= D^2 of the Gaussian core).
    See the module docstring for the warm start, the plausibility constraints and the restarts. Deterministic given seed.
    """
    if not warm_start:
        return _legacy_search(
            engine_fn, spec, budget=budget, seed=seed, season=season, horizon_days=horizon_days,
            duration_range=duration_range, n_starts=n_starts, bound_sd=bound_sd, sigma_mult=sigma_mult, spike=spike,
            target_usd=target_usd, rules_fn=rules_fn, max_iter=max_iter,
        )
    rng = np.random.default_rng(seed)
    mu, sd, cov = spec.mu, spec.sd, spec.cov
    n = len(sd)
    chol = np.linalg.cholesky(cov)
    corr = np.diag(1.0 / sd) @ cov @ np.diag(1.0 / sd)  # A^-1 in standardised coordinates
    a_mat = np.diag(sd) @ np.linalg.inv(cov) @ np.diag(sd)  # D^2 in standardised coordinates
    lo_d, hi_d = duration_range[0], min(duration_range[1], horizon_days)
    ev = Evaluator(engine_fn, budget, "optimizer", seed, season, horizon_days, target_usd, rules_fn)
    factors = config.GAUSSIAN_CORE_FACTORS
    lim = dict(z_limits or {})
    lim_idx = [(k, f) for k, f in enumerate(factors) if f in lim]
    n_q = 2 + n  # loss (USD m), sqrt of the engine D^2, z of the five factors
    lin = _Linear(n_q, n)
    state = {"dur": int(warm_duration), "it": 0, "limit": budget, "scale": 1.0, "l_ok": 0.0, "l_ok_lo": 0.0, "l_bad_hi": np.inf, "l_bad_lo": -np.inf}
    last_result: dict = {}

    def measure(u: np.ndarray, update: bool = True) -> np.ndarray | None:
        """Engine call at u (cached/ budgeted); vector of measured quantities, or None if the engine rejects the shock."""
        shock = factors_to_shock(mu + sd * u, state["dur"], 0, 0.0)
        res = ev.evaluate(shock, iteration=state["it"], limit=state["limit"])
        state["it"] += 1
        if res is None:
            return None
        zd = res.get("z") or {}
        v = np.empty(n_q)
        v[0] = -res["pnl_total"] / LOSS_SCALE_USD / state["scale"]  # loss in warm-duration units (loss ~ shocked days)
        v[1] = np.sqrt(max(float(res.get("d2", 0.0)), 0.0))  # distance-like: closer to linear in u than D^2 or log D^2
        v[2:] = [float(zd.get(f, 0.0)) for f in factors]
        exceeded = list(res.get("marginals_exceeded") or [])
        if "T" in exceeded:
            if u[LOAD_INDEX] >= 0:
                state["l_bad_hi"] = min(state["l_bad_hi"], float(u[LOAD_INDEX]))
            else:
                state["l_bad_lo"] = max(state["l_bad_lo"], float(u[LOAD_INDEX]))
        elif u[LOAD_INDEX] >= 0:
            state["l_ok"] = max(state["l_ok"], float(u[LOAD_INDEX]))
        else:
            state["l_ok_lo"] = min(state["l_ok_lo"], float(u[LOAD_INDEX]))
        last_result["res"] = res
        if update:
            lin.update(u, v)
        return v

    def l_caps() -> tuple[float, float]:
        hi = bound_sd
        if np.isfinite(state["l_bad_hi"]):
            hi = min(hi, CAP_SAFETY * (state["l_ok"] + 0.5 * (state["l_bad_hi"] - state["l_ok"])))
        lo = -bound_sd
        if np.isfinite(state["l_bad_lo"]):
            lo = max(lo, CAP_SAFETY * (state["l_ok_lo"] + 0.5 * (state["l_bad_lo"] - state["l_ok_lo"])))
        return lo, hi

    def scaled_jacobian() -> np.ndarray:
        j = lin.J.copy()
        j[0] *= state["scale"]  # back to the current duration's loss (about proportional to the number of shocked days)
        return j

    tgt = target_usd / LOSS_SCALE_USD

    def build(v: np.ndarray, u: np.ndarray) -> np.ndarray:
        rows = [v[0] * state["scale"] - tgt * (1.0 + margin_loss)]
        if tail_d2 is not None:
            rows.append(v[1] - np.sqrt(tail_d2 * (1.0 + margin_tail)))
        for k, f in lim_idx:
            lo_z, hi_z = lim[f]
            rows.append(hi_z - margin_z - v[2 + k])
            rows.append(v[2 + k] - lo_z - margin_z)
        lo_c, hi_c = l_caps()
        rows.append(hi_c - u[LOAD_INDEX])
        rows.append(u[LOAD_INDEX] - lo_c)
        return np.array(rows)

    def build_jac() -> np.ndarray:
        j = scaled_jacobian()
        rows = [j[0]]
        if tail_d2 is not None:
            rows.append(j[1])
        for k, _ in lim_idx:
            rows.append(-j[2 + k])
            rows.append(j[2 + k])
        up, dn = np.zeros(n), np.zeros(n)
        up[LOAD_INDEX], dn[LOAD_INDEX] = -1.0, 1.0
        rows += [up, dn]
        return np.array(rows)

    def polish(u0: np.ndarray, bounds: list[tuple[float, float]], stop_at: int) -> None:
        state["limit"] = stop_at

        def cons(u: np.ndarray) -> np.ndarray:
            v = measure(u)
            if v is None:
                return np.full(len(build_jac()), -1e3)
            # the loss row must be on the unscaled measured loss; the scale only affects extrapolation (Jacobian)
            return build(v, u)

        constraints = [{"type": "ineq", "fun": cons, "jac": lambda u: build_jac()}]
        try:
            minimize(
                lambda u: float(u @ a_mat @ u), np.clip(u0, [b[0] for b in bounds], [b[1] for b in bounds]),
                jac=lambda u: 2.0 * a_mat @ u, bounds=bounds, constraints=constraints, method="SLSQP",
                options={"maxiter": max_iter, "ftol": 1e-6},
            )
        except BudgetExhausted:
            pass
        except (FloatingPointError, np.linalg.LinAlgError):
            pass

    # ---- 1. warm start: the conditional-Gaussian linearised point, with this arm's own engine calls
    u_best: np.ndarray | None = None
    try:
        state["limit"] = budget
        v0 = measure(np.zeros(n), update=False)
        if v0 is not None:
            jfd = np.zeros((n_q, n))
            h = fd_step_sd
            for i in range(n):
                u = np.zeros(n)
                u[i] = h
                vi = measure(u, update=False)
                jfd[:, i] = 0.0 if vi is None else (vi - v0) / h
            lin.J = jfd
            lin.u_prev, lin.v_prev = np.zeros(n), v0.copy()
            g_u = jfd[0] * LOSS_SCALE_USD
            direction = corr @ g_u
            curv = float(g_u @ direction)
            l0 = v0[0] * LOSS_SCALE_USD
            if curv > 0.0:
                aim = target_usd * (1.0 + overshoot)
                lam = max((aim - l0) / curv, 0.0)
                prev: tuple[float, float] | None = None
                slope = curv
                best_d2 = np.inf
                for _ in range(max_newton):
                    u = np.clip(lam * direction, -bound_sd, bound_sd)
                    v = measure(u)
                    if v is None:
                        break
                    lk = v[0] * LOSS_SCALE_USD
                    if lk >= target_usd and float(u @ a_mat @ u) < best_d2:
                        u_best, best_d2 = u.copy(), float(u @ a_mat @ u)
                    if target_usd <= lk <= target_usd * (1.0 + 2.0 * overshoot + 0.03):
                        break
                    if prev is not None and abs(lam - prev[0]) > 1e-15:
                        sec = (lk - prev[1]) / (lam - prev[0])
                        if sec > 0.0:
                            slope = sec
                    prev = (lam, lk)
                    lam = max(lam + damping * (aim - lk) / slope, 0.0)
                if u_best is None:
                    u_best = np.clip(lam * direction, -bound_sd, bound_sd)
        # ---- 2. sign-consistency bounds from the warm point (hard rule: cold_snap needs gas >= 0)
        base_bounds = [(-bound_sd, bound_sd)] * n
        l_cold = float(np.log(1.05)) / float(sd[LOAD_INDEX])
        centre = np.zeros(n) if u_best is None else u_best
        if season == "winter":
            if centre[LOAD_INDEX] >= l_cold:
                base_bounds[GAS_INDEX] = (0.0, bound_sd)
            else:
                base_bounds[LOAD_INDEX] = (-bound_sd, l_cold - 1e-4)
        # ---- 3. polish the warm point, then restarts with equal shares of the remaining budget
        rounds = max(1, int(n_starts))
        k = 0
        while ev.used < budget and k < 20 * rounds:
            remaining = budget - ev.used
            share = max(2, remaining // max(rounds - k, 1)) if k < rounds else remaining
            stop_at = min(budget, ev.used + share)
            if k == 0:
                state["dur"], state["scale"] = int(warm_duration), 1.0
                u0 = centre.copy()
            else:
                state["dur"] = int(rng.integers(min(max(lo_d, int(warm_duration)), hi_d), hi_d + 1))
                state["scale"] = state["dur"] / float(warm_duration)
                u0 = centre + restart_scale * (np.linalg.solve(np.diag(sd), chol @ rng.standard_normal(n)))
                if season == "winter" and u0[LOAD_INDEX] >= l_cold:
                    u0[GAS_INDEX] = abs(u0[GAS_INDEX])
            polish(u0, base_bounds, stop_at)
            k += 1
            if ev.used >= stop_at and ev.used >= budget:
                break
    except BudgetExhausted:
        pass
    return ev.records


def _legacy_search(
    engine_fn: EngineFn,
    spec: FactorSpec,
    *,
    budget: int,
    seed: int,
    season: str,
    horizon_days: int,
    duration_range: tuple[int, int],
    n_starts: int,
    bound_sd: float,
    sigma_mult: float,
    spike: SpikeOverlay | None,
    target_usd: float,
    rules_fn: RulesFn,
    max_iter: int,
) -> list[dict]:
    """Original optimizer: SLSQP from n_starts random starts, analytic D^2, engine loss constraint, finite differences."""
    overlay = SpikeOverlay() if spike is None else spike
    rng = np.random.default_rng(seed)
    sd, chol = spec.sd, np.linalg.cholesky(spec.cov)
    scale = np.diag(sd)
    a_mat = scale @ np.linalg.inv(spec.cov) @ scale
    lo_d, hi_d = duration_range[0], min(duration_range[1], horizon_days)
    ev = Evaluator(engine_fn, budget, "optimizer", seed, season, horizon_days, target_usd, rules_fn)
    n = len(sd)

    n_eff = max(1, min(n_starts, budget))
    for k in range(n_eff):
        share = (budget - ev.used) // (n_eff - k)
        if share <= 0:
            break
        stop_at = ev.used + share
        duration = int(rng.integers(lo_d, hi_d + 1))
        n_spike, avg0 = overlay.sample(rng, duration)
        x0 = spec.mu + sigma_mult * chol @ rng.standard_normal(n)
        u0 = np.clip((x0 - spec.mu) / sd, -bound_sd, bound_sd)
        has_spike = n_spike > 0
        w0 = np.clip((avg0 - overlay.threshold_usd) / (overlay.max_avg_usd - overlay.threshold_usd), 0.0, 1.0) if has_spike else 0.0
        z0 = np.append(u0, w0) if has_spike else u0
        bounds = [(-bound_sd, bound_sd)] * n + ([(0.0, 1.0)] if has_spike else [])

        def to_shock(z: np.ndarray) -> dict:
            x = spec.mu + sd * z[:n]
            avg = overlay.threshold_usd + z[n] * (overlay.max_avg_usd - overlay.threshold_usd) if has_spike else 0.0
            return factors_to_shock(x, duration, n_spike, avg)

        def objective(z: np.ndarray) -> float:
            u = z[:n]
            return float(u @ a_mat @ u)

        def gradient(z: np.ndarray) -> np.ndarray:
            g = np.zeros_like(z)
            g[:n] = 2.0 * a_mat @ z[:n]
            return g

        def slack(z: np.ndarray) -> float:
            result = ev.evaluate(to_shock(z), iteration=k, limit=stop_at)
            loss = -1e3 * LOSS_SCALE_USD if result is None else -result["pnl_total"]
            return float(loss - target_usd) / LOSS_SCALE_USD

        try:
            minimize(
                objective, z0, jac=gradient, bounds=bounds, constraints=[{"type": "ineq", "fun": slack}],
                method="SLSQP", options={"maxiter": max_iter, "ftol": 1e-8, "eps": 1e-2},
            )
        except BudgetExhausted:
            if ev.used >= budget:
                break
    return ev.records
