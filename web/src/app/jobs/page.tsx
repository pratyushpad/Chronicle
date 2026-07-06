import { Suspense } from "react";
import { getJobs, getMeta, getCompanies } from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { FilterBar } from "@/components/FilterBar";
import { SectionLabel } from "@/components/SectionLabel";
import { Pagination } from "@/components/Pagination";
import { JobListSkeleton } from "@/components/JobCardSkeleton";
import { formatNumber } from "@/lib/utils";

interface PageProps {
  searchParams: Promise<Record<string, string>>;
}

async function JobFeed({ searchParams }: { searchParams: Record<string, string> }) {
  const page = parseInt(searchParams.page ?? "1", 10);
  const params = {
    q: searchParams.q,
    mode:
      searchParams.q && ["semantic", "hybrid"].includes(searchParams.mode)
        ? (searchParams.mode as "semantic" | "hybrid")
        : undefined,
    company: searchParams.company,
    company_id: searchParams.company_id ? parseInt(searchParams.company_id, 10) : undefined,
    department: searchParams.department,
    location: searchParams.location,
    employment_type: searchParams.employment_type,
    experience_level: searchParams.experience_level,
    level: searchParams.level,
    industry: searchParams.industry,
    remote: searchParams.remote === "true" ? true : undefined,
    since_last_run: searchParams.since_last_run === "true" ? true : undefined,
    page,
    page_size: 20,
  };

  const [data, meta, companies] = await Promise.all([
    getJobs(params),
    getMeta(),
    getCompanies(),
  ]);

  const filterParams: Record<string, string> = {};
  for (const [k, v] of Object.entries(searchParams)) {
    if (k !== "page" && v) filterParams[k] = v;
  }

  return (
    <div>
      <FilterBar
        departments={meta.departments}
        locations={meta.locations}
        employmentTypes={meta.employment_types}
        experienceLevels={meta.experience_levels ?? []}
        industries={meta.industries ?? []}
        companies={companies.map((c) => ({ id: c.id, name: c.name }))}
        selectedCompanyName={
          searchParams.company ??
          (searchParams.company_id
            ? companies.find((c) => c.id === parseInt(searchParams.company_id, 10))?.name
            : undefined)
        }
      />

      <div className="mt-6 flex items-center justify-between">
        <p className="font-body text-sm text-muted-foreground">
          {formatNumber(data.total)} role{data.total !== 1 ? "s" : ""}
          {data.search_mode && (
            <span className="ml-2 border border-foreground px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-foreground">
              {data.search_mode} match
            </span>
          )}
        </p>
        {meta.last_run?.started_at && (
          <p className="font-mono text-xs text-muted-foreground tracking-[0.05em]">
            Updated{" "}
            {new Intl.DateTimeFormat("en-US", {
              month: "short",
              day: "numeric",
              hour: "numeric",
              minute: "2-digit",
            }).format(new Date(meta.last_run.started_at))}
          </p>
        )}
      </div>

      {data.items.length === 0 ? (
        <div className="py-24 text-center">
          <p className="font-display text-2xl text-muted-foreground">No roles found</p>
          <p className="mt-2 font-body text-sm text-muted-foreground">Try adjusting your filters</p>
        </div>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          {data.items.map((job) => (
            <JobCard key={job.id} job={job} surface="search" />
          ))}
        </div>
      )}

      <Pagination
        page={data.page}
        totalPages={data.total_pages}
        basePath="/jobs"
        searchParams={filterParams}
      />
    </div>
  );
}

export default async function JobsPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  return (
    <main id="main" className="mx-auto max-w-6xl px-6 py-12 md:px-8 lg:px-12">
      <SectionLabel className="mb-6">Open Roles</SectionLabel>

      <Suspense fallback={<JobListSkeleton />}>
        <JobFeed searchParams={sp} />
      </Suspense>
    </main>
  );
}
