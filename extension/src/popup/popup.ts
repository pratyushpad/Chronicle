import { getSettings, setSettings } from "../lib/storage";
import type { BgResponse, FillResult, MeData, PageJob } from "../lib/types";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const statusEl = $("status");
const resultEl = $("result");
const fillBtn = $<HTMLButtonElement>("fill");
const saveBtn = $<HTMLButtonElement>("save");
const connectBtn = $<HTMLButtonElement>("connect");
const apiBaseInput = $<HTMLInputElement>("apiBase");
const tokenInput = $<HTMLInputElement>("token");
const connDetails = $<HTMLDetailsElement>("conn");

function setStatus(text: string, kind: "ok" | "bad" | "" = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${kind}`.trim();
}

function setResult(text: string) {
  resultEl.textContent = text;
}

async function refreshStatus() {
  const { token } = await getSettings();
  if (!token) {
    setStatus("Not connected", "bad");
    connDetails.open = true;
    return;
  }
  const res = (await chrome.runtime.sendMessage({ type: "API_GET_ME" })) as BgResponse<MeData>;
  if (res.ok && res.data) {
    setStatus(res.data.name ? `✓ ${res.data.name.split(" ")[0]}` : "Connected", "ok");
  } else {
    setStatus("Token invalid", "bad");
    connDetails.open = true;
  }
}

async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function onFill() {
  const tab = await activeTab();
  if (!tab?.id) return;
  fillBtn.disabled = true;
  setResult("Filling…");
  try {
    const res = (await chrome.tabs.sendMessage(tab.id, { type: "FILL_PAGE" })) as FillResult;
    setResult(res?.filled ? `Filled ${res.filled} field${res.filled === 1 ? "" : "s"}.` : "No matching fields — open the application page first.");
  } catch {
    setResult("Open a Greenhouse/Lever/Ashby application page, then try again.");
  } finally {
    fillBtn.disabled = false;
  }
}

async function onSave() {
  const tab = await activeTab();
  if (!tab?.id) return;
  saveBtn.disabled = true;
  setResult("Saving…");
  try {
    const page = (await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_JOB" })) as { ok: boolean; job: PageJob | null };
    if (!page?.job) {
      setResult("No role detected on this page.");
      return;
    }
    const res = (await chrome.runtime.sendMessage({ type: "API_SAVE", payload: page.job })) as BgResponse;
    setResult(res.ok ? "Saved to your tracker." : res.error ?? "Save failed.");
  } catch {
    setResult("Open a Greenhouse/Lever/Ashby role page, then try again.");
  } finally {
    saveBtn.disabled = false;
  }
}

async function onConnect() {
  await setSettings({ token: tokenInput.value.trim(), apiBase: apiBaseInput.value.trim() });
  setResult("Saved connection.");
  await refreshStatus();
}

async function init() {
  const { token, apiBase } = await getSettings();
  apiBaseInput.value = apiBase;
  tokenInput.value = token;
  fillBtn.addEventListener("click", onFill);
  saveBtn.addEventListener("click", onSave);
  connectBtn.addEventListener("click", onConnect);
  await refreshStatus();
}

void init();
