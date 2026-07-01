// Content script entry. On a recognized application page it injects a small
// Chronicle bar ("Fill" + "Save to Chronicle") and answers popup messages.
// It NEVER submits — the only writes it makes are to input .value.
import { detectJob } from "./detect";
import { fillPage } from "./fill";
import type { BgResponse, ContentMessage, FillResult, MeData, PageJob, ProfileData } from "../lib/types";

const job: PageJob | null = detectJob();

function toast(msg: string, ok = true): void {
  const el = document.createElement("div");
  el.textContent = msg;
  el.style.cssText = `position:fixed;left:50%;bottom:76px;transform:translateX(-50%);z-index:2147483647;
    background:${ok ? "#111" : "#7a1010"};color:#fff;font:500 13px/1.4 ui-sans-serif,system-ui;
    padding:10px 16px;border:1px solid #000;max-width:420px;`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

async function doFill(): Promise<FillResult> {
  if (!job) return { ok: false, filled: 0, fields: [] };
  const res = (await chrome.runtime.sendMessage({ type: "API_GET_PROFILE" })) as BgResponse<ProfileData>;
  if (!res.ok || !res.data) {
    toast(res.error ?? "Could not load your Chronicle profile.", false);
    return { ok: false, filled: 0, fields: [] };
  }
  const result = fillPage(job.ats, res.data);
  toast(result.filled ? `Filled ${result.filled} field${result.filled === 1 ? "" : "s"}. Review before submitting.` : "No matching fields found on this page.", result.filled > 0);
  return result;
}

async function doSave(): Promise<void> {
  if (!job) return;
  const res = (await chrome.runtime.sendMessage({ type: "API_SAVE", payload: job })) as BgResponse;
  toast(res.ok ? "Saved to Chronicle tracker." : res.error ?? "Save failed.", res.ok);
}

// ── In-page bar ──
function injectBar(): void {
  if (!job || document.getElementById("chronicle-bar")) return;
  const bar = document.createElement("div");
  bar.id = "chronicle-bar";
  bar.style.cssText = `position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:2147483646;
    display:flex;gap:8px;align-items:center;background:#fff;border:2px solid #111;
    padding:8px 12px;font:500 12px/1 ui-sans-serif,system-ui;box-shadow:0 2px 0 #111;`;

  const label = document.createElement("span");
  label.textContent = "CHRONICLE";
  label.style.cssText = "font:600 10px/1 ui-monospace,monospace;letter-spacing:.15em;color:#111;margin-right:4px;";

  const fillBtn = mkBtn("Fill this page", true);
  const saveBtn = mkBtn("Save to Chronicle", false);
  fillBtn.onclick = () => void doFill();
  saveBtn.onclick = () => void doSave();

  const note = document.createElement("span");
  note.textContent = "fill-only · never submits";
  note.style.cssText = "font:500 10px/1 ui-sans-serif,system-ui;color:#666;margin-left:2px;";

  bar.append(label, fillBtn, saveBtn, note);
  document.body.appendChild(bar);
}

function mkBtn(text: string, solid: boolean): HTMLButtonElement {
  const b = document.createElement("button");
  b.textContent = text;
  b.style.cssText = `cursor:pointer;border:1px solid #111;padding:7px 12px;font:600 11px/1 ui-monospace,monospace;
    letter-spacing:.08em;text-transform:uppercase;${solid ? "background:#111;color:#fff;" : "background:#fff;color:#111;"}`;
  return b;
}

// ── Popup ↔ content messaging ──
chrome.runtime.onMessage.addListener((msg: ContentMessage, _sender, sendResponse) => {
  if (msg.type === "GET_PAGE_JOB") {
    sendResponse({ ok: true, job });
    return; // sync
  }
  if (msg.type === "FILL_PAGE") {
    doFill().then(sendResponse);
    return true; // async
  }
});

if (job) injectBar();

// Silence "unused" for the type-only import in some build modes.
export type { MeData };
