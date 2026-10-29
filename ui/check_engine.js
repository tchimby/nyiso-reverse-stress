// Compares the JS engine port with the Python reference cases stored in data/engine.json. Usage: node ui/check_engine.js
const E = require("./data/engine.json"), R = require("./engine.js");
let bad = 0, worst = 0;
for (const c of E.reference_cases) {
  const o = R.run(E, c.season, c.shock), rel = (a, b) => Math.abs(a - b) / Math.max(1, Math.abs(b));
  const errs = [["loss", rel(o.loss_usd, c.loss_usd)], ["d2", rel(o.score.d2, c.d2)], ["q", Math.abs(o.score.q - c.q)]];
  for (const p of Object.keys(c.pnl_by_position)) errs.push([p, rel(o.pnl_by_position[p], c.pnl_by_position[p])]);
  const sevOk = o.score.severity === c.severity, mexOk = JSON.stringify(o.score.marginals_exceeded) === JSON.stringify([...c.marginals_exceeded].sort());
  const m = Math.max(...errs.map((e) => e[1])); worst = Math.max(worst, m);
  if (m > 1e-6 || !sevOk || !mexOk) { bad++; console.log("MISMATCH", c.season, JSON.stringify(c.shock), errs.filter((e) => e[1] > 1e-6), o.score.severity, c.severity, o.score.marginals_exceeded, c.marginals_exceeded); }
}
console.log(`${E.reference_cases.length} cases, ${bad} mismatches, worst relative error ${worst.toExponential(2)}`);
process.exit(bad ? 1 : 0);
