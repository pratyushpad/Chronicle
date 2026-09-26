/**
 * schema.org JobPosting structured data for a job page, built from known fields only.
 *
 * Never invents data: a field the API doesn't know is left out. `datePosted` is required
 * by search engines, so when the posting date is unknown (we only know when Chronicle
 * first saw the role) there is no JobPosting at all. Closed roles get none either.
 */
import type { JobDetail } from "@/lib/api";
import { jobAge, parseTimestamp, type PayPeriod } from "@/lib/format";
import { formatLocation } from "@/lib/utils";

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

const UNIT: Record<PayPeriod, string> = {
  hour: "HOUR",
  day: "DAY",
  week: "WEEK",
  month: "MONTH",
  year: "YEAR",
};

const US_STATES = new Set([
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY",
  "LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND",
  "OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
]);

/** Employment type from what the posting says. Unknown → omitted. */
export function employmentType(job: Pick<JobDetail, "employment_type" | "experience_level">): string | null {
  if ((job.experience_level ?? "").toLowerCase() === "internship") return "INTERN";
  const t = (job.employment_type ?? "").toLowerCase().replace(/[\s_-]+/g, "");
  if (!t) return null;
  if (t.includes("intern")) return "INTERN";
  if (t.includes("fulltime") || t === "permanent") return "FULL_TIME";
  if (t.includes("parttime")) return "PART_TIME";
  if (t.includes("contract")) return "CONTRACTOR";
  if (t.includes("temp")) return "TEMPORARY";
  return null;
}

const STATE_NAMES: Record<string, string> = {
  alabama: "AL", alaska: "AK", arizona: "AZ", arkansas: "AR", california: "CA", colorado: "CO",
  connecticut: "CT", delaware: "DE", florida: "FL", georgia: "GA", hawaii: "HI", idaho: "ID",
  illinois: "IL", indiana: "IN", iowa: "IA", kansas: "KS", kentucky: "KY", louisiana: "LA",
  maine: "ME", maryland: "MD", massachusetts: "MA", michigan: "MI", minnesota: "MN",
  mississippi: "MS", missouri: "MO", montana: "MT", nebraska: "NE", nevada: "NV",
  "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
  "north carolina": "NC", "north dakota": "ND", ohio: "OH", oklahoma: "OK", oregon: "OR",
  pennsylvania: "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
  tennessee: "TN", texas: "TX", utah: "UT", vermont: "VT", virginia: "VA", washington: "WA",
  "west virginia": "WV", wisconsin: "WI", wyoming: "WY", "district of columbia": "DC",
};

function usState(part: string | undefined): string | null {
  if (!part) return null;
  const p = part.trim();
  if (US_STATES.has(p.toUpperCase())) return p.toUpperCase();
  return STATE_NAMES[p.toLowerCase()] ?? null;
}

/** "Austin, TX" / "South San Francisco, California, USA" → a US PostalAddress; a bare
 *  city → locality only; anything else → null (not parsed, so not claimed). */
export function postalAddress(locationNormalized: string | null | undefined): Record<string, Json> | null {
  const loc = formatLocation(locationNormalized);
  if (!loc || /remote/i.test(loc) || /[;|/]/.test(loc)) return null;
  const parts = loc.split(",").map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return null;
  const address: Record<string, Json> = { "@type": "PostalAddress", addressLocality: parts[0] };
  if (parts.length === 1) return address;
  const state = usState(parts[1]);
  const country = parts[2]?.toUpperCase();
  if (!state || parts.length > 3 || (country && country !== "USA" && country !== "US")) return null;
  address.addressRegion = state;
  address.addressCountry = "US";
  return address;
}

function baseSalary(job: JobDetail): Record<string, Json> | null {
  const period = job.pay_period;
  const lo = typeof job.pay_min === "number" && job.pay_min > 0 ? job.pay_min : null;
  const hi = typeof job.pay_max === "number" && job.pay_max > 0 ? job.pay_max : null;
  const currency = (job.pay_currency ?? "").trim().toUpperCase();
  if (!period || !(period in UNIT) || (lo === null && hi === null) || !/^[A-Z]{3}$/.test(currency)) {
    return null;
  }
  const value: Record<string, Json> = { "@type": "QuantitativeValue", unitText: UNIT[period] };
  if (lo !== null && hi !== null && lo !== hi) {
    value.minValue = Math.min(lo, hi);
    value.maxValue = Math.max(lo, hi);
  } else {
    value.value = (lo ?? hi) as number;
  }
  return { "@type": "MonetaryAmount", currency, value };
}

export function jobPostingJsonLd(job: JobDetail, url: string, description: string): Record<string, Json> | null {
  if (job.is_active === false) return null;
  const age = jobAge(job, Date.now());
  if (!age || age.kind !== "posted" || parseTimestamp(age.iso) === null) return null;
  if (!description.trim()) return null;

  const data: Record<string, Json> = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: job.title,
    description,
    datePosted: new Date(parseTimestamp(age.iso) as number).toISOString(),
    hiringOrganization: { "@type": "Organization", name: job.company_name },
    url,
    directApply: false,
  };
  const type = employmentType(job);
  if (type) data.employmentType = type;
  const address = postalAddress(job.location_normalized);
  if (address) data.jobLocation = { "@type": "Place", address };
  if (job.remote === true) data.jobLocationType = "TELECOMMUTE";
  const salary = baseSalary(job);
  if (salary) data.baseSalary = salary;
  return data;
}

/** JSON for an inline <script type="application/ld+json">: `<`, `>`, `&` and the JS line
 *  separators are escaped, so no posting text can close the script tag. */
export function serializeJsonLd(data: unknown): string {
  return JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
