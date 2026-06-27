import Link from "next/link";
import { getCompanies, getMeta } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";
import { formatNumber } from "@/lib/utils";

const INDUSTRY_COLORS: Record<string, string> = {
  "AI/ML": "bg-purple-50 text-purple-700 border-purple-200",
  "FinTech": "bg-green-50 text-green-700 border-green-200",
  "Developer Tools": "bg-blue-50 text-blue-700 border-blue-200",
  "Security": "bg-red-50 text-red-700 border-red-200",
  "Data": "bg-amber-50 text-amber-700 border-amber-200",
  "Analytics": "bg-orange-50 text-orange-700 border-orange-200",
  "Database": "bg-indigo-50 text-indigo-700 border-indigo-200",
  "Marketing": "bg-pink-50 text-pink-700 border-pink-200",
  "HR Tech": "bg-teal-50 text-teal-700 border-teal-200",
  "Sales Tech": "bg-cyan-50 text-cyan-700 border-cyan-200",
};

function industryClass(industry: string | null) {
  if (!industry) return "bg-muted text-muted-foreground border-border";
  return INDUSTRY_COLORS[industry] ?? "bg-muted text-muted-foreground border-border";
}

export default async function CompaniesPage() {
  const [companies, meta] = await Promise.all([
    getCompanies().catch(() => []),
    getMeta().catch(() => null),
  ]);

  const industries = Array.from(new Set(companies.map((c) => c.industry).filter(Boolean))).sort() as string[];

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <SectionLabel className="mb-8">Companies</SectionLabel>

      <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-4xl text-foreground">
            {companies.length} companies
          </h1>
          {meta && (
            <p className="mt-1 font-body text-muted-foreground">
              {formatNumber(meta.total_active_jobs)} open roles across {industries.length} industries
            </p>
          )}
        </div>
        <Link
          href="/jobs"
          className="inline-flex min-h-[44px] items-center justify-center rounded-md bg-accent px-6 font-body text-sm font-medium text-white shadow-sm hover:-translate-y-0.5 hover:shadow-md transition-all duration-200"
        >
          Browse All Roles
        </Link>
      </div>

      {/* Industry filter pills */}
      <div className="mb-8 flex flex-wrap gap-2">
        <Link
          href="/companies"
          className="font-mono text-xs border border-accent text-accent px-3 py-1.5 rounded-full transition-colors hover:bg-accent hover:text-white"
        >
          All
        </Link>
        {industries.map((ind) => (
          <Link
            key={ind}
            href={`/jobs?industry=${encodeURIComponent(ind)}`}
            className={`font-mono text-xs border px-3 py-1.5 rounded-full transition-colors hover:opacity-80 ${industryClass(ind)}`}
          >
            {ind}
          </Link>
        ))}
      </div>

      {/* Company grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {companies
          .filter((c) => c.active_job_count > 0)
          .sort((a, b) => b.active_job_count - a.active_job_count)
          .map((company) => (
            <Link
              key={company.id}
              href={`/companies/${company.id}`}
              className="group rounded-lg border border-border bg-card p-5 shadow-sm transition-all duration-200 hover:shadow-md hover:border-accent/30"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-body text-base font-semibold text-foreground group-hover:text-accent transition-colors">
                  {company.name}
                </h2>
                <span className="font-display text-xl text-accent shrink-0">
                  {formatNumber(company.active_job_count)}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                {company.industry && (
                  <span className={`font-mono text-[10px] uppercase tracking-[0.1em] border px-2 py-0.5 rounded ${industryClass(company.industry)}`}>
                    {company.industry}
                  </span>
                )}
                <span className="font-mono text-[10px] text-muted-foreground uppercase">
                  {company.ats}
                </span>
              </div>
              <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                {formatNumber(company.active_job_count)} open role{company.active_job_count !== 1 ? "s" : ""} →
              </p>
            </Link>
          ))}
      </div>
    </main>
  );
}
