import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getJob, getJobs, getSimilarJobs, type JobDetail } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";
import { JobCard } from "@/components/JobCard";
import { JobCardSkeleton } from "@/components/JobCardSkeleton";
import { JobDescription } from "@/components/JobDescription";
import { formatDepartment, formatLocation } from "@/lib/utils";
import { formatAbsoluteDate, formatPay, jobAge, relativeAge } from "@/lib/format";
import { descriptionBlocks, summarize } from "@/lib/description";
import { jobPostingJsonLd, serializeJsonLd } from "@/lib/jobPosting";
import { SITE_URL } from "@/lib/site";

interface PageProps {
  params: Promise<{ id: string }>;
}

async function loadJob(params: PageProps["params"]): Promise<JobDetail> {
  const { id } = await params;
  const jobId = Number(id);
  if (!Number.isInteger(jobId) || jobId <= 0) notFound();
  try {
    return await getJob(jobId);
  } catch (e) {
    // Only a real 404 is "not found". A cold start, timeout or 5xx must surface as an
    // error (a 5xx), never as a not-found page that tells crawlers to drop a live role.
    if (e instanceof Error && e.message === "Job not found") notFound();
    throw e;
  }
}

function summaryOf(job: JobDetail): string {
  return (
    job.description_summary ??
    summarize(job.description_text) ??
    `${job.title} at ${job.company_name}${job.location_normalized ? `, ${formatLocation(job.location_normalized)}` : ""}.`
  );
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const job = await loadJob(params);
  const title = `${job.title} at ${job.company_name}`;
  const description = summaryOf(job);
  const url = `/jobs/${job.id}`;
  return {
    title,
    description,
    alternates: { canonical: url },
    // A closed role stays reachable for people who saved it, but isn't offered to search.
    robots: job.is_active === false ? { index: false, follow: true } : undefined,
    openGraph: { title, description, url, type: "website", siteName: "Chronicle" },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function JobDetailPage({ params }: PageProps) {
  const job = await loadJob(params);

  // One render time for every relative label on this page (server-rendered, not hydrated).
  const now = Date.now();
  const closed = job.is_active === false;
  const department = formatDepartment(job.department); // "" for the "Other" catch-all
  const location = formatLocation(job.location_normalized);
  const pay = formatPay(job);
  const age = jobAge(job, now);
  const seenLive = relativeAge(job.last_seen_at, now);
  const blocks = descriptionBlocks(job);
  const jsonLd = jobPostingJsonLd(job, `${SITE_URL}/jobs/${job.id}`, job.description_text ?? "");

  const glance: { label: string; value: string }[] = [
    pay ? { label: "Pay", value: pay } : null,
    location || job.remote
      ? { label: "Location", value: [location, job.remote === true ? "Remote" : null].filter(Boolean).join(" · ") }
      : null,
    job.experience_level ? { label: "Level", value: job.experience_level } : null,
    job.employment_type ? { label: "Type", value: job.employment_type } : null,
    department ? { label: "Team", value: department } : null,
    job.company_industry ? { label: "Industry", value: job.company_industry } : null,
    age ? { label: age.kind === "posted" ? "Posted" : "First seen", value: age.absolute } : null,
  ].filter((x): x is { label: string; value: string } => x !== null);

  return (
    <main id="main" className="mx-auto max-w-6xl px-4 pb-32 pt-10 sm:px-6 lg:pb-20 lg:pt-16">
      {jsonLd && (
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }} />
      )}
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <Link href="/jobs" className="font-body text-sm text-muted-foreground hover:text-foreground">
          ← All roles
        </Link>
        <Link href={`/companies/${job.company_id}`} className="font-body text-sm text-muted-foreground hover:text-foreground">
          {job.company_name} →
        </Link>
      </nav>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-14">
        <article className="min-w-0">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
            {job.company_name}
          </p>
          <h1 className="mt-3 font-display text-3xl leading-[1.2] text-foreground sm:text-4xl">{job.title}</h1>

          {closed && (
            <div role="note" className="mt-6 border border-foreground bg-muted px-4 py-3 font-body text-sm text-foreground">
              <strong className="font-semibold">This role is closed.</strong>{" "}
              {seenLive
                ? `Chronicle last saw it live on ${job.company_name}'s board ${seenLive}.`
                : `It is no longer on ${job.company_name}'s board.`}
            </div>
          )}

          {glance.length > 0 && (
            <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-4 border-y border-border-light py-5 sm:grid-cols-3">
              {glance.map((g) => (
                <div key={g.label} className="min-w-0">
                  <dt className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{g.label}</dt>
                  <dd className="mt-1 break-words font-body text-sm text-foreground">{g.value}</dd>
                </div>
              ))}
            </dl>
          )}

          <section aria-label="Job description" className="mt-6">
            {blocks.length > 0 ? (
              <JobDescription blocks={blocks} />
            ) : (
              <p className="font-body italic text-muted-foreground">
                The posting has no description. The full details are on {job.company_name}&rsquo;s site.
              </p>
            )}
          </section>
        </article>

        {/* Desktop: sticky right rail. Mobile gets the fixed bottom bar below. */}
        <aside className="hidden lg:block">
          <div className="sticky top-24 border border-foreground bg-card p-6">
            <ApplyPanel job={job} closed={closed} pay={pay} age={age} seenLive={seenLive} />
          </div>
        </aside>
      </div>

      <Suspense fallback={<RelatedSkeleton label="Similar roles" />}>
        <SimilarRoles jobId={job.id} now={now} />
      </Suspense>
      <Suspense fallback={<RelatedSkeleton label={`More at ${job.company_name}`} />}>
        <MoreAtCompany job={job} now={now} />
      </Suspense>

      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-foreground bg-background/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-6xl items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-body text-sm text-foreground">{closed ? "Closed" : pay ?? job.company_name}</p>
            {seenLive && (
              <p className="truncate font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
                {closed ? "Last seen" : "Verified"} {seenLive}
              </p>
            )}
          </div>
          <ApplyLink job={job} closed={closed} className="shrink-0 px-5" />
        </div>
      </div>
    </main>
  );
}

