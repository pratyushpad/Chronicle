import Link from "next/link";
import { getMeta } from "@/lib/api";
import { SectionLabel } from "@/components/SectionLabel";
import { formatNumber } from "@/lib/utils";

export default async function Home() {
  let meta = null;
  try {
    meta = await getMeta();
  } catch {
    // API not up yet — render gracefully
  }

  return (
    <main className="relative overflow-hidden">
      {/* Ambient glow */}
      <div
        aria-hidden
        className="pointer-events-none fixed left-1/2 top-1/2 h-[600px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          background: "radial-gradient(circle, rgba(184,134,11,0.04) 0%, transparent 70%)",
        }}
      />

      {/* Hero */}
      <section className="mx-auto max-w-3xl px-6 py-32 text-center">
        <SectionLabel className="mb-10">Job Intelligence</SectionLabel>

        <h1 className="font-display text-5xl leading-[1.1] tracking-[-0.02em] text-foreground sm:text-6xl lg:text-7xl">
          Every open role.
          <br />
          Every company.
          <br />
          <span className="text-accent">One feed.</span>
        </h1>

        <p className="mx-auto mt-6 max-w-xl font-body text-lg leading-[1.75] text-muted-foreground">
          Folio pulls every open role from 201 top tech companies — Stripe, Anthropic,
          OpenAI, Databricks, Spotify, and more — into one searchable feed. No signup.
          No noise. Refreshed every 48 hours.
        </p>

        {/* Live stat */}
        {meta && (
          <div className="mt-10 flex flex-col items-center gap-1">
            <span className="font-display text-5xl text-accent">
              {formatNumber(meta.total_active_jobs)}
            </span>
            <span className="font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
              open roles across {meta.total_companies} companies
            </span>
          </div>
        )}

        {/* CTA */}
        <div className="mt-12 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
          <Link
            href="/jobs"
            className="inline-flex min-h-[44px] items-center justify-center rounded-md bg-accent px-8 font-body text-sm font-medium tracking-wide text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-accent-secondary hover:shadow-md active:translate-y-0"
          >
            Browse Open Roles
          </Link>
          <Link
            href="/jobs?since_last_run=true"
            className="inline-flex min-h-[44px] items-center justify-center rounded-md border border-border px-8 font-body text-sm text-muted-foreground transition-all duration-200 hover:border-accent hover:text-accent"
          >
            New since last run →
          </Link>
        </div>
      </section>

      {/* Divider */}
      <div className="border-t border-border" />

      {/* Stats strip */}
      {meta && (
        <section className="mx-auto max-w-5xl px-6 py-16">
          <SectionLabel className="mb-12">At a glance</SectionLabel>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
            {[
              { value: formatNumber(meta.total_active_jobs), label: "Active roles" },
              { value: String(meta.total_companies), label: "Companies" },
              { value: ((meta as any).industries?.length ?? meta.departments.length).toString(), label: "Industries" },
              {
                value: meta.last_run
                  ? `${meta.last_run.companies_ok}/${meta.last_run.companies_ok + meta.last_run.companies_failed}`
                  : "—",
                label: "Sources OK",
              },
            ].map(({ value, label }) => (
              <div key={label} className="text-center">
                <div className="font-display text-4xl text-accent">{value}</div>
                <div className="mt-1 font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground">
                  {label}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
