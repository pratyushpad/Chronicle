import type { PayPeriod } from "@/lib/format";
import type { DescriptionBlock } from "@/lib/description";
import { ApiUnavailableError } from "@/lib/api-errors";
import { SERVICE_HEADER, serviceKey } from "@/lib/internal-service";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// New response fields are optional: Vercel previews run new web against the prod API
// until the API deploys, so every consumer must degrade when a field is absent.
export interface JobListItem {
  id: number;
  title: string;
  company_name: string;
  company_id: number;
  company_domain?: string | null;
  location_normalized: string | null;
  locations?: string[] | null;
  location_count?: number | null;
  remote: boolean | null;
  department: string | null;
  employment_type: string | null;
  experience_level: string | null;
  tech_tags?: string[] | null;
  sponsorship_flag?: string | null;
  /** Legacy annualized pay (sorting + old clients). Display goes through formatPay. */
  salary_min?: number | null;
  salary_max?: number | null;
  /** Structured pay as the source stated it. Absent on the pre-PR-1 API. */
  pay_min?: number | null;
  pay_max?: number | null;
  /** ISO 4217, e.g. "USD". */
  pay_currency?: string | null;
  pay_period?: PayPeriod | null;
  pay_source?: "ats" | "text" | null;
  /** Student filters as the posting states them (null = unstated). Absent before PR 4. */
  term_season?: "summer" | "fall" | "spring" | "winter" | null;
  term_year?: number | null;
  degree_levels?: ("bachelor" | "master" | "phd")[] | null;
  grad_year_min?: number | null;
  grad_year_max?: number | null;
  us_citizen_required?: boolean | null;
  us_person_required?: boolean | null;
  clearance_required?: boolean | null;
  workplace_type?: "onsite" | "hybrid" | "remote" | null;
  country?: string | null;
  posted_at: string | null;
  first_seen_at: string;
  /** Last time Chronicle saw the role live on the company's board. */
  last_seen_at?: string;
  is_active?: boolean;
  apply_url: string;
  is_new: boolean;
}

export interface JobDetail extends JobListItem {
  company_industry: string | null;
  location_raw: string | null;
  /** Plain text of the description (every API version sends it). */
  description_text: string | null;
  /** The description as typed blocks. Absent on the pre-PR-2 API. */
  description_blocks?: DescriptionBlock[];
  /** ~180 characters of plain text for meta tags. Absent on the pre-PR-2 API. */
  description_summary?: string | null;
  last_seen_at: string;
}

export interface SitemapJobs {
  total: number;
  /** The sitemap only reads `id`; the API may leave `last_seen_at` out. */
  items: { id: number; last_seen_at?: string | null }[];
}

export interface CompanyItem {
  id: number;
  name: string;
  ats: string;
  careers_url: string | null;
  industry: string | null;
  active_job_count: number;
}

export interface CompanyDetail extends CompanyItem {
  last_ingested_at: string | null;
}

export interface VelocityPoint {
  week: string; // ISO date (Monday)
  opened: number;
  closed: number;
}

export interface CompanyVelocity {
  company_id: number;
  weeks: VelocityPoint[];
  new_this_week: number;
  active_now: number;
  opened_last_30d: number;
  closed_last_30d: number;
  /** Roles already open at the board's first ingest, left out of "opened". Absent on the pre-PR-3 API. */
  first_ingest_excluded?: number;
}

export interface LastRunSummary {
  started_at: string | null;
  jobs_seen: number;
  jobs_new: number;
  companies_ok: number;
  companies_failed: number;
}

export interface IndustryCount {
  industry: string;
  count: number;
}

/** How recently the company boards were actually re-checked (from companies.last_ingested_at
 *  over active boards). Absent on the pre-PR-1 API — copy must have a number-free fallback. */
export interface Freshness {
  boards_active: number;
  boards_checked_24h: number;
  boards_checked_7d: number;
  median_check_age_hours: number | null;
  oldest_check_at: string | null;
}

