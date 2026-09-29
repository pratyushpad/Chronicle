import { Suspense } from "react";
import Link from "next/link";
import { getJobs, getMeta, type Meta } from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { FilterBar } from "@/components/FilterBar";
import { Pagination } from "@/components/Pagination";
import { JobListSkeleton } from "@/components/JobCardSkeleton";
import { formatNumber } from "@/lib/utils";
import { boardsRechecked, relativeAge } from "@/lib/format";
import { RELEASED, effectiveHides, validCountry, validTerm } from "@/lib/eligibility";

interface PageProps {
  searchParams: Promise<Record<string, string>>;
}

async function JobFeed({ searchParams }: { searchParams: Record<string, string> }) {
  const compact = searchParams.density === "compact";
  const parsedPage = parseInt(searchParams.page ?? "1", 10);
  const page = Number.isFinite(parsedPage) && parsedPage >= 1 ? parsedPage : 1;
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
    sort: ["newest", "relevance", "pay"].includes(searchParams.sort) ? searchParams.sort : undefined,
    ...effectiveHides(searchParams),
    term: RELEASED.term ? validTerm(searchParams.term) : undefined,
    workplace: RELEASED.workplace ? searchParams.workplace : undefined,
    country: RELEASED.country ? validCountry(searchParams.country) : undefined,
    page,
    page_size: compact ? 40 : 20,
  };

  // No company list here any more: the old FilterBar fetched all ~600 companies on the
  // server for one <select>, which sat on the feed's critical path (LCP).
  const [data, meta] = await Promise.all([getJobs(params), getMeta().catch(() => null)]);

  const filterParams: Record<string, string> = {};
  for (const [k, v] of Object.entries(searchParams)) {
    if (k !== "page" && v) filterParams[k] = v;
  }

  // One render time for every "3d ago" on the page, passed to the (client) cards so the
  // server HTML and hydration produce the same text.
  const now = Date.now();
  // Freshness is stated, never promised: how many boards were actually re-checked
  // (from /meta), or — on an API without that block — when the last sync started.
  const lastSync = relativeAge(meta?.last_run?.started_at, now);
  const freshnessNote =
    boardsRechecked(meta?.freshness) ?? (lastSync ? `Last sync started ${lastSync}` : null);
  // Filtered to one company by id (from a company page): name it, with a way out.
  const companyName = searchParams.company_id ? data.items[0]?.company_name : undefined;

  return (
    <div>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p className="font-sans text-sm text-muted-foreground">
          {formatNumber(data.total)} role{data.total !== 1 ? "s" : ""}
          {companyName && (
            <>
              {" "}at {companyName}{" "}
              <Link
                href={(() => {
                  const p = new URLSearchParams(filterParams);
                  p.delete("company_id");
                  const qs = p.toString();
                  return qs ? `/jobs?${qs}` : "/jobs";
                })()}
                className="text-foreground underline underline-offset-4 hover:text-muted-foreground"
              >
                (all companies)
              </Link>
            </>
          )}
          {data.search_mode && (
            <span className="ml-2 border border-input px-1.5 py-0.5 font-sans text-[11px] uppercase tracking-[0.08em] text-foreground">
              {data.search_mode} match
            </span>
          )}
        </p>
        {freshnessNote && (
          <p className="font-sans text-xs text-muted-foreground tracking-[0.05em]">
            {freshnessNote}
          </p>
        )}
      </div>

      {data.items.length === 0 ? (
        <div className="mt-6 border-y border-border-light py-24 text-center">
          <p className="font-display text-3xl text-foreground">No roles found</p>
          <p className="mt-3 font-sans text-sm text-muted-foreground">
            Try adjusting or clearing your filters.
          </p>
        </div>
      ) : (
        <div className={compact ? "mt-4 flex flex-col gap-2" : "mt-6 flex flex-col gap-4"}>
          {data.items.map((job) => (
            // No entrance animation: cards start hidden until the keyframe plays, which
            // held back LCP (a card title) by ~0.9 s on a throttled phone.
            <div key={job.id}>
              <JobCard job={job} surface="search" now={now} density={compact ? "compact" : "comfortable"} />
            </div>
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

async function Filters() {
  const meta: Meta | null = await getMeta().catch(() => null);
  return (
    <FilterBar
      departments={meta?.departments ?? []}
      locations={meta?.locations ?? []}
      employmentTypes={meta?.employment_types ?? []}
      industries={meta?.industries ?? []}
      terms={meta?.terms ?? []}
      countries={meta?.countries ?? []}
    />
  );
}

export default async function JobsPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  // Filters render outside the feed's Suspense boundary, so typing in the search box
  // never swaps it for a skeleton (and never loses focus) while results load. They get
  // their own boundary, so /meta never holds up the first streamed HTML either.
  return (
    <main id="main" className="mx-auto max-w-6xl px-6 py-10 md:px-8 lg:px-12">
      <h1 className="mb-6 font-display text-3xl text-foreground md:text-4xl">Open roles</h1>
      <Suspense fallback={<FilterBar departments={[]} locations={[]} employmentTypes={[]} industries={[]} terms={[]} countries={[]} />}>
        <Filters />
      </Suspense>
      <Suspense fallback={<JobListSkeleton />}>
        <JobFeed searchParams={sp} />
      </Suspense>
    </main>
  );
}
