import { describe, expect, it } from "vitest";
import type { JobListItem } from "./api";
import { RELEASED, effectiveHides, eligibilityFacts, jobTerm, termLabel } from "./eligibility";

const base = { term_season: "summer", term_year: 2027, degree_levels: ["bachelor", "master"], country: "US" } as unknown as JobListItem;

describe("eligibility display", () => {
  it("labels terms", () => {
    expect(termLabel("summer-2027")).toBe("Summer 2027");
    expect(termLabel("fall")).toBe("Fall");
    expect(jobTerm(base)).toBe("Summer 2027");
    expect(jobTerm({ term_season: null, term_year: null })).toBeNull();
  });

  it("shows only released, stated facts", () => {
    const facts = eligibilityFacts({ ...base, us_citizen_required: true, clearance_required: true } as JobListItem);
    expect(facts.map((f) => f.label)).toEqual(["Term", "Open to", "Country"]);
    expect(facts[1].value).toBe("Bachelor's, Master's");
    expect(facts[2].value).toBe("United States");
    // Unreleased restrictions never render, even when the API sends them.
    expect(RELEASED.citizenship || RELEASED.clearance).toBe(false);
    expect(eligibilityFacts({} as JobListItem)).toEqual([]);
  });

  it("sends no default hides while the restriction fields are unreleased", () => {
    expect(effectiveHides({ level: "intern" })).toEqual({});
    expect(effectiveHides({ level: "intern", hide_citizen_required: "true" })).toEqual({});
  });
});