export interface Meta {
  departments: string[];
  locations: string[];
  employment_types: string[];
  experience_levels: string[];
  industries: string[];
  last_run: LastRunSummary | null;
  total_active_jobs: number;
  total_companies: number;
  fresh_since_last_run: number;
  remote_count: number;
  experience_counts: Record<string, number>;
  top_industries: IndustryCount[];
  freshness?: Freshness | null;
  /** "summer-2027" terms and ISO country codes present among active roles (PR 4). */
  terms?: string[];
  countries?: string[];
  /** Whether the server sends alert emails (PR 6). Absent on older APIs: treat as false. */
  email_alerts?: boolean;
}

export interface JobListResponse {
  items: JobListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  search_mode?: "semantic" | "hybrid" | null;
}

export interface JobParams {
  q?: string;
  mode?: "keyword" | "semantic" | "hybrid";
  company?: string;
  company_id?: number;
  department?: string;
  location?: string;
  remote?: boolean;
  employment_type?: string;
  experience_level?: string;
  level?: string;
  industry?: string;
  since_last_run?: boolean;
  page?: number;
  page_size?: number;
  sort?: string;
  hide_citizen_required?: boolean;
  hide_us_person_required?: boolean;
  hide_clearance_required?: boolean;
  hide_grad_only?: boolean;
  term?: string;
  workplace?: string;
  country?: string;
}

/**
 * Fetch JSON with a per-attempt timeout and retry-on-timeout/5xx. Absorbs Render
 * free-tier cold starts (first request after spin-down can take ~30-60s) and transient
 * 5xx without letting a slow wake-up hang the request forever. 4xx (except an optional
 * notFound) fail fast — they won't get better on retry.
 */
class FinalError extends Error {}

/** serviceKey() reads a server-only env var; fetchJSON only runs in server renders. */
async function serverKey(): Promise<string | undefined> {
  return typeof window === "undefined" ? serviceKey() : undefined;
}

