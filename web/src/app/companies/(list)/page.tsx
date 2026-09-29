import Link from "next/link";
import type { Metadata } from "next";
import { getCompanies, getMeta } from "@/lib/api";
import { Pagination } from "@/components/Pagination";
import { cn, formatNumber } from "@/lib/utils";
import { queryCompanies, type CompanySort } from "@/lib/companies";

export const metadata: Metadata = {
  title: "Companies",
  description: "Every company Chronicle reads, with open roles pulled from its own careers board.",
};

interface Props {
  searchParams: Promise<Record<string, string>>;
}

export default async function CompaniesPage({ searchParams }: Props) {
  const sp = await searchParams;
  // A failed fetch is an error page, never "0 companies".
  const [companies, meta] = await Promise.all([getCompanies(), getMeta().catch(() => null)]);
  const sort: CompanySort = sp.sort === "name" ? "name" : "roles";
  const result = queryCompanies(companies, {
    q: sp.q,
    industry: sp.industry,
    sort,
    page: Number(sp.page) || 1,
    pageSize: 30,
  });
  const linkParams = (patch: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    const merged = { q: sp.q, industry: sp.industry, sort: sp.sort, ...patch };
    for (const [k, v] of Object.entries(merged)) if (v) p.set(k, v);
    const qs = p.toString();
    return qs ? `/companies?${qs}` : "/companies";
  };
  const chip = (active: boolean) =>
    cn(
      "inline-flex min-h-[36px] items-center gap-2 border px-3 font-sans text-sm transition-colors",
      active ? "border-foreground bg-foreground text-background" : "border-border-light text-foreground hover:border-input hover:bg-muted",
    );

  return (
    <main id="main" className="mx-auto max-w-6xl px-6 py-10 md:px-8 lg:px-12">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl text-foreground md:text-4xl">Companies</h1>
          <p className="mt-2 font-sans text-sm text-muted-foreground">
            {formatNumber(result.hiring)} hiring now
            {meta && <> · {formatNumber(meta.total_active_jobs)} open roles · {formatNumber(meta.total_companies)} companies read</>}
          </p>
        </div>
      </div>

      <form action="/companies" method="get" role="search" className="mt-6 flex flex-col gap-3 sm:flex-row">
        <label htmlFor="company-search" className="sr-only">
          Search companies
        </label>
        <input
          id="company-search"
          type="search"
          name="q"
          defaultValue={sp.q ?? ""}
          placeholder="Search companies"
          className="h-11 w-full min-w-0 border border-input sm:flex-1 bg-background px-3 font-sans text-sm text-foreground placeholder:text-muted-foreground focus:border-foreground focus:outline-none"
        />
        {sp.industry && <input type="hidden" name="industry" value={sp.industry} />}
        {sp.sort && <input type="hidden" name="sort" value={sp.sort} />}
        <button
          type="submit"
          className="h-11 shrink-0 bg-accent px-5 font-sans text-sm font-medium text-accent-foreground hover:bg-accent-secondary"
        >
          Search
        </button>
      </form>

      <nav aria-label="Industries" className="mt-5 flex flex-wrap gap-2">
        <Link href={linkParams({ industry: undefined })} className={chip(!sp.industry)} aria-current={!sp.industry ? "page" : undefined}>
          All industries
        </Link>
        {result.industries.map((ind) => {
          const active = (sp.industry ?? "").toLowerCase() === ind.name.toLowerCase();
          return (
            <Link
              key={ind.name}
              href={linkParams({ industry: active ? undefined : ind.name })}
              className={chip(active)}
              aria-current={active ? "page" : undefined}
            >
              {ind.name}
              <span className={active ? "text-background/70" : "text-muted-foreground"}>{ind.companies}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-b border-border-light pb-3">
        <p className="font-sans text-sm text-muted-foreground">
          {formatNumber(result.total)} {result.total === 1 ? "company" : "companies"}
          {sp.q && <> matching &ldquo;{sp.q}&rdquo;</>}
        </p>
        <p className="flex items-center gap-3 font-sans text-sm">
          <span className="text-muted-foreground">Sort:</span>
          <Link href={linkParams({ sort: undefined })} aria-current={sort === "roles" ? "true" : undefined} className={sort === "roles" ? "text-foreground underline underline-offset-4" : "text-muted-foreground hover:text-foreground"}>
            Most roles
          </Link>
          <Link href={linkParams({ sort: "name" })} aria-current={sort === "name" ? "true" : undefined} className={sort === "name" ? "text-foreground underline underline-offset-4" : "text-muted-foreground hover:text-foreground"}>
            A to Z
          </Link>
        </p>
      </div>

      {result.items.length === 0 ? (
        <p className="py-20 text-center font-sans text-sm text-muted-foreground">
          No companies match. <Link href="/companies" className="text-foreground underline underline-offset-4">Show all</Link>
        </p>
      ) : (
        <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {result.items.map((company) => (
            <li key={company.id}>
              <Link
                href={`/companies/${company.id}`}
                className="group flex h-full flex-col border border-border-light bg-card p-5 transition-colors duration-100 hover:bg-muted focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:-outline-offset-[3px]"
              >
                <div className="flex items-start justify-between gap-3">
                  <h2 className="min-w-0 break-words font-display text-lg text-foreground underline-offset-4 group-hover:underline">
                    {company.name}
                  </h2>
                  <span className="shrink-0 font-sans text-sm font-medium text-foreground">
                    {formatNumber(company.active_job_count)}
                    <span className="font-normal text-muted-foreground"> open</span>
                  </span>
                </div>
                {company.industry && (
                  <p className="mt-2 font-sans text-xs text-muted-foreground">{company.industry}</p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}

      <Pagination
        page={result.page}
        totalPages={result.totalPages}
        basePath="/companies"
        searchParams={Object.fromEntries(
          Object.entries({ q: sp.q, industry: sp.industry, sort: sp.sort }).filter(([, v]) => v) as [string, string][],
        )}
      />
    </main>
  );
}
