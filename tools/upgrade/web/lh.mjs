// Lighthouse (mobile, default simulated throttling) — median of N runs.
// usage: node lh.mjs <url> [runs=3] [label]
import lighthouse from "lighthouse";
import * as chromeLauncher from "chrome-launcher";
import { chromium } from "playwright";

const url = process.argv[2];
const runs = Number(process.argv[3] ?? 3);
const label = process.argv[4] ?? "";
const med = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };

const results = [];
for (let i = 0; i < runs; i++) {
  const chrome = await chromeLauncher.launch({
    chromePath: chromium.executablePath(),
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
  });
  try {
    const r = await lighthouse(url, {
      port: chrome.port, output: "json", logLevel: "error",
      onlyCategories: ["performance", "accessibility", "best-practices", "seo"],
    });
    const a = r.lhr.audits, c = r.lhr.categories;
    results.push({
      perf: Math.round(c.performance.score * 100), a11y: Math.round(c.accessibility.score * 100),
      bp: Math.round(c["best-practices"].score * 100), seo: Math.round(c.seo.score * 100),
      lcp: Math.round(a["largest-contentful-paint"].numericValue),
      cls: Number(a["cumulative-layout-shift"].numericValue.toFixed(3)),
      tbt: Math.round(a["total-blocking-time"].numericValue),
      fcp: Math.round(a["first-contentful-paint"].numericValue),
    });
  } finally {
    await chrome.kill();
  }
}
const keys = Object.keys(results[0]);
const median = Object.fromEntries(keys.map((k) => [k, med(results.map((r) => r[k]))]));
console.log(JSON.stringify({ label, url, runs: results.length, median, all: results }));
