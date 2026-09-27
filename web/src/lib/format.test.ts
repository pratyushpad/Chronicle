import { describe, expect, it } from "vitest";
import {
  boardsRechecked,
  displayDepartment,
  formatAbsoluteDate,
  formatPay,
  jobAge,
  parseTimestamp,
  relativeAge,
} from "./format";

describe("formatPay — new API (pay_period present)", () => {
  it("hourly range", () => {
    expect(formatPay({ pay_min: 45, pay_max: 55, pay_currency: "USD", pay_period: "hour" })).toBe(
      "$45 to 55/hr",
    );
  });

  it("single hourly value (min only, max only, or min === max)", () => {
    expect(formatPay({ pay_min: 40, pay_max: null, pay_currency: "USD", pay_period: "hour" })).toBe("$40/hr");
    expect(formatPay({ pay_min: null, pay_max: 40, pay_currency: "USD", pay_period: "hour" })).toBe("$40/hr");
    expect(formatPay({ pay_min: 40, pay_max: 40, pay_currency: "USD", pay_period: "hour" })).toBe("$40/hr");
  });

  it("annual range in thousands", () => {
    expect(
      formatPay({ pay_min: 205000, pay_max: 300000, pay_currency: "USD", pay_period: "year" }),
    ).toBe("$205k to 300k/yr");
  });

  it("annual non-round thousands keep one decimal", () => {
    expect(
      formatPay({ pay_min: 124000, pay_max: 195500, pay_currency: "USD", pay_period: "year" }),
    ).toBe("$124k to 195.5k/yr");
  });

  it("monthly prints full grouped amounts", () => {
    expect(formatPay({ pay_min: 8000, pay_max: 9000, pay_currency: "USD", pay_period: "month" })).toBe(
      "$8,000 to 9,000/mo",
    );
  });

  it("weekly and daily", () => {
    expect(formatPay({ pay_min: 1500, pay_max: null, pay_currency: "USD", pay_period: "week" })).toBe("$1,500/wk");
    expect(formatPay({ pay_min: 400, pay_max: 500, pay_currency: "USD", pay_period: "day" })).toBe("$400 to 500/day");
  });

  it("non-USD currencies show their symbol or code", () => {
    expect(formatPay({ pay_min: 30, pay_max: 35, pay_currency: "GBP", pay_period: "hour" })).toBe("£30 to 35/hr");
    expect(formatPay({ pay_min: 90000, pay_max: 110000, pay_currency: "CAD", pay_period: "year" })).toBe(
      "CA$90k to 110k/yr",
    );
    expect(formatPay({ pay_min: 50000, pay_max: 60000, pay_currency: "EUR", pay_period: "year" })).toBe(
      "€50k to 60k/yr",
    );
    expect(formatPay({ pay_min: 120000, pay_max: 150000, pay_currency: "CHF", pay_period: "year" })).toBe(
      "CHF 120k to 150k/yr",
    );
    expect(formatPay({ pay_min: 30, pay_max: 35, pay_currency: "gbp", pay_period: "hour" })).toBe("£30 to 35/hr");
  });

  it("no decimals unless the amount has cents", () => {
    expect(formatPay({ pay_min: 22.5, pay_max: null, pay_currency: "USD", pay_period: "hour" })).toBe("$22.50/hr");
    expect(formatPay({ pay_min: 22.5, pay_max: 30, pay_currency: "USD", pay_period: "hour" })).toBe(
      "$22.50 to 30/hr",
    );
    expect(formatPay({ pay_min: 45.0, pay_max: 55.0, pay_currency: "USD", pay_period: "hour" })).toBe(
      "$45 to 55/hr",
    );
  });

  it("accepts Decimal-as-string amounts", () => {
    expect(
      formatPay({
        pay_min: "45.00" as unknown as number,
        pay_max: "55.50" as unknown as number,
        pay_currency: "USD",
        pay_period: "hour",
      }),
    ).toBe("$45 to 55.50/hr");
  });

  it("orders a reversed range", () => {
    expect(formatPay({ pay_min: 55, pay_max: 45, pay_currency: "USD", pay_period: "hour" })).toBe("$45 to 55/hr");
  });

  it("missing currency means the source printed a bare $", () => {
    expect(formatPay({ pay_min: 45, pay_max: 55, pay_currency: null, pay_period: "hour" })).toBe("$45 to 55/hr");
  });

  it("shows nothing when the period is unknown, even if legacy salary exists", () => {
    expect(
      formatPay({
        pay_min: 45,
        pay_max: 55,
        pay_currency: "USD",
        pay_period: null,
        salary_min: 45000,
        salary_max: 55000,
      }),
    ).toBeNull();
  });

  it("shows nothing when there are no usable amounts", () => {
    expect(formatPay({ pay_min: null, pay_max: null, pay_currency: "USD", pay_period: "hour" })).toBeNull();
    expect(formatPay({ pay_min: 0, pay_max: -5, pay_currency: "USD", pay_period: "hour" })).toBeNull();
    expect(formatPay({ pay_min: NaN, pay_max: Infinity, pay_currency: "USD", pay_period: "year" })).toBeNull();
  });

  it("ignores a period outside the vocabulary", () => {
    expect(
      formatPay({ pay_min: 45, pay_max: 55, pay_currency: "USD", pay_period: "biweekly" as never }),
    ).toBeNull();
  });
});

