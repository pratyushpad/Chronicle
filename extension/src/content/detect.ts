// Recognize a Greenhouse/Lever/Ashby application page and extract the job identity.
// source_job_id mirrors what the backend ATS adapters store (the id in the URL),
// so a later ingest run upserts the same Job row the extension find-or-creates.
import type { Ats, PageJob } from "../lib/types";

function pageTitle(): string {
  const h1 = document.querySelector("h1");
  const t = (h1?.textContent ?? "").trim();
  if (t) return t;
  // Fall back to the document title, stripped of a trailing " - Company" / " | Board".
  return (document.title || "").split(/[|·]/)[0].trim() || "Role";
}

export function detectJob(): PageJob | null {
  const host = location.hostname;
  const parts = location.pathname.split("/").filter(Boolean);

  // Greenhouse: job-boards|boards.greenhouse.io/{slug}/jobs/{id}
  if (host.endsWith("greenhouse.io")) {
    const jobsIdx = parts.indexOf("jobs");
    if (jobsIdx > 0 && parts[jobsIdx + 1]) {
      return base("greenhouse", parts[0], parts[jobsIdx + 1]);
    }
    return null;
  }

  // Lever: jobs.lever.co/{slug}/{postingId}[/apply]
  if (host.endsWith("lever.co")) {
    if (parts[0] && parts[1]) return base("lever", parts[0], parts[1]);
    return null;
  }

  // Ashby: jobs.ashbyhq.com/{slug}/{jobId}[/application]
  if (host.endsWith("ashbyhq.com")) {
    if (parts[0] && parts[1]) return base("ashby", parts[0], parts[1]);
    return null;
  }

  return null;
}

function base(ats: Ats, slug: string, sourceJobId: string): PageJob {
  const title = pageTitle();
  return {
    ats,
    company_slug: slug,
    company_name: slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    source_job_id: sourceJobId,
    title,
    apply_url: location.href.split("#")[0],
    location: null,
  };
}
