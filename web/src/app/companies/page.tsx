import Link from "next/link";
import { getCompanies, getMeta } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";
import { formatNumber } from "@/lib/utils";

export default async function CompaniesPage() {
  const [companies, meta] = await Promise.all([
    getCompanies().catch(() => []),
    getMeta().catch(() => null),
  ]);

  const industries = Array.from(new Set(companies.map((c) => c.industry).filter(Boolean))).sort() as string[];

  return (
    <main id="main" className="mx-auto max-w-6xl px-6 py-12 md:px-8 lg:px-12">
      <SectionLabel className="mb-8">Companies</SectionLabel>

      <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-5xl font-medium tracking-tight text-foreground md:text-7xl">
            {companies.length} companies
          </h1>
          {meta && (
            <p className="mt-2 font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground">
              {formatNumber(meta.total_active_jobs)} open roles · {industries.length} industries
            </p>
          )}
        </div>
        <Link
          href="/jobs"
          className="inline-flex h-12 items-center justify-center gap-3 border-2 border-foreground bg-foreground px-6 font-mono text-xs font-medium uppercase tracking-[0.15em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px]"
        >
          Browse All Roles <span aria-hidden>→</span>
        </Link>
      </div>

      {/* Industry filter pills */}
      <div className="mb-10 flex flex-wrap gap-2">
        <Link
          href="/companies"
          className="border border-foreground bg-foreground px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground"
        >
          All
        </Link>
        {industries.map((ind) => (
          <Link
            key={ind}
            href={`/jobs?industry=${encodeURIComponent(ind)}`}
            className="border border-foreground px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background"
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
              className="group border border-foreground border-l-4 bg-card p-5 transition-colors duration-100 hover:bg-muted focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:-outline-offset-[3px]"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-display text-lg font-medium text-foreground underline-offset-4 group-hover:underline">
                  {company.name}
                </h2>
                <span className="shrink-0 font-display text-2xl font-medium text-foreground">
                  {formatNumber(company.active_job_count)}
                </span>
              </div>
              <div className="mt-3 flex items-center gap-2">
                {company.industry && (
                  <span className="border border-foreground px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] text-foreground">
                    {company.industry}
                  </span>
                )}
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                  {company.ats}
                </span>
              </div>
              <p className="mt-3 border-t border-border-light pt-3 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
                {formatNumber(company.active_job_count)} open role{company.active_job_count !== 1 ? "s" : ""} →
              </p>
            </Link>
          ))}
      </div>
    </main>
  );
}