describe("formatPay — old API fallback (pay_period absent)", () => {
  it("shows legacy values as annual only", () => {
    expect(formatPay({ salary_min: 120000, salary_max: 150000 })).toBe("$120k to 150k/yr");
    expect(formatPay({ salary_min: 70000, salary_max: 70000 })).toBe("$70k/yr");
    expect(formatPay({ salary_min: 70000, salary_max: null })).toBe("$70k/yr");
  });

  it("never derives an hourly figure from legacy values", () => {
    // The old parser stored "$30 — $45" as 30000/45000; we show what's stored, as annual.
    const out = formatPay({ salary_min: 30000, salary_max: 45000 });
    expect(out).toBe("$30k to 45k/yr");
    expect(out).not.toMatch(/hr/);
  });

  it("shows nothing when neither structured nor legacy pay exists", () => {
    expect(formatPay({})).toBeNull();
    expect(formatPay({ salary_min: null, salary_max: null })).toBeNull();
  });
});

describe("relativeAge", () => {
  const now = Date.parse("2026-09-25T12:00:00Z");
  const ago = (ms: number) => new Date(now - ms).toISOString();
  const MIN = 60_000;
  const HR = 60 * MIN;
  const DAY = 24 * HR;

  it("units from minutes to years", () => {
    expect(relativeAge(ago(30 * 1000), now)).toBe("just now");
    expect(relativeAge(ago(12 * MIN), now)).toBe("12m ago");
    expect(relativeAge(ago(3 * HR), now)).toBe("3h ago");
    expect(relativeAge(ago(3 * DAY), now)).toBe("3d ago");
    expect(relativeAge(ago(14 * DAY), now)).toBe("2w ago");
    expect(relativeAge(ago(125 * DAY), now)).toBe("4mo ago");
    expect(relativeAge(ago(800 * DAY), now)).toBe("2y ago");
  });

  it("boundaries floor to the smaller unit until the next one is complete", () => {
    expect(relativeAge(ago(59 * MIN), now)).toBe("59m ago");
    expect(relativeAge(ago(60 * MIN), now)).toBe("1h ago");
    expect(relativeAge(ago(DAY - 1), now)).toBe("23h ago");
    expect(relativeAge(ago(DAY), now)).toBe("1d ago");
    expect(relativeAge(ago(7 * DAY - 1), now)).toBe("6d ago");
    expect(relativeAge(ago(7 * DAY), now)).toBe("1w ago");
    expect(relativeAge(ago(29 * DAY), now)).toBe("4w ago");
    expect(relativeAge(ago(30 * DAY), now)).toBe("1mo ago");
    expect(relativeAge(ago(364 * DAY), now)).toBe("12mo ago");
    expect(relativeAge(ago(365 * DAY), now)).toBe("1y ago");
  });

  it("future timestamps: small skew is 'just now', far future is unknown", () => {
    expect(relativeAge(new Date(now + 5 * MIN).toISOString(), now)).toBe("just now");
    expect(relativeAge(new Date(now + 3 * DAY).toISOString(), now)).toBeNull();
  });

  it("null, empty and invalid input", () => {
    expect(relativeAge(null, now)).toBeNull();
    expect(relativeAge(undefined, now)).toBeNull();
    expect(relativeAge("", now)).toBeNull();
    expect(relativeAge("not a date", now)).toBeNull();
    expect(relativeAge(ago(DAY), NaN)).toBeNull();
  });

  it("parses the API's microsecond UTC timestamps and offset-less ones as UTC", () => {
    expect(relativeAge("2026-09-25T09:00:00.015033Z", now)).toBe("2h ago");
    expect(relativeAge("2026-09-25T09:00:00", now)).toBe("3h ago");
    expect(parseTimestamp("2026-09-25T09:00:00")).toBe(Date.parse("2026-09-25T09:00:00Z"));
    expect(parseTimestamp("2026-09-25")).toBe(Date.parse("2026-09-25T00:00:00Z"));
    expect(parseTimestamp("2026-09-25T09:00:00+02:00")).toBe(Date.parse("2026-09-25T07:00:00Z"));
  });
});

