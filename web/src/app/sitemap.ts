import type { MetadataRoute } from "next";
import { getCompanies, getSitemapJobs } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

// Sitemap 0 holds the static pages and companies; 1..JOB_CHUNKS hold one URL per distinct
// active role (the API's /sitemap/jobs, paged by id). A fixed chunk count keeps the
// sitemap ids and robots.txt identical at build and at request time; 3 × 20,000 covers
// the corpus with room to spare (about 45k rows, fewer distinct roles), and an empty
// chunk is a valid, empty sitemap.
export const JOB_CHUNK_SIZE = 20_000;
export const JOB_CHUNKS = 3;
export const revalidate = 3600;

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
  return page.items.map((j) => ({
    url: `${SITE_URL}/jobs/${j.id}`,
    lastModified: j.last_seen_at,
    changeFrequency: "daily" as const,
    priority: 0.8,
  }));
}