async function fetchJSON<T>(
  path: string,
  opts: {
    revalidate?: number;
    retries?: number;
    timeoutMs?: number;
    errMsg: string;
    notFoundMsg?: string;
  },
): Promise<T> {
  // One retry for these idempotent GETs, 10 s per attempt, 500 ms backoff: worst case is
  // about 20.5 s, under the ~25 s a server render can afford. The retry is what absorbs a
  // Render cold start (the first attempt wakes the API, the second lands on it). Long waits
  // were what cost GB-hours during the Oct 2026 database outage (9 to 67 GB-h in a day);
  // the API now answers 503 fast when the database is down, so only a cold start is slow.
  // Callers that cannot afford a retry (similar roles, sitemap) pass retries: 0.
  const { revalidate = 300, retries = 1, timeoutMs = 10000, errMsg, notFoundMsg } = opts;
  const key = await serverKey();
  let lastErr: unknown;
  let lastStatus = 0;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${API}${path}`, {
        next: { revalidate },
        signal: controller.signal,
        // Lets the API skip the per-IP search limit for server renders (Vercel's few egress
        // IPs would otherwise share one bucket). Absent in browsers and local dev.
        ...(key ? { headers: { [SERVICE_HEADER]: key } } : {}),
      });
      if (res.ok) return (await res.json()) as T;
      // 4xx answers are final (a retry gets the same one); 5xx and network errors retry.
      if (notFoundMsg && res.status === 404) throw new FinalError(notFoundMsg);
      if (res.status < 500) throw new FinalError(`${errMsg} (${res.status})`);
      lastStatus = res.status;
      lastErr = new Error(`${errMsg} (${res.status})`);
    } catch (e) {
      if (e instanceof FinalError) throw new Error(e.message);
      lastErr = e;
      lastStatus = 0;
    } finally {
      clearTimeout(timer);
    }
    if (attempt < retries) await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
  }
  // A final 503 means the database is down or suspended: say so, so the page can show a
  // calm notice instead of the generic error.
  if (lastStatus === 503) throw new ApiUnavailableError(`${errMsg} (503)`);
  throw lastErr instanceof Error ? lastErr : new Error(errMsg);
}

function buildQuery(params: Record<string, unknown>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      q.set(k, String(v));
    }
  }
  const str = q.toString();
  return str ? `?${str}` : "";
}

/**
 * `revalidate` is the cache window in seconds. It is a separate argument, not a JobParams
 * field, so it never reaches the query string. The feed keeps the 5-minute default; the
 * job page's "more at company" list passes an hour.
 */
export async function getJobs(
  params: JobParams = {},
  { revalidate = 300 }: { revalidate?: number } = {},
): Promise<JobListResponse> {
  return fetchJSON<JobListResponse>(
    `/jobs${buildQuery(params as Record<string, unknown>)}`,
    { revalidate, errMsg: "Failed to fetch jobs" },
  );
}

// A week. Job pages are long-tail: with ~36K roles a crawler revisits each one about every
// 29 hours, so an hour-long window made 97% of hits a fresh render (2 API calls, 20 ms CPU).
// A role's text rarely changes after posting; closing it is the main change, and a closed
// role showing as open for a few days is an acceptable trade for the hosting quota.
export const JOB_PAGE_REVALIDATE = 604800;

export async function getJob(id: number): Promise<JobDetail> {
  // One retry to absorb a Render cold start or a transient 503 under prefetch fan-out.
  return fetchJSON<JobDetail>(`/jobs/${id}`, {
    revalidate: JOB_PAGE_REVALIDATE,
    retries: 1,
    errMsg: "Job fetch failed",
    notFoundMsg: "Job not found",
  });
}

export async function getCompanies(params: { industry?: string } = {}): Promise<CompanyItem[]> {
  return fetchJSON<CompanyItem[]>(`/companies${buildQuery(params)}`, {
    revalidate: 3600,
    errMsg: "Failed to fetch companies",
  });
}

export async function getCompany(id: number): Promise<CompanyDetail> {
  return fetchJSON<CompanyDetail>(`/companies/${id}`, {
    revalidate: 3600,
    errMsg: "Failed to fetch company",
    notFoundMsg: "Company not found",
  });
}

export async function getCompanyVelocity(id: number, weeks = 8): Promise<CompanyVelocity> {
  return fetchJSON<CompanyVelocity>(`/companies/${id}/velocity?weeks=${weeks}`, {
    revalidate: 3600,
    errMsg: "Failed to fetch company velocity",
  });
}

export async function getMeta(): Promise<Meta> {
  // Every page's layout calls this. It only changes when the twice-daily ingest runs.
  return fetchJSON<Meta>(`/meta`, { revalidate: 3600, errMsg: "Failed to fetch meta" });
}

/**
 * Nearest active roles by embedding. Optional by design: an empty list when the API
 * predates the endpoint (Vercel previews talk to production), the job isn't embedded
 * yet, or the call is slow — similar roles must never hold up or break a job page.
 */
export async function getSimilarJobs(id: number, limit = 4): Promise<JobListItem[]> {
  try {
    return await fetchJSON<JobListItem[]>(`/jobs/${id}/similar?limit=${limit}`, {
      revalidate: 3600,
      retries: 0,
      timeoutMs: 8000,
      errMsg: "Failed to fetch similar jobs",
    });
  } catch {
    return [];
  }
}

export async function getSitemapJobs(offset: number, limit: number): Promise<SitemapJobs> {
  return fetchJSON<SitemapJobs>(`/sitemap/jobs?offset=${offset}&limit=${limit}`, {
    revalidate: 86400, // a day; keep equal to `revalidate` in app/sitemap.ts (the shorter one wins)
    timeoutMs: 30000,
    retries: 0,
    errMsg: "Failed to fetch sitemap jobs",
  });
}

export interface StatusRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  seconds: number | null;
  boards_total: number;
  boards_ok: number;
  boards_failed: number;
  jobs_seen: number;
  jobs_new: number;
  jobs_closed: number;
  open: boolean;
  crashed: boolean;
}

export interface FailingBoard {
  company: string | null;
  ats: string | null;
  slug: string | null;
  failed_runs: number;
  last_error: string | null;
  last_success_at: string | null;
}

export interface StatusResponse {
  runs: StatusRun[];
  failing_boards: FailingBoard[];
  freshness?: Freshness | null;
}

/** Ingest health for /status. Absent on APIs before PR 7 (the page says so). */
export async function getStatus(): Promise<StatusResponse> {
  return fetchJSON<StatusResponse>(`/status`, { revalidate: 900, errMsg: "Failed to fetch status" });
}
