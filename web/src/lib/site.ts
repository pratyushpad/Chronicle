/** Absolute origin of the public site, for canonical URLs, the sitemap and social cards.
 *  NEXT_PUBLIC_SITE_URL overrides it (e.g. a custom domain); otherwise production's. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://chronicles-weld.vercel.app").replace(/\/+$/, "");
