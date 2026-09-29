import type { Metadata } from "next";
import { getStatus, type StatusResponse } from "@/lib/api";
import { boardsRechecked, formatAbsoluteDate, relativeAge } from "@/lib/format";
import { formatNumber } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Status",
  description: "How fresh Chronicle's data is: recent ingest runs, failing company boards and re-check coverage.",
};

function duration(seconds: number | null): string {
  if (seconds == null) return "running";
  if (seconds < 90) return `${seconds} s`;
  return `${Math.round(seconds / 60)} min`;
}

export default async function StatusPage() {
  let status: StatusResponse | null = null;
  try {
    status = await getStatus();
  } catch {
    status = null;
  }
  const now = Date.now();

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-10 md:px-8">
      <h1 className="font-display text-3xl text-foreground md:text-4xl">Status</h1>
      <p className="mt-2 max-w-prose font-sans text-sm text-muted-foreground">
        Chronicle re-reads each company&rsquo;s own careers board on a rolling cycle. This page shows
        what the last runs actually did. Every number comes from the run log.
      </p>

      {!status ? (
        <p className="mt-10 font-sans text-sm text-muted-foreground">Status is unavailable right now.</p>
      ) : (
        <>
          {status.freshness && (
            <p className="mt-6 border-y border-border-light py-4 font-sans text-sm text-foreground">
              {boardsRechecked(status.freshness) ?? "Board freshness is unknown."}
              {status.freshness.oldest_check_at && (
                <span className="text-muted-foreground">
                  {" "}
                  · oldest check {relativeAge(status.freshness.oldest_check_at, now) ?? formatAbsoluteDate(status.freshness.oldest_check_at)}
                </span>
              )}
            </p>
          )}

          <section className="mt-10" aria-labelledby="runs">
            <h2 id="runs" className="font-display text-2xl text-foreground">Recent runs</h2>
            {status.runs.length === 0 ? (
              <p className="mt-4 font-sans text-sm text-muted-foreground">No runs recorded yet.</p>
            ) : (
              // Scrolls sideways on phones; focusable so keyboard users can scroll it too.
              <div className="mt-4 overflow-x-auto" tabIndex={0} role="region" aria-label="Recent runs (scrolls sideways)">
                <table className="w-full min-w-[560px] border-collapse font-sans text-sm">
                  <thead>
                    <tr className="border-b border-border-light text-left text-xs text-muted-foreground">
                      <th scope="col" className="py-2 pr-4 font-normal">Started</th>
                      <th scope="col" className="py-2 pr-4 font-normal">Took</th>
                      <th scope="col" className="py-2 pr-4 font-normal">Boards read</th>
                      <th scope="col" className="py-2 pr-4 font-normal">Roles seen</th>
                      <th scope="col" className="py-2 pr-4 font-normal">New</th>
                      <th scope="col" className="py-2 font-normal">Closed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.runs.map((r) => (
                      <tr key={r.id} className="border-b border-border-light">
                        <td className="py-2 pr-4 text-foreground">
                          <time dateTime={r.started_at} title={formatAbsoluteDate(r.started_at) ?? undefined}>
                            {relativeAge(r.started_at, now) ?? formatAbsoluteDate(r.started_at)}
                          </time>
                          {r.crashed && <span className="ml-2 font-medium text-negative">crashed</span>}
                          {r.open && <span className="ml-2 font-medium text-warning">running</span>}
                        </td>
                        <td className="py-2 pr-4 text-foreground">{r.crashed ? "–" : duration(r.seconds)}</td>
                        <td className="py-2 pr-4 text-foreground">
                          {formatNumber(r.boards_ok)} of {formatNumber(r.boards_total)}
                          {r.boards_failed > 0 && <span className="text-negative"> ({r.boards_failed} failed)</span>}
                        </td>
                        <td className="py-2 pr-4 text-foreground">{formatNumber(r.jobs_seen)}</td>
                        <td className="py-2 pr-4 text-foreground">{formatNumber(r.jobs_new)}</td>
                        <td className="py-2 text-foreground">{formatNumber(r.jobs_closed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="mt-12" aria-labelledby="failing">
            <h2 id="failing" className="font-display text-2xl text-foreground">Boards failing to load</h2>
            <p className="mt-1 font-sans text-sm text-muted-foreground">
              Across the runs above. A board that fails every run has usually moved or closed.
            </p>
            {status.failing_boards.length === 0 ? (
              <p className="mt-4 font-sans text-sm text-foreground">None.</p>
            ) : (
              <ul className="mt-4 divide-y divide-border-light border-y border-border-light">
                {status.failing_boards.map((b) => (
                  <li key={`${b.ats}:${b.slug}`} className="py-3 font-sans text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <span className="text-foreground">
                        {b.company ?? b.slug} <span className="text-muted-foreground">({b.ats}: {b.slug})</span>
                      </span>
                      <span className="text-negative">
                        failed {b.failed_runs} of {status!.runs.length} runs
                      </span>
                    </div>
                    <p className="mt-1 break-words text-xs text-muted-foreground">
                      {b.last_success_at
                        ? `Last loaded ${relativeAge(b.last_success_at, now) ?? formatAbsoluteDate(b.last_success_at)}`
                        : "Never loaded"}
                      {b.last_error && <> · {b.last_error}</>}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
