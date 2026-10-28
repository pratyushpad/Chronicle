import { describe, expect, it } from "vitest";
import { MAX_PAGE, MAX_TEXT, clampPage, clampText, parseJobId } from "./params";
import robots from "@/app/robots";

describe("clampPage", () => {
  it("defaults junk to page 1 and caps deep pages", () => {
    expect(clampPage(undefined)).toBe(1);
    expect(clampPage("abc")).toBe(1);
    expect(clampPage("-4")).toBe(1);
    expect(clampPage("7")).toBe(7);
    expect(clampPage("100000")).toBe(MAX_PAGE);
  });
});

describe("clampText", () => {
  it("strips NUL and truncates to the API limit", () => {
    expect(clampText(undefined)).toBeUndefined();
    expect(clampText("\u0000")).toBeUndefined();
    expect(clampText("a\u0000b")).toBe("ab");
    expect(clampText("x".repeat(5000))).toHaveLength(MAX_TEXT);
  });
});

describe("parseJobId", () => {
  it("accepts plain positive int4 ids only", () => {
    expect(parseJobId("42")).toBe(42);
    expect(parseJobId("2147483647")).toBe(2147483647);
    for (const bad of ["0", "-1", "abc", "1e3", "042", "4.2", "2147483648", "99999999999", ""]) {
      expect(parseJobId(bad)).toBeNull();
    }
  });
});

describe("robots", () => {
  it("keeps crawlers off query-string variants and per-job pages", () => {
    const rules = robots().rules;
    const disallow = (Array.isArray(rules) ? rules[0] : rules).disallow as string[];
    for (const path of ["/jobs/", "/jobs?", "/companies?", "/*?*page=", "/*?*q="]) {
      expect(disallow).toContain(path);
    }
    expect(disallow).not.toContain("/jobs");
    expect(disallow).not.toContain("/companies/");
  });
});
