import type { CompanyItem } from "@/lib/api";

export type CompanySort = "roles" | "name";

export interface CompanyQuery {
  q?: string;
  industry?: string;
  sort?: CompanySort;
  page?: number;
  pageSize?: number;
}

export interface CompanyPage {
  items: CompanyItem[];
  total: number;
  page: number;
  totalPages: number;
  /** Companies with at least one open role, before search and filters. */
  hiring: number;
  /** Industries among companies with open roles, most roles first (for the chips). */
  industries: { name: string; companies: number; roles: number }[];
}

/**
 * Search, filter, sort and page the company list. Pure, so the page stays a server
 * component with plain links and a GET form (works without JavaScript). The list is
 * small (~600 companies), so doing this on the Next server costs nothing.
 */
export function queryCompanies(all: CompanyItem[], query: CompanyQuery): CompanyPage {
  const pageSize = Math.max(1, query.pageSize ?? 30);
  const hiring = all.filter((c) => c.active_job_count > 0);

  const byIndustry = new Map<string, { companies: number; roles: number }>();
  for (const c of hiring) {
    if (!c.industry) continue;
    const e = byIndustry.get(c.industry) ?? { companies: 0, roles: 0 };
    e.companies += 1;
    e.roles += c.active_job_count;
    byIndustry.set(c.industry, e);
  }
  const industries = Array.from(byIndustry, ([name, v]) => ({ name, ...v })).sort(
    (a, b) => b.roles - a.roles || a.name.localeCompare(b.name),
  );

  const q = (query.q ?? "").trim().toLowerCase();
  const industry = (query.industry ?? "").trim().toLowerCase();
  let items = hiring.filter(
    (c) =>
      (!q || c.name.toLowerCase().includes(q)) &&
      (!industry || (c.industry ?? "").toLowerCase() === industry),
  );
  items =
    query.sort === "name"
      ? items.sort((a, b) => a.name.localeCompare(b.name))
      : items.sort((a, b) => b.active_job_count - a.active_job_count || a.name.localeCompare(b.name));

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.min(Math.max(1, Math.floor(query.page ?? 1)), totalPages);
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize),
    total,
    page,
    totalPages,
    hiring: hiring.length,
    industries,
  };
}
