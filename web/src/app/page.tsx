import Link from "next/link";
import { getMeta, getCompanies, type Meta, type CompanyItem } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { HeroHeadline } from "@/components/landing/HeroHeadline";
import { BarFill } from "@/components/landing/BarFill";
import { CountUp } from "@/components/motion/CountUp";
import { Reveal } from "@/components/motion/Reveal";

export default async function Home() {
  let meta: Meta | null = null;
  let companies: CompanyItem[] = [];
  try {
    [meta, companies] = await Promise.all([getMeta(), getCompanies()]);
  } catch {
    // API not up yet — render gracefully with whatever resolved
    try {
      meta = await getMeta();
    } catch {}
  }

  const remotePct =
    meta && meta.total_active_jobs > 0
      ? Math.round((meta.remote_count / meta.total_active_jobs) * 100)
      : 0;
  const topIndustries = meta?.top_industries ?? [];
  const maxIndustry = topIndustries.reduce((m, i) => Math.max(m, i.count), 0) || 1;
  const exp = meta?.experience_counts ?? {};

  // Curated wordmark wall — most-hiring companies first.
  const marquee = [...companies]
    .sort((a, b) => b.active_job_count - a.active_job_count)
    .slice(0, 28);

  return (
    <main id="main" className="relative overflow-hidden">
      {/* ─── Hero ─── */}
      <section className="mx-auto max-w-6xl px-6 pb-24 pt-20 md:px-8 md:pb-32 md:pt-28 lg:px-12">
        <div className="flex items-center gap-4">
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-foreground">
            Job Intelligence
          </span>
          <span className="h-px flex-1 bg-foreground" />
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-muted-foreground">
            Est. 2026
          </span>
        </div>

        <HeroHeadline />

        <div className="mt-12 flex items-center gap-6 md:mt-16">
          <span className="h-1 w-24 bg-foreground md:w-40" />
          <span className="h-3 w-3 border-2 border-foreground" />
          <span className="h-1 flex-1 bg-foreground" />
        </div>

        <div className="mt-12 grid gap-12 md:grid-cols-12 md:gap-8">
          <p className="font-body text-xl leading-relaxed text-foreground md:col-span-7 lg:text-2xl">
            Chronicle pulls every open role <span className="italic">directly</span>{" "}
            from {meta ? formatNumber(meta.total_companies) : "hundreds of"} companies&rsquo;
            own career pages — Stripe, Anthropic, OpenAI, Databricks, and more. Verified
            live every sync. Auto-removed the moment a role closes. No ghost jobs. No
            recruiters. No noise.
          </p>

          <div className="flex flex-col gap-4 md:col-span-5 md:items-end md:justify-end">
            <Link
              href="/jobs"
              className="group inline-flex h-14 w-full items-center justify-between gap-4 border-2 border-foreground bg-foreground px-8 font-mono text-xs font-medium uppercase tracking-[0.2em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px] md:w-auto"
            >
              Browse Open Roles
              <span aria-hidden>→</span>
            </Link>
            <Link
              href="/jobs?since_last_run=true"
              className="group inline-flex h-14 w-full items-center justify-between gap-4 border-2 border-foreground bg-background px-8 font-mono text-xs font-medium uppercase tracking-[0.2em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px] md:w-auto"
            >
              New Since Last Sync
              <span aria-hidden>→</span>
            </Link>
          </div>
        </div>
      </section>

      {/* ─── Inverted stats ─── */}
      {meta && (
        <section className="relative bg-foreground text-background">
          <div
            aria-hidden
            className="texture-lines-inverted pointer-events-none absolute inset-0 opacity-[0.06]"
          />
          <div className="relative mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
            <div className="flex items-center gap-4">
              <span className="font-mono text-xs uppercase tracking-[0.25em] text-background">
                At a Glance
              </span>
              <span className="h-px flex-1 bg-background/40" />
            </div>

            <div className="mt-16 border-b border-background/20 pb-16">
              <CountUp
                value={meta.total_active_jobs}
                className="font-display text-7xl font-medium leading-none tracking-tight md:text-8xl lg:text-9xl"
              />
              <div className="mt-4 font-mono text-xs uppercase tracking-[0.2em] text-background/60">
                Open roles indexed across {meta.total_companies} companies
              </div>
            </div>

            <div className="mt-16 grid grid-cols-1 divide-y divide-background/20 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              {[
                { value: formatNumber(meta.fresh_since_last_run), label: "Fresh this sync" },
                { value: `${remotePct}%`, label: "Remote roles" },
                {
                  value: meta.last_run
                    ? `${meta.last_run.companies_ok}/${
                        meta.last_run.companies_ok + meta.last_run.companies_failed
                      }`
                    : "—",
                  label: "Sources verified",
                },
              ].map(({ value, label }) => (
                <div key={label} className="py-8 sm:px-8 sm:py-0 sm:first:pl-0">
                  <div className="font-display text-5xl font-medium leading-none md:text-6xl">
                    {value}
                  </div>
                  <div className="mt-3 font-mono text-xs uppercase tracking-[0.2em] text-background/60">
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <div className="h-1 w-full bg-foreground" />

      {/* ─── How it works — direct from source ─── */}
      <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
        <div className="flex items-center gap-4">
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-foreground">
            Sourced Direct
          </span>
          <span className="h-px flex-1 bg-foreground" />
        </div>

        <h2 className="mt-10 max-w-3xl font-display text-4xl font-medium leading-tight tracking-tight text-foreground md:text-6xl">
          We don&rsquo;t scrape job boards. We read the source.
        </h2>

        <div className="mt-16 grid grid-cols-1 gap-px border border-foreground bg-foreground md:grid-cols-3">
          {[
            {
              n: "01",
              t: "Pulled from the ATS",
              d: "Every role comes straight from each company's own Greenhouse, Lever, or Ashby board — the same system their recruiters post to.",
            },
            {
              n: "02",
              t: "Verified live each sync",
              d: `We re-check all ${meta ? meta.total_companies + " " : ""}sources on every run. If a role is still listed, it's still open. What you see is what's actually hiring.`,
            },
            {
              n: "03",
              t: "Auto-expired when gone",
              d: "The instant a role disappears from the source, it disappears here. No stale listings, no dead links, no ghost jobs.",
            },
          ].map((step, i) => (
            <Reveal
              key={step.n}
              index={i}
              className="group bg-background p-8 transition-colors duration-100 hover:bg-foreground hover:text-background"
            >
              <div className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground transition-colors duration-100 group-hover:text-background/60">
                {step.n}
              </div>
              <h3 className="mt-6 font-display text-2xl font-medium leading-snug">
                {step.t}
              </h3>
              <p className="mt-4 font-body text-base leading-relaxed text-muted-foreground transition-colors duration-100 group-hover:text-background/80">
                {step.d}
              </p>
            </Reveal>
          ))}
        </div>
      </section>

      <div className="h-1 w-full bg-foreground" />

      {/* ─── Market intelligence ─── */}
      {topIndustries.length > 0 && (
        <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
          <div className="flex items-center gap-4">
            <span className="font-mono text-xs uppercase tracking-[0.25em] text-foreground">
              Market Intelligence
            </span>
            <span className="h-px flex-1 bg-foreground" />
          </div>

          <h2 className="mt-10 font-display text-4xl font-medium leading-tight tracking-tight text-foreground md:text-6xl">
            Where the hiring is.
          </h2>

          <div className="mt-16 grid gap-16 lg:grid-cols-12 lg:gap-12">
            {/* Industry bars */}
            <div className="lg:col-span-8">
              <div className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                Open roles by industry
              </div>
              <ul className="mt-8 space-y-5">
                {topIndustries.map((ind, i) => (
                  <Reveal as="li" key={ind.industry} index={i}>
                    <div className="flex items-baseline justify-between gap-4">
                      <span className="font-display text-lg text-foreground md:text-xl">
                        {ind.industry}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {formatNumber(ind.count)}
                      </span>
                    </div>
                    <BarFill pct={Math.max(4, (ind.count / maxIndustry) * 100)} />
                  </Reveal>
                ))}
              </ul>
            </div>

            {/* Experience mix */}
            <div className="lg:col-span-4">
              <div className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                By career stage
              </div>
              <div className="mt-8 divide-y divide-border-light border-y border-foreground">
                {[
                  { label: "Internships", value: exp.intern ?? 0, href: "/jobs?level=intern" },
                  { label: "New Grad", value: exp.new_grad ?? 0, href: "/jobs?level=new_grad" },
                  { label: "Senior +", value: exp.senior ?? 0, href: "/jobs?experience_level=Senior" },
                  { label: "Remote", value: meta?.remote_count ?? 0, href: "/jobs?remote=true" },
                ].map((row) => (
                  <Link
                    key={row.label}
                    href={row.href}
                    className="group flex items-baseline justify-between py-5 transition-colors duration-100 hover:bg-muted focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
                  >
                    <span className="font-mono text-xs uppercase tracking-[0.15em] text-foreground">
                      {row.label}
                    </span>
                    <span className="font-display text-3xl font-medium text-foreground group-hover:underline">
                      {formatNumber(row.value)}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      <div className="h-1 w-full bg-foreground" />

      {/* ─── Transparency ─── */}
      <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
        <div className="flex items-center gap-4">
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-foreground">
            Radical Transparency
          </span>
          <span className="h-px flex-1 bg-foreground" />
        </div>

        <div className="mt-16 grid grid-cols-1 gap-x-12 gap-y-12 md:grid-cols-3">
          {[
            {
              t: "Always live",
              d: "Every listing is re-verified against its source on each sync. No expired roles wasting your time.",
            },
            {
              t: "Sponsorship-flagged",
              d: "We parse each posting for visa-sponsorship signals and flag it — so international candidates can filter for roles that will actually consider them.",
            },
            {
              t: "Salary, where shared",
              d: "When a company discloses a salary band, we surface it on the card. No guessing, no bait-and-switch.",
            },
          ].map((item, i) => (
            <Reveal key={item.t} index={i} className="border-t-2 border-foreground pt-6">
              <h3 className="font-display text-2xl font-medium leading-snug text-foreground">
                {item.t}
              </h3>
              <p className="mt-4 font-body text-base leading-relaxed text-muted-foreground">
                {item.d}
              </p>
            </Reveal>
          ))}
        </div>
      </section>

      <div className="h-1 w-full bg-foreground" />

      {/* ─── Curated companies wordmark wall ─── */}
      {marquee.length > 0 && (
        <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
          <div className="flex items-center gap-4">
            <span className="font-mono text-xs uppercase tracking-[0.25em] text-foreground">
              The Index
            </span>
            <span className="h-px flex-1 bg-foreground" />
            <span className="font-mono text-xs uppercase tracking-[0.25em] text-muted-foreground">
              {meta?.total_companies ? `${formatNumber(meta.total_companies)} companies, hand-picked` : "Hand-picked companies"}
            </span>
          </div>

          <Reveal className="mt-12 grid grid-cols-2 gap-px border border-foreground bg-foreground sm:grid-cols-3 lg:grid-cols-4">
            {marquee.map((c) => (
              <Link
                key={c.id}
                href={`/jobs?company_id=${c.id}`}
                className="group flex flex-col justify-between gap-6 bg-background p-6 transition-colors duration-100 hover:bg-foreground hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:-outline-offset-[3px]"
              >
                <span className="font-display text-2xl font-medium leading-tight">
                  {c.name}
                </span>
                <span className="font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground transition-colors duration-100 group-hover:text-background/60">
                  {formatNumber(c.active_job_count)} open
                </span>
              </Link>
            ))}
          </Reveal>

          <div className="mt-10">
            <Link
              href="/companies"
              className="inline-flex items-center gap-3 font-mono text-xs uppercase tracking-[0.2em] text-foreground underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
            >
              View all companies
              <span aria-hidden>→</span>
            </Link>
          </div>
        </section>
      )}

      {/* ─── Final CTA — inverted ─── */}
      <section className="relative bg-foreground text-background">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "radial-gradient(circle at top center, #ffffff, transparent 70%)",
          }}
        />
        <div className="relative mx-auto max-w-6xl px-6 py-28 text-center md:px-8 md:py-40 lg:px-12">
          <h2 className="mx-auto max-w-4xl font-display text-5xl font-medium leading-[1.05] tracking-tight md:text-7xl lg:text-8xl">
            Find the role that&rsquo;s{" "}
            <span className="italic">actually</span> open.
          </h2>
          <div className="mt-12 flex justify-center">
            <Link
              href="/jobs"
              className="group inline-flex h-14 items-center gap-4 border-2 border-background bg-background px-10 font-mono text-xs font-medium uppercase tracking-[0.2em] text-foreground transition-colors duration-100 hover:bg-transparent hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-background focus-visible:outline-offset-[3px]"
            >
              Browse {meta ? formatNumber(meta.total_active_jobs) : "all"} open roles
              <span aria-hidden>→</span>
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
