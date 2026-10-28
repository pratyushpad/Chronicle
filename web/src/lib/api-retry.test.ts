import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getJob, getJobs, getSimilarJobs } from "./api";
import { serviceKey } from "./internal-service";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

const ok = () => new Response(JSON.stringify({ id: 1 }), { status: 200 });

describe("fetchJSON retry", () => {
  it("retries an idempotent GET once after a 503 (Render cold start) and returns the second answer", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 503 })).mockResolvedValueOnce(ok());
    await expect(getJob(1)).resolves.toEqual({ id: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries once after a network error, then gives up (two attempts, never more)", async () => {
    fetchMock.mockRejectedValue(new Error("socket hang up"));
    await expect(getJobs({})).rejects.toThrow("socket hang up");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry a 4xx", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 422 }));
    await expect(getJobs({})).rejects.toThrow("(422)");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts each attempt at 10 s: a hung API costs about 20.5 s in total, under 25 s", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_url: string, init: { signal: AbortSignal }) =>
        new Promise((_res, rej) => {
          init.signal.addEventListener("abort", () => rej(new Error("aborted")));
        }),
    );
    const p = getJobs({});
    const assertion = expect(p).rejects.toThrow("aborted");
    await vi.advanceTimersByTimeAsync(20_500);
    await assertion;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("similar roles stay one-shot", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 503 }));
    await expect(getSimilarJobs(1)).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("server-to-server key", () => {
  it("is sent when INTERNAL_API_SECRET is set, and matches the API's service_key()", async () => {
    vi.stubEnv("INTERNAL_API_SECRET", "s3cret");
    fetchMock.mockResolvedValue(ok());
    await getJobs({ q: "x", mode: "hybrid" });
    const init = fetchMock.mock.calls[0][1] as { headers: Record<string, string> };
    // Value computed by api/app/ratelimit.py service_key("s3cret"); the two must agree.
    expect(init.headers["X-Internal-Service"]).toBe(
      "19e328a26863af84496a1dbadbdb3f28dc475492d1d5def6f4c99d37ed595c87",
    );
    expect(serviceKey()).toBe(init.headers["X-Internal-Service"]);
  });

  it("is omitted without a secret", async () => {
    vi.stubEnv("INTERNAL_API_SECRET", "");
    fetchMock.mockResolvedValue(ok());
    await getJobs({});
    expect((fetchMock.mock.calls[0][1] as { headers?: unknown }).headers).toBeUndefined();
  });
});
