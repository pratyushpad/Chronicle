import { describe, expect, it } from "vitest";
import type { JobDetail } from "./api";
import { employmentType, jobPostingJsonLd, postalAddress, serializeJsonLd } from "./jobPosting";

// Field values from the real Zipline posting in the replica (greenhouse:flyzipline).
const job: JobDetail = {
  id: 73,
  title: "Embedded Engineering Intern (Summer 2027)",
  company_name: "Zipline",
  company_id: 9,
  company_industry: null,
  location_raw: "South San Francisco, California, United States",
  location_normalized: "south san francisco, california, usa",
  remote: null,
  department: "Hardware",
  employment_type: null,
  experience_level: "Internship",
  pay_min: 54,
  pay_max: 54,
  pay_currency: "USD",
  pay_period: "hour",
  posted_at: "2026-08-26T17:00:00Z",
  first_seen_at: "2026-09-26T19:50:00Z",
  last_seen_at: "2026-09-26T19:50:00Z",
  is_active: true,
  apply_url: "https://boards.greenhouse.io/flyzipline/jobs/1",
  is_new: false,
  description_text: "About Zipline\nZipline is the world’s largest drone delivery service.",
};

describe("jobPostingJsonLd", () => {
  it("includes only known fields", () => {
    const ld = jobPostingJsonLd(job, "https://c.test/jobs/73", job.description_text!)!;
    expect(ld).toMatchObject({
      "@type": "JobPosting",
      title: job.title,
      datePosted: "2026-08-26T17:00:00.000Z",
      hiringOrganization: { "@type": "Organization", name: "Zipline" },
      employmentType: "INTERN",
      jobLocation: {
        "@type": "Place",
        address: { "@type": "PostalAddress", addressLocality: "South San Francisco", addressRegion: "CA", addressCountry: "US" },
      },
      baseSalary: { "@type": "MonetaryAmount", currency: "USD", value: { "@type": "QuantitativeValue", unitText: "HOUR", value: 54 } },
    });
    expect(ld).not.toHaveProperty("validThrough");
    expect(ld).not.toHaveProperty("jobLocationType");
  });

  it("is omitted when the posting date is unknown", () => {
    expect(jobPostingJsonLd({ ...job, posted_at: null }, "u", "d")).toBeNull();
    // A posted_at after Chronicle first saw the role is an update stamp, not a posting date.
    expect(jobPostingJsonLd({ ...job, posted_at: "2026-09-29T00:00:00Z" }, "u", "d")).toBeNull();
  });

  it("is omitted for closed roles and empty descriptions", () => {
    expect(jobPostingJsonLd({ ...job, is_active: false }, "u", "d")).toBeNull();
    expect(jobPostingJsonLd(job, "u", "  ")).toBeNull();
  });

  it("leaves pay out when the period or currency is unknown", () => {
    expect(jobPostingJsonLd({ ...job, pay_period: null }, "u", "d")).not.toHaveProperty("baseSalary");
    expect(jobPostingJsonLd({ ...job, pay_currency: null }, "u", "d")).not.toHaveProperty("baseSalary");
    const range = jobPostingJsonLd({ ...job, pay_min: 45, pay_max: 55 }, "u", "d")!;
    expect(range.baseSalary).toMatchObject({ value: { minValue: 45, maxValue: 55 } });
  });
});

describe("postalAddress", () => {
  it("parses US city/state and refuses what it can't parse", () => {
    expect(postalAddress("austin, tx, usa")).toMatchObject({ addressLocality: "Austin", addressRegion: "TX" });
    expect(postalAddress("london")).toEqual({ "@type": "PostalAddress", addressLocality: "London" });
    expect(postalAddress("toronto, on, canada")).toBeNull();
    expect(postalAddress("georgia, tbilisi")).toBeNull();
    expect(postalAddress("seattle, washington")).toMatchObject({ addressRegion: "WA", addressCountry: "US" });
    expect(postalAddress("remote")).toBeNull();
    expect(postalAddress("new york, ny; san francisco, ca")).toBeNull();
    expect(postalAddress(null)).toBeNull();
  });
});

describe("employmentType", () => {
  it("maps what the posting says, else nothing", () => {
    expect(employmentType({ experience_level: "Internship", employment_type: null })).toBe("INTERN");
    expect(employmentType({ experience_level: null, employment_type: "Full-time" })).toBe("FULL_TIME");
    expect(employmentType({ experience_level: null, employment_type: "FullTime" })).toBe("FULL_TIME");
    expect(employmentType({ experience_level: null, employment_type: "Contract" })).toBe("CONTRACTOR");
    expect(employmentType({ experience_level: null, employment_type: null })).toBeNull();
    expect(employmentType({ experience_level: null, employment_type: "Hybrid" })).toBeNull();
  });
});

describe("serializeJsonLd", () => {
  it("can't be closed by posting text", () => {
    const out = serializeJsonLd({ description: "</script><script>alert(1)</script> & \u2028" });
    expect(out).not.toContain("<");
    expect(out).not.toContain(">");
    expect(JSON.parse(out).description).toBe("</script><script>alert(1)</script> & \u2028");
  });
});
