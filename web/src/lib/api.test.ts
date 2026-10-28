import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { revalidate as sitemapRevalidate } from "@/app/sitemap";
import {
  getJob,
  getJobs,
  getMeta,
  getSimilarJobs,
  getSitemapJobs,
  getStatus,
  type SitemapJobs,
} from "./api";

// Each API fetch's `next.revalidate` is how long Vercel serves its cached copy before going
// back to the Render API (and Neon behind it). Crawler traffic on /jobs/[id] hits the same
// few URLs again and again, so these windows are the egress budget. A page refreshes at the
// pace of its shortest fetch, which is why everything the job page renders (the job, /meta
// in the layout, similar roles, more-at-company) is pinned to the same hour.

const HOUR = 3600;
const DAY = 86400;

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** URL and cache window of the one fetch the helper under test just made. */
function sent(): { url: string; revalidate: number | undefined } {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as [string, { next?: { revalidate?: number } }];
  return { url, revalidate: init.next?.revalidate };
}

const CASES: Array<[name: string, call: () => Promise<unknown>, path: string, revalidate: number]> = [
  ["getJob", () => getJob(42), "/jobs/42", HOUR],
  ["getMeta", () => getMeta(), "/meta", HOUR],
  ["getSimilarJobs", () => getSimilarJobs(42, 4), "/jobs/42/similar?limit=4", HOUR],
  ["getStatus", () => getStatus(), "/status", 900],
  ["getSitemapJobs", () => getSitemapJobs(0, 20_000), "/sitemap/jobs?offset=0&limit=20000", DAY],
  ["getJobs (the feed's default)", () => getJobs({ q: "rust" }), "/jobs?q=rust", 300],
];

describe("API cache windows", () => {
  it.each(CASES)("%s", async (_name, call, path, revalidate) => {
    await call();
    const req = sent();
    expect(req.url.endsWith(path)).toBe(true);
    expect(req.revalidate).toBe(revalidate);
  });

  it("getJobs takes a longer window for more-at-company, and keeps it out of the query string", async () => {
    await getJobs({ company_id: 7, page_size: 5 }, { revalidate: HOUR });
    const req = sent();
    expect(req.url.endsWith("/jobs?company_id=7&page_size=5")).toBe(true);
    expect(req.revalidate).toBe(HOUR);
  });

  it("the sitemap segment refreshes on the same window as its job fetch", async () => {
    await getSitemapJobs(0, 10);
    expect(sitemapRevalidate).toBe(sent().revalidate);
  });
});

describe("SitemapJobs", () => {
  it("allows rows without last_seen_at (the sitemap only reads id)", () => {
    // Compile-time contract, checked by `tsc --noEmit`: the API may stop sending the field.
    const rows: SitemapJobs["items"] = [
      { id: 1 },
      { id: 2, last_seen_at: null },
      { id: 3, last_seen_at: "2026-10-01T00:00:00Z" },
    ];
    expect(rows.map((r) => r.id)).toEqual([1, 2, 3]);
  });
});
