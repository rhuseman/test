// Compare the JS port against golden.json. Exit code 1 on any mismatch.
const BC = require("./bolt_calc.js");
const cases = require("./golden.json");

const close = (a, b) =>
  b === "inf" ? a === Infinity : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));

let failures = 0;
for (const { input, expected, error } of cases) {
  let r;
  try {
    r = BC.analyze(input);
  } catch (e) {
    if (!error) { failures++; console.log("Unexpected error", input, e.message); }
    continue;
  }
  if (error) { failures++; console.log("Expected error", input); continue; }
  const got = {
    ...r, proof: r.strength.proof, yield_: r.strength.yield_,
    ultimate: r.strength.ultimate,
    kb: r.stiffness?.kb, km: r.stiffness?.km,
  };
  for (const [k, v] of Object.entries(expected)) {
    const ok = typeof v === "string" && v !== "inf" ? got[k] === v : close(got[k], v);
    if (!ok) { failures++; console.log(`Mismatch ${k}: js=${got[k]} py=${v}`, input); }
  }
}
console.log(`${cases.length} cases, ${failures} mismatches`);
process.exit(failures ? 1 : 0);
