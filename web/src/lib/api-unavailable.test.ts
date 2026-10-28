import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getJobs } from "./api";
import { API_UNAVAILABLE_DIGEST, isApiUnavailable } from "./api-errors";
import { ErrorNotice } from "@/components/ErrorNotice";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const render = (error: Error & { digest?: string }) =>
  renderToStaticMarkup(createElement(ErrorNotice, { error, reset: () => {} }));

describe("API 503 handling", () => {
  it("a final 503 becomes an error carrying the marker digest", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 503 }));
    const err = await getJobs({}).catch((e) => e);
    expect(err.digest).toBe(API_UNAVAILABLE_DIGEST);
    expect(isApiUnavailable(err)).toBe(true);
    expect(err.message).toContain("(503)");
  });

  it("other failures stay ordinary errors", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 500 }));
    const err = await getJobs({}).catch((e) => e);
    expect(isApiUnavailable(err)).toBe(false);
  });

  it("503 shows the calm notice with the GitHub link and a Try again button", () => {
    const html = render(Object.assign(new Error("x"), { digest: API_UNAVAILABLE_DIGEST }));
    expect(html).toContain("Live job data is refreshing");
    expect(html).toContain("Roles will be back shortly. The code, evals and screenshots are on");
    expect(html).toContain('href="https://github.com/pratyushpad/Chronicle"');
    expect(html).toContain("Try again");
    expect(html).not.toContain("Oops");
  });

  it("any other error keeps the generic page", () => {
    const html = render(Object.assign(new Error("boom"), { digest: "12345" }));
    expect(html).toContain("Oops");
    expect(html).toContain("Something went wrong loading this page.");
    expect(html).not.toContain("refreshing");
  });
});
