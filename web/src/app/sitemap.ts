import type { MetadataRoute } from "next";
import { getCompanies, getSitemapJobs } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

// Sitemap 0 holds the static pages and companies. Per-role job URLs are no longer listed:
// crawlers walking ~36k job pages exhausted the hosting plan's CPU in Oct 2026, so job
// pages are disallowed in robots.ts and JOB_CHUNKS is 0. Raise it again only with
// edge-cached job pages and a usage alert in place.
export const JOB_CHUNK_SIZE = 2_000; // the API caps /sitemap/jobs at 2,000 ids per call
export const JOB_CHUNKS = 0;
export const revalidate = 86400; // a day; getSitemapJobs uses the same window

export async function generateSitemaps() {
  return Array.from({ length: JOB_CHUNKS + 1 }, (_, id) => ({ id }));
}

export default async function sitemap({ id }: { id: number }): Promise<MetadataRoute.Sitemap> {
  if (Number(id) === 0) {
    const pages: MetadataRoute.Sitemap = [
      { url: `${SITE_URL}/`, changeFrequency: "daily", priority: 1 },
      { url: `${SITE_URL}/jobs`, changeFrequency: "hourly", priority: 0.9 },
      { url: `${SITE_URL}/companies`, changeFrequency: "daily", priority: 0.7 },
    ];
    const companies = await getCompanies().catch(() => []);
    return pages.concat(
      companies
        .filter((c) => c.active_job_count > 0)
        .map((c) => ({ url: `${SITE_URL}/companies/${c.id}`, changeFrequency: "daily" as const, priority: 0.6 })),
    );
  }
  const offset = (Number(id) - 1) * JOB_CHUNK_SIZE;
  const page = await getSitemapJobs(offset, JOB_CHUNK_SIZE).catch(() => null);
  if (!page) return [];
  // No lastModified: the only per-role timestamp that moves is last_seen_at, which
  // changes on every ingest and would make every URL look modified every time.
  return page.items.map((j) => ({
    url: `${SITE_URL}/jobs/${j.id}`,
    changeFrequency: "daily" as const,
    priority: 0.8,
  }));
}
