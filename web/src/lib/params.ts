/**
 * Clamp URL query values to what the API accepts, so a crafted or overlong query string
 * renders a normal page instead of an API 422 surfacing as an error page.
 * Keep in step with api/app/routers/jobs.py (_MAX_TEXT, _MAX_PAGE).
 */
export const MAX_TEXT = 200;
export const MAX_PAGE = 500;

export function clampPage(raw: string | undefined): number {
  const n = parseInt(raw ?? "1", 10);
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.min(n, MAX_PAGE);
}

export function clampText(raw: string | undefined): string | undefined {
  if (raw === undefined) return undefined;
  const clean = raw.replace(/\u0000/g, "").slice(0, MAX_TEXT);
  return clean === "" ? undefined : clean;
}

// Postgres integer ids: anything outside 1..2^31-1, or not plain digits, cannot exist, so the
// job page 404s on it before any API call.
const MAX_JOB_ID = 2147483647;

export function parseJobId(id: string): number | null {
  if (!/^[1-9][0-9]{0,9}$/.test(id)) return null;
  const n = Number(id);
  return n <= MAX_JOB_ID ? n : null;
}
