// Service worker: the ONLY place that talks to the Chronicle API. Running the
// fetch here (extension origin, with host_permissions) sidesteps page CORS — a
// content-script fetch would carry the job board's origin and be rejected.
import { getSettings } from "./lib/storage";
import type { BgMessage, BgResponse } from "./lib/types";

async function apiFetch(path: string, init: RequestInit = {}): Promise<BgResponse> {
  const { token, apiBase } = await getSettings();
  if (!token) return { ok: false, error: "No token — connect the extension in the popup." };
  try {
    const res = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      return { ok: false, status: res.status, error: detail || `HTTP ${res.status}` };
    }
    return { ok: true, status: res.status, data: await res.json() };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

chrome.runtime.onMessage.addListener((msg: BgMessage, _sender, sendResponse) => {
  (async () => {
    switch (msg.type) {
      case "API_GET_ME":
        sendResponse(await apiFetch("/extension/me"));
        break;
      case "API_GET_PROFILE":
        sendResponse(await apiFetch("/extension/profile"));
        break;
      case "API_SAVE":
        sendResponse(
          await apiFetch("/extension/saved", {
            method: "POST",
            body: JSON.stringify(msg.payload),
          })
        );
        break;
      default:
        sendResponse({ ok: false, error: "Unknown message" });
    }
  })();
  return true; // keep the message channel open for the async response
});