describe("formatAbsoluteDate", () => {
  it("formats in UTC regardless of the runtime zone", () => {
    expect(formatAbsoluteDate("2026-09-22T23:30:00Z")).toBe("Sep 22, 2026");
    expect(formatAbsoluteDate("2026-09-23T00:30:00+02:00")).toBe("Sep 22, 2026");
    expect(formatAbsoluteDate(null)).toBeNull();
    expect(formatAbsoluteDate("garbage")).toBeNull();
  });
});

describe("jobAge", () => {
  const now = Date.parse("2026-09-25T12:00:00Z");

  it("uses posted_at when it is no later than a day after first seen", () => {
    const age = jobAge({ posted_at: "2026-09-22T10:00:00Z", first_seen_at: "2026-09-22T11:00:00Z" }, now);
    expect(age).toEqual({
      kind: "posted",
      iso: "2026-09-22T10:00:00Z",
      relative: "3d ago",
      absolute: "Sep 22, 2026",
      label: "Posted Sep 22, 2026",
    });
    // Published up to a day after we first saw it (feed lag) still counts as posted.
    expect(
      jobAge({ posted_at: "2026-09-24T23:46:06Z", first_seen_at: "2026-09-24T00:01:17.015033Z" }, now)?.kind,
    ).toBe("posted");
  });

  it("falls back to first seen when posted_at is a later re-publish stamp", () => {
    // Anduril 9497 on prod: posted_at is an updated_at-style bump, months after we first saw it.
    const age = jobAge(
      { posted_at: "2026-09-21T18:54:43Z", first_seen_at: "2026-06-28T00:15:51.761131Z" },
      now,
    );
    expect(age?.kind).toBe("first_seen");
    expect(age?.label).toBe("First seen by Chronicle Jun 28, 2026");
    expect(age?.relative).toBe("2mo ago");
  });

  it("falls back to first seen when posted_at is missing or invalid", () => {
    expect(jobAge({ posted_at: null, first_seen_at: "2026-09-24T12:00:00Z" }, now)?.label).toBe(
      "First seen by Chronicle Sep 24, 2026",
    );
    expect(jobAge({ posted_at: "bogus", first_seen_at: "2026-09-24T12:00:00Z" }, now)?.kind).toBe("first_seen");
  });

  it("returns null when there is no usable date", () => {
    expect(jobAge({ posted_at: null, first_seen_at: null }, now)).toBeNull();
    expect(jobAge({}, now)).toBeNull();
  });

  it("keeps the absolute date when the relative age is unknown (far future)", () => {
    const age = jobAge({ posted_at: null, first_seen_at: "2027-01-01T00:00:00Z" }, now);
    expect(age?.relative).toBeNull();
    expect(age?.absolute).toBe("Jan 1, 2027");
  });
});

describe("boardsRechecked", () => {
  it("states the 7-day count from /meta freshness", () => {
    expect(boardsRechecked({ boards_active: 596, boards_checked_7d: 412 })).toBe(
      "412 of 596 company boards re-checked in the last 7 days",
    );
    expect(boardsRechecked({ boards_active: 1500, boards_checked_7d: 1204 })).toBe(
      "1,204 of 1,500 company boards re-checked in the last 7 days",
    );
    expect(boardsRechecked({ boards_active: 596, boards_checked_7d: 596 })).toBe(
      "All 596 company boards re-checked in the last 7 days",
    );
    expect(boardsRechecked({ boards_active: 596, boards_checked_7d: 0 })).toBe(
      "0 of 596 company boards re-checked in the last 7 days",
    );
  });

  it("returns null (number-free copy) when freshness is absent or inconsistent", () => {
    expect(boardsRechecked(undefined)).toBeNull();
    expect(boardsRechecked(null)).toBeNull();
    expect(boardsRechecked({ boards_active: 0, boards_checked_7d: 0 })).toBeNull();
    expect(boardsRechecked({ boards_active: 10, boards_checked_7d: 11 })).toBeNull();
    expect(boardsRechecked({ boards_active: 10, boards_checked_7d: -1 })).toBeNull();
    expect(boardsRechecked({ boards_active: 10.5, boards_checked_7d: 3 })).toBeNull();
  });
});

describe("displayDepartment", () => {
  it("drops the Other catch-all and empty values", () => {
    expect(displayDepartment("Other")).toBe("");
    expect(displayDepartment(" other ")).toBe("");
    expect(displayDepartment(null)).toBe("");
    expect(displayDepartment(undefined)).toBe("");
    expect(displayDepartment("  ")).toBe("");
  });

  it("keeps real departments untouched", () => {
    expect(displayDepartment("Engineering")).toBe("Engineering");
    expect(displayDepartment("G&A")).toBe("G&A");
    expect(displayDepartment(" ML & AI ")).toBe("ML & AI");
  });
});
