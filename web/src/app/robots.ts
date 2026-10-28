import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";
import { JOB_CHUNKS } from "./sitemap";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Signed-in and API routes: personal, and never useful in search results.
      // /jobs/ (one page per role) is disallowed: crawler traffic on those pages paused
      // the whole hosting account in Oct 2026. The /jobs list page stays crawlable.
      // Query strings are disallowed too: /jobs?q=...&mode=hybrid runs a search during the
      // server render, and ?page= on /jobs and /companies/[id] makes an uncached render per
      // value. The plain /jobs, /companies and /companies/[id] pages stay crawlable.
      disallow: [
        "/api/",
        "/jobs/",
        "/jobs?",
        "/companies?",
        "/*?*page=",
        "/*?*q=",
        "/tracker",
        "/saved",
        "/settings",
        "/onboarding",
        "/for-you",
      ],
    },
    sitemap: Array.from({ length: JOB_CHUNKS + 1 }, (_, id) => `${SITE_URL}/sitemap/${id}.xml`),
  };
}