function ApplyLink({ job, closed, className = "" }: { job: JobDetail; closed: boolean; className?: string }) {
  if (closed) {
    return (
      <a
        href={job.apply_url}
        target="_blank"
        rel="noopener noreferrer"
        className={`inline-flex min-h-[44px] items-center justify-center border border-foreground font-body text-sm text-foreground hover:bg-muted ${className}`}
      >
        Original posting
      </a>
    );
  }
  return (
    <a
      href={job.apply_url}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex min-h-[44px] items-center justify-center bg-accent font-body text-sm font-medium tracking-wide text-accent-foreground transition-colors hover:bg-foreground/85 ${className}`}
    >
      Apply on {job.company_name}&rsquo;s site<span aria-hidden>&nbsp;→</span>
    </a>
  );
}

function ApplyPanel({
  job,
  closed,
  pay,
  age,
  seenLive,
}: {
  job: JobDetail;
  closed: boolean;
  pay: string | null;
  age: ReturnType<typeof jobAge>;
  seenLive: string | null;
}) {
  return (
    <>
      {pay && <p className="font-display text-2xl text-foreground">{pay}</p>}
      <ApplyLink job={job} closed={closed} className="mt-4 w-full px-4" />
      <dl className="mt-5 space-y-2 font-body text-sm">
        {age && (
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{age.kind === "posted" ? "Posted" : "First seen"}</dt>
            <dd className="text-right text-foreground">
              <time dateTime={age.iso}>{age.relative ?? age.absolute}</time>
            </dd>
          </div>
        )}
        {seenLive && (
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{closed ? "Last seen live" : "Verified live"}</dt>
            <dd className="text-right text-foreground">
              <time dateTime={job.last_seen_at} title={formatAbsoluteDate(job.last_seen_at) ?? undefined}>
                {seenLive}
              </time>
            </dd>
          </div>
        )}
      </dl>
      <p className="mt-4 font-body text-xs leading-relaxed text-muted-foreground">
        {age?.kind === "first_seen"
          ? `${job.company_name}'s board doesn't publish a posting date, so this is when Chronicle first saw the role. `
          : ""}
        &ldquo;Verified&rdquo; is the last time Chronicle saw this role on {job.company_name}&rsquo;s own board.
      </p>
    </>
  );
}

async function SimilarRoles({ jobId, now }: { jobId: number; now: number }) {
  const similar = await getSimilarJobs(jobId, 4);
  if (similar.length === 0) return null;
  return (
    <section className="mt-20" aria-labelledby="similar-roles">
      <SectionLabel className="mb-8">
        <span id="similar-roles">Similar roles</span>
      </SectionLabel>
      <div className="grid gap-4 md:grid-cols-2">
        {similar.map((j) => (
          <JobCard key={j.id} job={j} now={now} />
        ))}
      </div>
    </section>
  );
}

async function MoreAtCompany({ job, now }: { job: JobDetail; now: number }) {
  let related: Awaited<ReturnType<typeof getJobs>> | null = null;
  try {
    related = await getJobs({ company_id: job.company_id, page_size: 5 });
  } catch {
    return null; // non-critical
  }
  // The feed collapses a role's duplicates into one card whose id may differ from this
  // page's, so match on the title too: never offer the role you're already reading.
  const others = related.items.filter((j) => j.id !== job.id && j.title !== job.title).slice(0, 4);
  if (others.length === 0) return null;
  return (
    <section className="mt-20" aria-labelledby="more-at-company">
      <SectionLabel className="mb-8">
        <span id="more-at-company">More at {job.company_name}</span>
      </SectionLabel>
      <div className="grid gap-4 md:grid-cols-2">
        {others.map((j) => (
          <JobCard key={j.id} job={j} now={now} />
        ))}
      </div>
      {related.total > others.length + 1 && (
        <Link
          href={`/companies/${job.company_id}`}
          className="mt-6 inline-block font-body text-sm text-foreground underline underline-offset-4 hover:text-muted-foreground"
        >
          All {related.total} roles at {job.company_name} →
        </Link>
      )}
    </section>
  );
}

function RelatedSkeleton({ label }: { label: string }) {
  return (
    <section className="mt-20" aria-busy="true" aria-label={`Loading ${label.toLowerCase()}`}>
      <SectionLabel className="mb-8">{label}</SectionLabel>
      <div className="grid gap-4 md:grid-cols-2">
        <JobCardSkeleton />
        <JobCardSkeleton />
      </div>
    </section>
  );
}
