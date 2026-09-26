import { describe, expect, it } from "vitest";
import type { CompanyItem } from "./api";
import { queryCompanies } from "./companies";

const co = (id: number, name: string, industry: string | null, roles: number): CompanyItem => ({
  id, name, industry, active_job_count: roles, ats: "greenhouse", careers_url: null,
});
// Names and canonical industries from the registry; role counts illustrative.
const ALL = [
  co(1, "Anduril", "Aerospace & Defense", 900),
  co(2, "Stripe", "Fintech", 300),
  co(3, "Ramp", "Fintech", 120),
  co(4, "Zipline", "Robotics & Autonomy", 80),
  co(5, "Closed Co", "Fintech", 0),
  co(6, "Unlabeled", null, 5),
];

describe("queryCompanies", () => {
  it("lists hiring companies, most roles first", () => {
    const r = queryCompanies(ALL, {});
    expect(r.items.map((c) => c.name)).toEqual(["Anduril", "Stripe", "Ramp", "Zipline", "Unlabeled"]);
    expect(r.total).toBe(5);
    expect(queryCompanies(ALL, { q: "ramp" }).hiring).toBe(5);
  });

  it("searches names case-insensitively and filters by industry", () => {
    expect(queryCompanies(ALL, { q: "RAM" }).items.map((c) => c.name)).toEqual(["Ramp"]);
    expect(queryCompanies(ALL, { industry: "fintech" }).items.map((c) => c.name)).toEqual(["Stripe", "Ramp"]);
  });

  it("sorts by name and pages, clamping out-of-range pages", () => {
    const r = queryCompanies(ALL, { sort: "name", pageSize: 2, page: 2 });
    expect(r.items.map((c) => c.name)).toEqual(["Stripe", "Unlabeled"]);
    expect(r.totalPages).toBe(3);
    expect(queryCompanies(ALL, { pageSize: 2, page: 99 }).page).toBe(3);
    expect(queryCompanies(ALL, { pageSize: 2, page: -1 }).page).toBe(1);
  });

  it("counts industries among hiring companies only", () => {
    expect(queryCompanies(ALL, {}).industries).toEqual([
      { name: "Aerospace & Defense", companies: 1, roles: 900 },
      { name: "Fintech", companies: 2, roles: 420 },
      { name: "Robotics & Autonomy", companies: 1, roles: 80 },
    ]);
  });
});
