/**
 * Static key the web sends on public API fetches so the API can tell a server render from a
 * browser and put it in the shared server-render search bucket (all renders share Vercel's
 * few egress IPs). Mirror of service_key() in api/app/ratelimit.py:
 * HMAC-SHA256(INTERNAL_API_SECRET, label). Constant on purpose, so it does not change the
 * Next.js fetch cache key. Server-side only.
 *
 * Uses Web Crypto (globalThis.crypto.subtle, built into Node 18+ and browsers) instead of
 * node:crypto: client components import "@/lib/api", and a node:crypto import made webpack
 * ship a ~130 kB crypto polyfill to the browser.
 */

const LABEL = "chronicle-ratelimit-exempt-v1";

export const SERVICE_HEADER = "X-Internal-Service";

let cached: { secret: string; key: string } | undefined;

/** The header value, or undefined when no secret is configured (local dev, tests). */
export async function serviceKey(): Promise<string | undefined> {
  const secret = process.env.INTERNAL_API_SECRET;
  if (!secret) return undefined;
  if (cached?.secret === secret) return cached.key;
  const enc = new TextEncoder();
  const k = await globalThis.crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = new Uint8Array(await globalThis.crypto.subtle.sign("HMAC", k, enc.encode(LABEL)));
  const key = Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
  cached = { secret, key };
  return key;
}
