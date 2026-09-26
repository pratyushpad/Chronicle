/**
 * Student filters (PR 4): which extracted fields the site shows, the internship view's
 * default hides, and display labels.
 *
 * RELEASED is set from docs/extraction_eval.md: a field ships only when its held-out
 * precision is at least 0.9 on enough predictions. An unreleased field is neither shown
 * nor filtered on, even though the API sends it.
 */
import type { JobListItem } from "@/lib/api";

// Held-out results (docs/extraction_eval.md, 85 postings): term 0.98, degree levels 0.98,
// country 0.98 ship. Not yet: MS/PhD-only (precision 1.00 but only 6 predictions),
// clearance (1.00, 3 predictions), workplace (0.89), U.S. person (0.75), and citizenship
// (no posting in the set requires it, so it can't be measured). Their filters and toggles
// are built and switch on here once a larger labeled set clears the bar.
export const RELEASED = {
  term: true,
  degree: true,
  gradOnly: false,
  citizenship: false,
  usPerson: false,
  clearance: false,
  workplace: false,
  country: true,
};

export type Restriction = "gradOnly" | "citizenship" | "clearance" | "usPerson";

/** The restrictions the internship view hides by default, each behind a visible toggle. */
export const INTERN_DEFAULT_HIDES: { key: Restriction; param: string; include: string; label: string }[] = [
  { key: "gradOnly", param: "hide_grad_only", include: "include_grad_only", label: "Master's/PhD-only roles" },
  { key: "citizenship", param: "hide_citizen_required", include: "include_citizen_required", label: "U.S. citizens only" },
  { key: "clearance", param: "hide_clearance_required", include: "include_clearance_required", label: "Security clearance required" },
];

export function isInternView(sp: Record<string, string | undefined>): boolean {
  return sp.level === "intern" || sp.experience_level === "Internship";
}

/**
 * Which hide_* params the feed sends. On the internship view each released restriction
 * is hidden unless the reader turned it back on (`include_*=1`); anywhere else only an
 * explicit `hide_*=true` hides.
 */
export function effectiveHides(sp: Record<string, string | undefined>): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  const intern = isInternView(sp);
  for (const h of INTERN_DEFAULT_HIDES) {
    if (!RELEASED[h.key]) continue;
    if ((intern && sp[h.include] !== "1") || sp[h.param] === "true") out[h.param] = true;
  }
  if (RELEASED.usPerson && sp.hide_us_person_required === "true") out.hide_us_person_required = true;
  return out;
}

const SEASON: Record<string, string> = { summer: "Summer", fall: "Fall", spring: "Spring", winter: "Winter" };

/** "summer-2027" → "Summer 2027". */
export function termLabel(term: string): string {
  const [season, year] = term.split("-");
  return [SEASON[season] ?? season, year].filter(Boolean).join(" ");
}

export function jobTerm(job: Pick<JobListItem, "term_season" | "term_year">): string | null {
  if (!RELEASED.term || !job.term_season) return null;
  return [SEASON[job.term_season] ?? job.term_season, job.term_year].filter(Boolean).join(" ");
}

const DEGREE: Record<string, string> = { bachelor: "Bachelor's", master: "Master's", phd: "PhD" };

const REGION = new Intl.DisplayNames(["en"], { type: "region" });
export function countryName(code: string): string {
  try {
    return REGION.of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

const WORKPLACE: Record<string, string> = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" };

/** Released eligibility facts for a job, as short labels (only what the posting states). */
export function eligibilityFacts(job: JobListItem): { label: string; value: string; restrictive?: boolean }[] {
  const facts: { label: string; value: string; restrictive?: boolean }[] = [];
  const term = jobTerm(job);
  if (term) facts.push({ label: "Term", value: term });
  if (RELEASED.workplace && job.workplace_type) facts.push({ label: "Workplace", value: WORKPLACE[job.workplace_type] ?? job.workplace_type });
  const levels = job.degree_levels ?? [];
  if (RELEASED.gradOnly && levels.length > 0 && !levels.includes("bachelor")) {
    facts.push({ label: "Degree", value: "Master's or PhD students", restrictive: true });
  } else if (RELEASED.degree && levels.length > 0) {
    facts.push({ label: "Open to", value: levels.map((l) => DEGREE[l] ?? l).join(", ") });
  }
  if (RELEASED.country && job.country) facts.push({ label: "Country", value: countryName(job.country) });
  if (RELEASED.citizenship && job.us_citizen_required) {
    facts.push({ label: "Eligibility", value: "U.S. citizens only", restrictive: true });
  } else if (RELEASED.usPerson && job.us_person_required) {
    facts.push({ label: "Eligibility", value: "U.S. persons (export control)", restrictive: true });
  }
  if (RELEASED.clearance && job.clearance_required) {
    facts.push({ label: "Clearance", value: "Security clearance required", restrictive: true });
  }
  return facts;
}
