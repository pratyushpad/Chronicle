// Shared message + data contracts across content / background / popup.

export type Ats = "greenhouse" | "lever" | "ashby";

/** Job identity extracted from a recognized application page. */
export interface PageJob {
  ats: Ats;
  company_slug: string;
  company_name: string;
  source_job_id: string;
  title: string;
  apply_url: string;
  location: string | null;
}

/** Autofill payload from GET /extension/profile. */
export interface ProfileData {
  full_name: string | null;
  email: string;
  phone: string | null;
  location: string | null;
  work_authorization: string | null;
  links: Record<string, string> | null;
}

export interface MeData {
  email: string;
  name: string | null;
}

// ── Messages to the background service worker (it owns all API calls) ──
export type BgMessage =
  | { type: "API_GET_ME" }
  | { type: "API_GET_PROFILE" }
  | { type: "API_SAVE"; payload: PageJob };

export interface BgResponse<T = unknown> {
  ok: boolean;
  status?: number;
  data?: T;
  error?: string;
}

// ── Messages to the content script (from the popup) ──
export type ContentMessage = { type: "FILL_PAGE" } | { type: "GET_PAGE_JOB" };

export interface FillResult {
  ok: boolean;
  filled: number;
  fields: string[];
}
