const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  salary_min?: number | null;
  salary_max?: number | null;
  posted_at: string | null;
  first_seen_at: string;
  apply_url: string;
  is_new: boolean;
}

export interface JobDetail extends JobListItem {
  company_industry: string | null;
  location_raw: string | null;
  description_text: string | null;
  last_seen_at: string;
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
}

export interface JobListResponse {
  items: JobListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface JobParams {
  q?: string;
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

export async function getJobs(params: JobParams = {}): Promise<JobListResponse> {
  const res = await fetch(`${API}/jobs${buildQuery(params as Record<string, unknown>)}`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

export async function getJob(id: number): Promise<JobDetail> {
  const res = await fetch(`${API}/jobs/${id}`, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error("Job not found");
  return res.json();
}

export async function getCompanies(params: { industry?: string } = {}): Promise<CompanyItem[]> {
  const res = await fetch(`${API}/companies${buildQuery(params)}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error("Failed to fetch companies");
  return res.json();
}

export async function getCompany(id: number): Promise<CompanyDetail> {
  const res = await fetch(`${API}/companies/${id}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error("Company not found");
  return res.json();
}

export async function getMeta(): Promise<Meta> {
  const res = await fetch(`${API}/meta`, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error("Failed to fetch meta");
  return res.json();
}
