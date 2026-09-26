// Headless screenshots + horizontal-overflow audit.
// usage: node shots.mjs config.json
// config: { baseURL, outDir, prefix, routes: [{name, path}], shots: [{w,h}], overflowWidths: [360,390,414],
//           cookies?: [{name,value,domain,path}], waitMs?: 1500, colorScheme?: "light"|"dark" }
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const waitMs = cfg.waitMs ?? 1500;
fs.mkdirSync(cfg.outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  reducedMotion: cfg.reducedMotion ?? "no-preference",
  colorScheme: cfg.colorScheme ?? "light",
  deviceScaleFactor: 1,
});
if (cfg.cookies?.length) await ctx.addCookies(cfg.cookies);
const page = await ctx.newPage();

async function open(url) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 120000 });
      await page.waitForTimeout(waitMs);
      return true;
    } catch (e) {
      if (attempt === 1) { console.error("goto failed", url, e.message); return false; }
    }
  }
}

const report = { baseURL: cfg.baseURL, prefix: cfg.prefix, routes: {} };
for (const r of cfg.routes) {
  const url = cfg.baseURL + r.path;
  const entry = { path: r.path, shots: [], overflow: {} };
  for (const s of cfg.shots ?? []) {
    await page.setViewportSize({ width: s.w, height: s.h });
    if (!(await open(url))) continue;
    const file = path.join(cfg.outDir, `${cfg.prefix}-${r.name}-${s.w}.jpg`);
    await page.screenshot({ path: file, type: "jpeg", quality: 70 });
    entry.shots.push(path.basename(file));
  }
  for (const w of cfg.overflowWidths ?? []) {
    await page.setViewportSize({ width: w, height: 800 });
    if (!(await open(url))) continue;
    entry.overflow[w] = await page.evaluate(() => {
      const W = document.documentElement.clientWidth;
      const sw = document.documentElement.scrollWidth;
      const clipped = (el) => {
        for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
          const o = getComputedStyle(p).overflowX;
          if (o === "hidden" || o === "clip" || o === "auto" || o === "scroll") return true;
        }
        return false;
      };
      const offenders = [];
      if (sw > W) {
        for (const el of document.querySelectorAll("body *")) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.right > W + 1 && !clipped(el)) {
            const id = el.id ? "#" + el.id : "";
            const cls = (el.getAttribute("class") || "").split(/\s+/).slice(0, 4).join(".");
            offenders.push({ el: el.tagName.toLowerCase() + id + (cls ? "." + cls : ""), right: Math.round(rect.right) });
          }
        }
        offenders.sort((a, b) => b.right - a.right);
      }
      return { viewport: W, scrollWidth: sw, overflows: sw > W, offenders: offenders.slice(0, 8) };
    });
  }
  if (cfg.reducedMotionAudit) {
    const rctx = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 390, height: 844 } });
    if (cfg.cookies?.length) await rctx.addCookies(cfg.cookies);
    const rp = await rctx.newPage();
    try {
      await rp.goto(url, { waitUntil: "networkidle", timeout: 120000 });
      await rp.waitForTimeout(waitMs);
      entry.reducedMotion = await rp.evaluate(() => {
        const hidden = [];
        for (const el of document.querySelectorAll("main *")) {
          const cs = getComputedStyle(el);
          if (parseFloat(cs.opacity) < 0.05 && (el.innerText || "").trim().length > 20) {
            const covered = hidden.some((h) => h.node.contains(el));
            if (!covered) hidden.push({ node: el, text: el.innerText.trim().slice(0, 60) });
          }
        }
        return { hiddenBlocks: hidden.length, samples: hidden.slice(0, 5).map((h) => h.text) };
      });
    } catch (e) { entry.reducedMotion = { error: e.message }; }
    await rctx.close();
  }
  report.routes[r.name] = entry;
  console.error(`done ${r.name}`);
}
fs.writeFileSync(path.join(cfg.outDir, `${cfg.prefix}-report.json`), JSON.stringify(report, null, 1));
console.log(JSON.stringify(Object.fromEntries(Object.entries(report.routes).map(([k, v]) =>
  [k, { ...Object.fromEntries(Object.entries(v.overflow).map(([w, o]) => [w, o.overflows ? `OVERFLOW ${o.scrollWidth}px` : "ok"])),
        ...(v.reducedMotion ? { rm_hidden: v.reducedMotion.hiddenBlocks ?? v.reducedMotion.error } : {}) }]))));
await browser.close();
