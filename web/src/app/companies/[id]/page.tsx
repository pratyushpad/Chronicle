import Link from "next/link";
import { notFound } from "next/navigation";
import { getCompany, getCompanyVelocity, getJobs, type CompanyVelocity } from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { SectionLabel } from "@/components/SectionLabel";
import { HiringVelocity } from "@/components/HiringVelocity";
import { Pagination } from "@/components/Pagination";
import { formatNumber, formatDate } from "@/lib/utils";

interface Props {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string>>;
}

export default async function CompanyPage({ params, searchParams }: Props) {
  const { id } = await params;
  const sp = await searchParams;
  const page = parseInt(sp.page ?? "1", 10);

  let company, jobs;
  try {
    [company, jobs] = await Promise.all([
      getCompany(parseInt(id, 10)),
      getJobs({ company_id: parseInt(id, 10), page, page_size: 20 }),
    ]);
  } catch {
    notFound();
  }

  // Velocity is a progressive enhancement — never fail the page if it errors.
  let velocity: CompanyVelocity | null = null;
  try {
    velocity = await getCompanyVelocity(parseInt(id, 10));
  } catch {
    velocity = null;
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <Link href="/companies" className="font-body text-sm text-muted-foreground hover:text-foreground">
        ← All Companies
      </Link>

      <div className="mt-6 mb-10">
        <SectionLabel className="mb-4">{company.industry ?? "Company"}</SectionLabel>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-4xl text-foreground">{company.name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <span className="font-mono text-xs text-muted-foreground uppercase tracking-[0.1em]">
                {company.ats}
              </span>
              {company.last_ingested_at && (
                <span className="font-mono text-xs text-muted-foreground">
                  Updated {formatDate(company.last_ingested_at)}
                </span>
              )}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="font-display text-5xl text-accent">{formatNumber(company.active_job_count)}</div>
            <div className="font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground">open roles</div>
          </div>
        </div>

        <div className="mt-6 flex gap-3">
          <Link
            href={`/jobs?company_id=${company.id}`}
            className="inline-flex min-h-[44px] items-center justify-center rounded-md bg-accent px-6 font-body text-sm font-medium text-white shadow-sm hover:-translate-y-0.5 hover:shadow-md transition-all duration-200"
          >
            Browse All {company.name} Roles
          </Link>
          {company.careers_url && (
            <a
              href={company.careers_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-[44px] items-center justify-center rounded-md border border-border px-6 font-body text-sm text-muted-foreground hover:border-accent hover:text-accent transition-all duration-200"
            >
              Careers Page →
            </a>
          )}
        </div>
      </div>

      <div className="border-t border-border" />

      {velocity && (velocity.active_now > 0 || velocity.weeks.some((w) => w.opened || w.closed)) && (
        <div className="mt-8">
          <HiringVelocity data={velocity} />
        </div>
      )}

      <div className="border-t border-border" />

      <div className="mt-8">
        <SectionLabel className="mb-6">Open Roles</SectionLabel>
        <p className="mb-4 font-body text-sm text-muted-foreground">
          Showing {jobs.items.length} of {formatNumber(jobs.total)} roles
        </p>
        <div className="flex flex-col gap-4">
          {jobs.items.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
        {jobs.total_pages > 1 && (
          <div className="mt-8">
            <Pagination
              page={jobs.page}
              totalPages={jobs.total_pages}
              basePath={`/companies/${id}`}
            />
          </div>
        )}
      </div>
    </main>
  );
}
