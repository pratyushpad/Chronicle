import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";
import { JOB_CHUNKS } from "./sitemap";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Signed-in and API routes: personal, and never useful in search results.
      disallow: ["/api/", "/tracker", "/saved", "/settings", "/onboarding", "/for-you"],
    },
    sitemap: Array.from({ length: JOB_CHUNKS + 1 }, (_, id) => `${SITE_URL}/sitemap/${id}.xml`),
  };
}
