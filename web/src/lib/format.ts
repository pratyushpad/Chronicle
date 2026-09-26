/**
 * Pure display formatters for job facts (pay, ages, dates, department).
 *
 * "Pure" is load-bearing: these run on the server AND during hydration, so they never
 * read the clock (callers pass `now`) and never depend on the runtime's locale or time
 * zone (dates render in UTC with a fixed en-US format). Same input → same string on
 * Node and in every browser, so server HTML and hydration can't disagree.
 *
 * They also never invent data: unknown pay, an unknown pay period, or a missing date
 * renders as nothing (null), not a guess.
 */

export type PayPeriod = "hour" | "day" | "week" | "month" | "year";

/** The pay-related fields a job may carry. Every field is optional: older API
 *  deployments send only the legacy annual `salary_min` / `salary_max`. */
export interface PayFields {
  pay_min?: number | null;
  pay_max?: number | null;
  /** ISO 4217 code, e.g. "USD", "GBP", "CAD". */
  pay_currency?: string | null;
  pay_period?: PayPeriod | null;
  /** Legacy: annualized figures (sorting + old clients). */
  salary_min?: number | null;
  salary_max?: number | null;
}

const PERIOD_SUFFIX: Record<PayPeriod, string> = {
  hour: "hr",
  day: "day",
  week: "wk",
  month: "mo",
  year: "yr",
};

/** Currencies we print with a symbol; any other valid ISO code prints as "CHF 120k…". */
const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$",
  CAD: "CA$",
  AUD: "A$",
  NZD: "NZ$",
  HKD: "HK$",
  SGD: "S$",
  GBP: "£",
  EUR: "€",
  JPY: "¥",
  CNY: "CN¥",
  INR: "₹",
};

// Fixed locale → identical digit grouping on Node and in every browser.
const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const CENTS = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const THOUSANDS = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** A positive, finite amount — or null. Accepts numeric strings defensively, since a
 *  Python Decimal can serialize as "45.00". */
function toAmount(v: unknown): number | null {
  const n = typeof v === "string" && v.trim() !== "" ? Number(v) : v;
  return typeof n === "number" && Number.isFinite(n) && n > 0 ? n : null;
}

function currencyPrefix(code: string | null | undefined): string {
  // No code: the ATS/text extractors only record amounts next to a currency marker,
  // so a missing code means the source printed a bare "$".
  if (code == null || code.trim() === "") return "$";
  const c = code.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(c)) return ""; // unrecognizable → no symbol rather than a wrong one
  return CURRENCY_SYMBOL[c] ?? `${c} `;
}

function hasCents(n: number): boolean {
  return Math.round(n * 100) % 100 !== 0;
}

function formatRange(
  minRaw: unknown,
  maxRaw: unknown,
  currency: string | null | undefined,
  period: PayPeriod,
): string | null {
  const amounts = [toAmount(minRaw), toAmount(maxRaw)].filter((n): n is number => n !== null);
  if (amounts.length === 0) return null;
  const lo = Math.min(...amounts);
  const hi = Math.max(...amounts);

  // Annual figures read as "205k"; everything else prints in full ("8,000", "22.50").
  const inThousands = period === "year" && lo >= 1000;
  const fmt = (n: number) =>
    inThousands ? `${THOUSANDS.format(n / 1000)}k` : (hasCents(n) ? CENTS : WHOLE).format(n);

  const body = fmt(lo) === fmt(hi) ? fmt(lo) : `${fmt(lo)} to ${fmt(hi)}`;
  return `${currencyPrefix(currency)}${body}/${PERIOD_SUFFIX[period]}`;
}

/**
 * Human pay line: "$45 to 55/hr", "$40/hr", "$205k to 300k/yr", "$8,000 to 9,000/mo",
 * "£30 to 35/hr", "CA$90k to 110k/yr", "$22.50/hr". Returns null when nothing honest
 * can be shown.
 *
 * - New API (`pay_period` key present): the structured fields are authoritative. A null
 *   period means the source didn't say (and the amount was ambiguous) → show nothing.
 * - Old API (`pay_period` key absent): only the legacy annual `salary_*` exist; show them
 *   as annual and never back-derive an hourly figure from them.
 */
export function formatPay(p: PayFields): string | null {
  if (p.pay_period !== undefined) {
    const period = p.pay_period;
    if (!period || !(period in PERIOD_SUFFIX)) return null;
    return formatRange(p.pay_min, p.pay_max, p.pay_currency, period);
  }
  return formatRange(p.salary_min, p.salary_max, "USD", "year");
}

