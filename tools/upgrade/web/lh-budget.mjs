// Lighthouse budget for CI: median of N mobile runs of one URL, then assert.
// usage: node lh-budget.mjs <url> [runs=5]
//   LCP_BUDGET_MS (default 3500) and CLS_BUDGET (default 0.1) fail the job when exceeded.
//   LCP_TARGET_MS (default 2500, the plan's goal) is reported, not enforced, until the
//   feed meets it; then set LCP_BUDGET_MS to it. Local runs of the same build vary by
//   about 0.3 s, so the enforced budget is a regression guard, not the goal.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const url = process.argv[2];
const runs = process.argv[3] ?? "5";
const num = (name, fallback) => {
  const v = Number(process.env[name] ?? fallback);
  // A typo'd budget would make every comparison false and pass silently.
  if (!Number.isFinite(v) || v <= 0) throw new Error(`${name} must be a positive number`);
  return v;
};
const lcpBudget = num("LCP_BUDGET_MS", 3500);
const lcpTarget = num("LCP_TARGET_MS", 2500);
const clsBudget = num("CLS_BUDGET", 0.1);

const out = execFileSync(process.execPath, [fileURLToPath(new URL("./lh.mjs", import.meta.url)), url, runs, "budget"], {
  encoding: "utf8",
});
const { median } = JSON.parse(out.trim().split("\n").pop());
console.log(`Lighthouse median of ${runs}: perf ${median.perf}, a11y ${median.a11y}, LCP ${median.lcp} ms, CLS ${median.cls}, TBT ${median.tbt} ms`);
console.log(`LCP target ${lcpTarget} ms: ${median.lcp <= lcpTarget ? "met" : "NOT met yet"}`);
const failures = [];
if (median.lcp > lcpBudget) failures.push(`LCP ${median.lcp} ms > budget ${lcpBudget} ms`);
if (median.cls > clsBudget) failures.push(`CLS ${median.cls} > budget ${clsBudget}`);
if (failures.length) {
  console.error("Budget exceeded: " + failures.join("; "));
  process.exit(1);
}
