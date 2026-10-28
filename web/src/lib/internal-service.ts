/**
 * Static key the web sends on public API fetches so the API can tell a server render from a
 * browser and skip the per-IP search limit (all renders share Vercel's few egress IPs).
 * Mirror of service_key() in api/app/ratelimit.py: HMAC-SHA256(INTERNAL_API_SECRET, label).
 * Constant on purpose, so it does not change the Next.js fetch cache key. Server-side only.
 */

import { createHmac } from "crypto";

const LABEL = "chronicle-ratelimit-exempt-v1";

export const SERVICE_HEADER = "X-Internal-Service";

/** The header value, or undefined when no secret is configured (local dev, tests). */
export function serviceKey(): string | undefined {
  const secret = process.env.INTERNAL_API_SECRET;
  if (!secret) return undefined;
  return createHmac("sha256", secret).update(LABEL, "utf8").digest("hex");
}
