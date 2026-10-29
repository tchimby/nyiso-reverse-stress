/* Browser port of the scenario engine: apply_shock + book P&L + factor scoring (revstress/shock.py, book.py, risk/plausibility.py).
   Parameters come from data/engine.json (scripts/export_engine.py). Not ported: spike days (spike_days must be 0) and nearest-date search.
   Verified against the Python engine on the reference cases in engine.json: node ui/check_engine.js */
(function (root) {
  const CORE = ["g", "l", "s", "c", "d"];
  const NEUTRAL = { gas_hh_pct: 0, ny_gas_basis_usd: 0, load_peak_ratio: 1, dc_load_shock_mw: 0, wh_onpeak_pct: 0, dom_minus_wh_usd: 0, dart_pct: 0, duration_days: 0 };
  const sum = (a) => a.reduce((x, y) => x + y, 0);
  const seasonOf = (E, date) => E.month_to_season[String(+date.slice(5, 7))];
  const doyOf = (date) => { const d = new Date(date + "T00:00:00Z"); return Math.round((d - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5); };

  function applyShock(E, season, shock) {
    const S = Object.assign({}, NEUTRAL, shock);
    const rows = E.seasons[season].rows, n = rows.length, pt = E.passthrough, cap = E.cap_usd;
    const dur = Math.max(0, Math.min(n, Math.round(S.duration_days)));
    const mask = rows.map((_, i) => i < dur);
    const dGas = Math.log1p(S.gas_hh_pct / 100), pct = 1 + S.wh_onpeak_pct / 100;
    const p = rows.map((r, i) => {
      const load0 = r.load_peak_mw, load1 = mask[i] ? load0 * S.load_peak_ratio + S.dc_load_shock_mw : load0;
      if (load1 <= 0) throw new Error("shocked load must stay positive");
      const l0 = Math.log(load0 / r.load_normal_mw), l1 = Math.log(load1 / r.load_normal_mw);
      const lt = pt.load_beta1 * (l1 - l0) + pt.load_beta2 * (l1 * l1 - l0 * l0);
      return { r, load1, fOn: mask[i] ? Math.exp(pt.gas_beta * dGas + lt) * pct : 1,
        fOff: mask[i] ? Math.exp(pt.gas_beta * dGas + pt.offpeak_scale * lt) * (1 + pt.offpeak_scale * S.wh_onpeak_pct / 100) : 1,
        dart: mask[i] ? 1 + S.dart_pct / 100 : 1 };
    });
    const decay = rows.map(() => 0);
    if (dur >= 1 && (pt.phi_level > 0 || pt.phi_spread > 0)) {
      const fOn = p[dur - 1].fOn, fOff = p[dur - 1].fOff;
      for (let i = dur; i < n; i++) {
        const k = i - (dur - 1);
        p[i].fOn = Math.exp(Math.log(fOn) * Math.pow(pt.phi_level, k));
        p[i].fOff = Math.exp(Math.log(fOff) * Math.pow(pt.phi_level, k));
        decay[i] = Math.pow(pt.phi_spread, k);
      }
    }
    const ws = E.weather_slopes;
    return p.map((x, i) => {
      const r = x.r;
      const daOn = Math.min(r.da_wh_on * x.fOn, cap), daOff = Math.min(r.da_wh_off * x.fOff, cap);
      const rtOn = Math.min(r.rt_wh_on * x.fOn * x.dart, cap), rtOff = Math.min(r.rt_wh_off * x.fOff * x.dart, cap);
      const shift = mask[i] ? S.dom_minus_wh_usd : decay[i] * S.dom_minus_wh_usd;
      const useH = r.hdd >= r.cdd, slope = useH ? ws.hdd : ws.cdd;
      const dd = mask[i] && slope > 1e-12 ? Math.log(S.load_peak_ratio) / slope : 0;
      return { date: r.date, mask: mask[i], da_wh_on: daOn, da_wh_off: daOff, rt_wh_on: rtOn, rt_wh_off: rtOff, wh_on: rtOn, wh_off: rtOff,
        dom_on: rtOn + (r.dom_on - r.wh_on) + shift, dom_off: rtOff + (r.dom_off - r.wh_off) + shift,
        hh_usd: mask[i] ? r.hh_usd * (1 + S.gas_hh_pct / 100) + S.ny_gas_basis_usd : r.hh_usd,
        load_peak_mw: x.load1, load_normal_mw: r.load_normal_mw,
        hdd: Math.max(r.hdd + (useH ? dd : 0), 0), cdd: Math.max(r.cdd + (useH ? 0 : dd), 0), onpeak_day: r.onpeak_day,
        capped: daOn >= cap || daOff >= cap || rtOn >= cap || rtOff >= cap };
    });
  }

  function pnl(E, path) {
    const B = E.book, sz = B.sizes;
    const daily = path.map((x) => {
      const on = x.onpeak_day ? 16 : 0, off = 24 - on;
      const g = x.hh_usd + B.basis[seasonOf(E, x.date)];
      const wh24 = (on * x.wh_on + off * x.wh_off) / 24, dom24 = (on * x.dom_on + off * x.dom_off) / 24;
      return { P1: on * sz.P1 * (x.wh_on - B.k1),
        P2: 24 * sz.P2 * ((dom24 - wh24) - B.c0),
        P3: off * sz.P3 * (x.da_wh_off - x.rt_wh_off),
        P4: on * sz.P4 * (Math.max(x.wh_on - B.heat_rate * g - B.vom, 0) - B.p4_prem),
        P5: 24 * sz.P5 * (x.load_peak_mw / x.load_normal_mw) * ((B.r - dom24) + (wh24 - B.h)),
        P6: -on * sz.P6 * (Math.max(x.wh_on - B.k6, 0) - B.p6_prem) };
    });
    return daily;
  }

  function score(E, season, path) {
    const pm = E.price_model, S = E.seasons;
    const fac = path.map((x) => {
      const sn = seasonOf(E, x.date), g = Math.log(Math.max(x.hh_usd, 0.01));
      const l = Math.log(x.load_peak_mw / pm.load_normal_by_month[String(+x.date.slice(5, 7))]);
      const a = 2 * Math.PI * doyOf(x.date) / 365.25, s1 = Math.sin(a), c1 = Math.cos(a);
      const h = [s1, c1, Math.sin(2 * a), Math.cos(2 * a), l * s1, l * c1];
      let fit = pm.intercepts[sn] + pm.b_gas * g + pm.b_load * l + pm.b_load2 * l * l;
      if (pm.harm.length) fit += sum(h.map((v, i) => v * pm.harm[i]));
      return { sn, g, l, T: x.hdd + x.cdd, s: Math.log(Math.max(x.wh_on, 1)) - fit, c: x.dom_on - x.wh_on, d: Math.log(Math.max(x.rt_wh_on, 1)) - Math.log(Math.max(x.da_wh_on, 1)) };
    });
    const d2 = fac.map((f) => {
      const z = CORE.map((k, i) => f[k] - S[f.sn].mu[i]), P = S[f.sn].precision;
      let t = 0; for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) t += z[i] * P[i][j] * z[j];
      return t;
    });
    let idx = path.map((x, i) => i).filter((i) => path[i].mask);
    if (!idx.length) idx = path.map((x, i) => i);
    let worst = idx[0]; idx.forEach((i) => { if (d2[i] > d2[worst]) worst = i; });
    const q = E.q.window_d2.filter((v) => v >= d2[worst]).length / E.q.window_d2.length;
    const exceeded = new Set();
    idx.forEach((i) => ["g", "l", "T", "s", "c", "d"].forEach((f) => { const [lo, hi] = S[fac[i].sn].limits[f]; if (fac[i][f] > hi || fac[i][f] < lo) exceeded.add(f); }));
    const failures = [];
    if (path.some((x) => x.capped && (x.da_wh_on > E.cap_usd + 1e-6 || x.rt_wh_on > E.cap_usd + 1e-6))) failures.push("price_cap");
    ["winter", "summer"].forEach((sn) => {
      const rr = idx.filter((i) => fac[i].sn === sn);
      if (rr.length && E.t_extreme[sn] !== undefined && sum(rr.map((i) => fac[i].T)) / rr.length > E.t_extreme[sn] && sum(rr.map((i) => fac[i].l)) / rr.length < 0) failures.push("extreme_weather_with_falling_load_" + sn);
    });
    const sev = failures.length || exceeded.size ? "implausible" : q < E.q.severe_max ? "severe" : q <= E.q.adverse_max ? "adverse" : "ordinary";
    return { d2: d2[worst], q, severity: sev, marginals_exceeded: [...exceeded].sort(), hard_rule_failures: failures, worst_day: path[worst].date, factors: fac, d2_daily: d2 };
  }

  function run(E, season, shock) {
    const path = applyShock(E, season, shock), daily = pnl(E, path), base = E.seasons[season].base_pnl, B = E.book;
    const pos = {}, ch = {};
    B.positions.forEach((p) => { pos[p] = sum(daily.map((d) => d[p])) - base[p]; });
    Object.keys(B.channel).forEach((p) => { ch[B.channel[p]] = (ch[B.channel[p]] || 0) + pos[p]; });
    const total = sum(Object.values(pos)), sc = score(E, season, path);
    return { path, daily, loss_usd: -total, pnl_by_position: pos, pnl_by_channel: ch, base: E.seasons[season].rows, score: sc,
      breach: -total >= E.target_usd && sc.q < E.q.adverse_max && !sc.hard_rule_failures.length && sc.severity !== "implausible" };
  }

  const api = { run, applyShock, pnl, score, NEUTRAL };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RevEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
