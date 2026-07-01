// Thin wrappers over chrome.storage.local for the connection settings.

const DEFAULT_API_BASE = "http://localhost:8002";

export interface Settings {
  token: string;
  apiBase: string;
}

export async function getSettings(): Promise<Settings> {
  const { token, apiBase } = await chrome.storage.local.get(["token", "apiBase"]);
  return {
    token: typeof token === "string" ? token : "",
    apiBase: typeof apiBase === "string" && apiBase ? apiBase : DEFAULT_API_BASE,
  };
}

export async function setSettings(patch: Partial<Settings>): Promise<void> {
  await chrome.storage.local.set(patch);
}
