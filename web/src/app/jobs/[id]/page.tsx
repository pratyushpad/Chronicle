import Link from "next/link";
import { notFound } from "next/navigation";
import { getJob, getJobs, JobListItem } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";
import { JobCard } from "@/components/JobCard";
import { formatDepartment, formatLocation } from "@/lib/utils";
import { formatPay, jobAge, relativeAge } from "@/lib/format";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function JobDetailPage({ params }: PageProps) {
  const { id } = await params;
  const jobId = parseInt(id, 10);

  if (isNaN(jobId)) notFound();

  let job;
  try {
    job = await getJob(jobId);
  } catch {
    notFound();
  }

  // Related jobs from same company (exclude current)
  let related: JobListItem[] = [];
  try {
    const relatedData = await getJobs({
      company: job.company_name,
      page_size: 4,
    });
    related = relatedData.items.filter((j) => j.id !== job.id).slice(0, 3);
  } catch {
    // Non-critical
  }

  // One render time for every relative label on this page (server-rendered, not hydrated).
  const now = Date.now();
  const department = formatDepartment(job.department); // "" for the "Other" catch-all
  const pay = formatPay(job);
  const age = jobAge(job, now);
  const seenLive = relativeAge(job.last_seen_at, now);

  const metaTags = [
    job.company_name,
    formatLocation(job.location_normalized) || null,
    job.remote === true ? "Remote" : null,
    job.experience_level ?? null,
    job.employment_type ?? null,
    department || null,
    job.company_industry ?? null,
  ].filter(Boolean) as string[];

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      {/* Back */}
      <div className="flex items-center gap-4">
        <Link href="/jobs" className="font-body text-sm text-muted-foreground hover:text-accent">
          ← All Roles
        </Link>
        <Link href={`/companies/${job.company_id}`} className="font-body text-sm text-muted-foreground hover:text-accent">
          {job.company_name} →
        </Link>
      </div>

      <div className="mt-8">
        <SectionLabel className="mb-6">{department || job.company_name}</SectionLabel>

        {/* Title */}
        <h1 className="font-display text-4xl leading-[1.2] text-foreground">
          {job.title}
        </h1>

        {/* Meta tags */}
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1">
          {metaTags.map((tag, i) => (
            <span
              key={i}
              className="font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>

        {pay && (
          <p className="mt-3 font-mono text-xs tracking-[0.05em] text-foreground">{pay}</p>
        )}

        {(age || seenLive) && (
          <p className="mt-2 font-body text-sm text-muted-foreground">
            {age && (
              <time dateTime={age.iso}>
                {age.label}
                {age.relative && <> ({age.relative})</>}
              </time>
            )}
            {age && seenLive && <span aria-hidden> · </span>}
            {seenLive && (
              <time
                dateTime={job.last_seen_at}
                title="The last time Chronicle saw this role live on the company's board"
              >
                {job.is_active === false ? "Last seen live" : "Verified"} {seenLive}
                <span className="sr-only">
                  {" "}
                  — the last time Chronicle saw this role live on the company&rsquo;s board
                </span>
              </time>
            )}
          </p>
        )}

        {/* Rule */}
        <div className="my-8 border-t border-border" />

        {/* Description */}
        {job.description_text ? (
          <div className="whitespace-pre-line break-words font-body text-base leading-[1.75] text-foreground">
            {job.description_text}
          </div>
        ) : (
          <p className="font-body text-muted-foreground italic">
            No description available.
          </p>
        )}

        {/* Apply CTA */}
        <div className="mt-10">
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[44px] items-center justify-center rounded-md bg-accent px-8 font-body text-sm font-medium tracking-wide text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-accent-secondary hover:shadow-md active:translate-y-0"
          >
            Apply Now →
          </a>
        </div>
      </div>

      {/* Related jobs */}
      {related.length > 0 && (
        <div className="mt-20">
          <SectionLabel className="mb-8">More at {job.company_name}</SectionLabel>
          <div className="flex flex-col gap-4">
            {related.map((j) => (
              <JobCard key={j.id} job={j} now={now} />
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