// ─── Dates ────────────────────────────────────────────────────────────────────────

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Parse an API timestamp to epoch ms, or null. Timestamps without an offset are UTC
 *  (never the runtime's local zone), and >3 fractional digits are trimmed for engines
 *  that reject microseconds. */
export function parseTimestamp(iso: string | null | undefined): number | null {
  if (!iso || typeof iso !== "string") return null;
  let s = iso.trim().replace(/(\.\d{3})\d+/, "$1");
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s += "T00:00:00Z";
  else if (/T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) s += "Z";
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : t;
}

/**
 * Compact age: "just now", "12m ago", "3h ago", "3d ago", "2w ago", "4mo ago", "2y ago".
 * Floors at every unit (a role 6d 23h old is "6d ago"). A timestamp slightly in the
 * future (clock skew) reads "just now"; one more than a day ahead is nonsense and
 * returns null rather than a made-up age.
 */
export function relativeAge(iso: string | null | undefined, now: number): string | null {
  const t = parseTimestamp(iso);
  if (t === null || !Number.isFinite(now)) return null;
  const diff = now - t;
  if (diff < 0) return diff > -DAY ? "just now" : null;
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  const days = Math.floor(diff / DAY);
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

const ABSOLUTE = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

/** "Sep 22, 2026" (UTC, so server and browser agree), or null. */
export function formatAbsoluteDate(iso: string | null | undefined): string | null {
  const t = parseTimestamp(iso);
  return t === null ? null : ABSOLUTE.format(t);
}

export interface JobAge {
  /** Which date we're showing: the source's own posting date, or when Chronicle first saw it. */
  kind: "posted" | "first_seen";
  /** The timestamp shown (for <time dateTime>). */
  iso: string;
  /** "3d ago" — null only for a far-future timestamp. */
  relative: string | null;
  /** "Sep 22, 2026". */
  absolute: string;
  /** Full accessible label: "Posted Sep 22, 2026" / "First seen by Chronicle Sep 22, 2026". */
  label: string;
}

/**
 * Which date a job card should show. `posted_at` is trusted only when it's no later than
 * a day after Chronicle first saw the role — a role can't be published after we already
 * saw it live, so a later `posted_at` is a re-publish/update stamp, not the posting date.
 * Otherwise we say plainly that the date is when Chronicle first saw it.
 */
export function jobAge(
  job: { posted_at?: string | null; first_seen_at?: string | null },
  now: number,
): JobAge | null {
  const first = parseTimestamp(job.first_seen_at);
  const posted = parseTimestamp(job.posted_at);

  if (job.posted_at && posted !== null && (first === null || posted <= first + DAY)) {
    const absolute = ABSOLUTE.format(posted);
    return {
      kind: "posted",
      iso: job.posted_at,
      relative: relativeAge(job.posted_at, now),
      absolute,
      label: `Posted ${absolute}`,
    };
  }
  if (job.first_seen_at && first !== null) {
    const absolute = ABSOLUTE.format(first);
    return {
      kind: "first_seen",
      iso: job.first_seen_at,
      relative: relativeAge(job.first_seen_at, now),
      absolute,
      label: `First seen by Chronicle ${absolute}`,
    };
  }
  return null;
}

// ─── Freshness ────────────────────────────────────────────────────────────────────

const COUNT = new Intl.NumberFormat("en-US");

/**
 * "412 of 596 company boards re-checked in the last 7 days" from /meta's freshness block,
 * or null when the block is absent (pre-PR-1 API) or inconsistent — callers then use
 * number-free copy. Every number comes from the API; nothing here assumes a cadence.
 */
export function boardsRechecked(
  f: { boards_active: number; boards_checked_7d: number } | null | undefined,
): string | null {
  if (!f) return null;
  const { boards_active: active, boards_checked_7d: checked } = f;
  if (!Number.isInteger(active) || !Number.isInteger(checked)) return null;
  if (active <= 0 || checked < 0 || checked > active) return null;
  const subject =
    checked === active ? `All ${COUNT.format(active)}` : `${COUNT.format(checked)} of ${COUNT.format(active)}`;
  return `${subject} company boards re-checked in the last 7 days`;
}

// ─── Department ───────────────────────────────────────────────────────────────────

/** Department label to display, or "" — never a chip for the "Other" catch-all or null. */
export function displayDepartment(raw: string | null | undefined): string {
  const s = raw?.trim() ?? "";
  return s.toLowerCase() === "other" ? "" : s;
}
