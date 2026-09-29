import Link from "next/link";
import { getMeta, getCompanies, type Meta, type CompanyItem } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { BarFill } from "@/components/landing/BarFill";
import { Reveal } from "@/components/motion/Reveal";
import { Marquee } from "@/components/gsap/Marquee";
import { BatchReveal } from "@/components/gsap/BatchReveal";
import { boardsRechecked } from "@/lib/format";

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

  // Freshness copy states what was measured (/meta freshness), never a cadence. Without
  // that block (older API) the copy stays true without a number.
  const rechecked = boardsRechecked(meta?.freshness);

  return (
    <main id="main" className="relative overflow-hidden">
      {/* ─── Hero: search and live numbers in the first viewport ─── */}
      <section className="mx-auto max-w-6xl px-6 pb-14 pt-8 md:px-8 md:pb-20 md:pt-14 lg:px-12">
        <p className="font-sans text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Internships and early-career roles, straight from company boards
        </p>
        <h1 className="mt-4 max-w-4xl font-display text-4xl leading-[1.08] tracking-tight text-foreground sm:text-5xl lg:text-6xl">
          Every open role. Every <span className="italic">company.</span>
        </h1>

        <form action="/jobs" method="get" role="search" className="mt-8 flex max-w-2xl flex-col gap-3 sm:flex-row">
          <label htmlFor="home-search" className="sr-only">
            Search roles
          </label>
          <input
            id="home-search"
            name="q"
            type="search"
            placeholder="Search roles, e.g. software engineer intern"
            className="h-12 w-full min-w-0 border border-input bg-background px-4 sm:flex-1 font-sans text-base text-foreground placeholder:text-muted-foreground focus:border-foreground focus:outline-none"
          />
          <button
            type="submit"
            className="h-12 shrink-0 bg-accent px-6 font-sans text-sm font-medium text-accent-foreground transition-colors hover:bg-accent-secondary focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
          >
            Search
          </button>
        </form>
        <nav aria-label="Popular searches" className="mt-4 flex flex-wrap gap-2">
          {[
            { label: "Internships", href: "/jobs?level=intern" },
            { label: "New grad", href: "/jobs?level=new_grad" },
            { label: "Remote", href: "/jobs?remote=true" },
            { label: "New since last run", href: "/jobs?since_last_run=true" },
          ].map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="inline-flex min-h-[36px] items-center border border-border-light px-3 font-sans text-sm text-foreground transition-colors hover:border-input hover:bg-muted"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        {meta && (
          <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-6 border-t border-border-light pt-6 sm:grid-cols-4">
            {[
              { value: formatNumber(meta.total_active_jobs), label: "Open roles" },
              { value: formatNumber(exp.intern ?? 0), label: "Internships" },
              { value: formatNumber(meta.total_companies), label: "Companies" },
              meta.freshness && meta.freshness.boards_active > 0
                ? {
                    value: `${formatNumber(meta.freshness.boards_checked_7d)}`,
                    label: `Boards re-checked in 7 days, of ${formatNumber(meta.freshness.boards_active)}`,
                  }
                : { value: `${remotePct}%`, label: "Remote roles" },
            ].map(({ value, label }) => (
              // dt first in the DOM (label, then value), shown number-first.
              <div key={label} className="flex min-w-0 flex-col-reverse">
                <dt className="mt-2 font-sans text-xs text-muted-foreground">{label}</dt>
                <dd className="font-display text-3xl leading-none text-foreground md:text-4xl">{value}</dd>
              </div>
            ))}
          </dl>
        )}

        <p className="mt-10 max-w-3xl font-body text-lg leading-relaxed text-foreground md:text-xl">
          Chronicle pulls every open role <span className="italic">directly</span>{" "}
          from {meta ? formatNumber(meta.total_companies) : "hundreds of"} companies&rsquo;
          own career pages — Stripe, Anthropic, OpenAI, Databricks, and more. Boards are
          re-checked on a rolling cycle, and a role that disappears from its company&rsquo;s
          board leaves Chronicle at the next check. No recruiters. No noise.
        </p>
      </section>

      <div className="h-px w-full bg-border-light" />

      {/* ─── How it works — direct from source ─── */}
      <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
        <div className="flex items-center gap-4">
          <span className="font-sans text-xs uppercase tracking-[0.25em] text-foreground">
            Sourced Direct
          </span>
          <span className="h-px flex-1 bg-border-light" />
        </div>

        <h2 className="mt-10 max-w-3xl font-display text-4xl font-medium leading-tight tracking-tight text-foreground md:text-6xl">
          We don&rsquo;t scrape job boards. We read the source.
        </h2>

        <BatchReveal className="mt-16 grid grid-cols-1 gap-px border border-input bg-foreground md:grid-cols-3">
          {[
            {
              n: "01",
              t: "Pulled from the ATS",
              d: "Every role comes straight from each company's own Greenhouse, Lever, or Ashby board — the same system their recruiters post to.",
            },
            {
              n: "02",
              t: "Re-checked at the source",
              d: rechecked
                ? `${rechecked}. The boards checked longest ago go first.`
                : "Company boards are re-checked on a rolling cycle, and the boards checked longest ago go first.",
            },
            {
              n: "03",
              t: "Removed at the next check",
              d: "When a role disappears from its company’s board, it leaves Chronicle the next time that board is checked.",
            },
          ].map((step) => (
            <div
              key={step.n}
              data-batch
              className="group bg-background p-8 transition-colors duration-100 hover:bg-foreground hover:text-background"
            >
              <div className="font-sans text-xs uppercase tracking-[0.2em] text-muted-foreground transition-colors duration-100 group-hover:text-background/60">
                {step.n}
              </div>
              <h3 className="mt-6 font-display text-2xl font-medium leading-snug">
                {step.t}
              </h3>
              <p className="mt-4 font-sans text-base leading-relaxed text-muted-foreground transition-colors duration-100 group-hover:text-background/80">
                {step.d}
              </p>
            </div>
          ))}
        </BatchReveal>
      </section>

      <div className="h-px w-full bg-border-light" />

      {/* ─── Market intelligence ─── */}
      {topIndustries.length > 0 && (
        <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
          <div className="flex items-center gap-4">
            <span className="font-sans text-xs uppercase tracking-[0.25em] text-foreground">
              Market Intelligence
            </span>
            <span className="h-px flex-1 bg-border-light" />
          </div>

          <h2 className="mt-10 font-display text-4xl font-medium leading-tight tracking-tight text-foreground md:text-6xl">
            Where the hiring is.
          </h2>

          <div className="mt-16 grid gap-16 lg:grid-cols-12 lg:gap-12">
            {/* Industry bars */}
            <div className="lg:col-span-8">
              <div className="font-sans text-xs uppercase tracking-[0.2em] text-muted-foreground">
                Open roles by industry
              </div>
              <ul className="mt-8 space-y-5">
                {topIndustries.map((ind, i) => (
                  <Reveal as="li" key={ind.industry} index={i}>
                    <div className="flex items-baseline justify-between gap-4">
                      <span className="font-display text-lg text-foreground md:text-xl">
                        {ind.industry}
                      </span>
                      <span className="font-sans text-xs text-muted-foreground">
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
              <div className="font-sans text-xs uppercase tracking-[0.2em] text-muted-foreground">
                By career stage
              </div>
              <div className="mt-8 divide-y divide-border-light border-y border-border-light">
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
                    <span className="font-sans text-xs uppercase tracking-[0.15em] text-foreground">
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

      <div className="h-px w-full bg-border-light" />

      {/* ─── Transparency ─── */}
      <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
        <div className="flex items-center gap-4">
          <span className="font-sans text-xs uppercase tracking-[0.25em] text-foreground">
            Radical Transparency
          </span>
          <span className="h-px flex-1 bg-border-light" />
        </div>

        <BatchReveal className="mt-16 grid grid-cols-1 gap-x-12 gap-y-12 md:grid-cols-3">
          {[
            {
              t: "Freshness, shown",
              d: "Every role page shows when Chronicle last saw it live on the company’s board, so you can judge how fresh a listing is before you apply.",
            },
            {
              t: "Sponsorship-flagged",
              d: "We parse each posting for visa-sponsorship signals and flag it on the card — so international candidates can spot the roles that will actually consider them.",
            },
            {
              t: "Salary, where shared",
              d: "When a company discloses a salary band, we surface it on the card. No guessing, no bait-and-switch.",
            },
          ].map((item) => (
            <div key={item.t} data-batch className="border-t border-border-light pt-6">
              <h3 className="font-display text-2xl font-medium leading-snug text-foreground">
                {item.t}
              </h3>
              <p className="mt-4 font-sans text-base leading-relaxed text-muted-foreground">
                {item.d}
              </p>
            </div>
          ))}
        </BatchReveal>
      </section>

      <div className="h-px w-full bg-border-light" />

      {/* ─── Curated companies wordmark wall ─── */}
      {marquee.length > 0 && (
        <section className="mx-auto max-w-6xl px-6 py-24 md:px-8 md:py-32 lg:px-12">
          <div className="flex items-center gap-4">
            <span className="font-sans text-xs uppercase tracking-[0.25em] text-foreground">
              The Index
            </span>
            <span className="h-px flex-1 bg-border-light" />
            <span className="font-sans text-xs uppercase tracking-[0.25em] text-muted-foreground">
              {meta?.total_companies ? `${formatNumber(meta.total_companies)} companies, hand-picked` : "Hand-picked companies"}
            </span>
          </div>

          <Marquee items={marquee.map((c) => ({ id: c.id, name: c.name }))} />

          <div className="mt-10">
            <Link
              href="/companies"
              className="inline-flex items-center gap-3 font-sans text-xs uppercase tracking-[0.2em] text-foreground underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
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
              "radial-gradient(circle at top center, var(--background), transparent 70%)",
          }}
        />
        <div className="relative mx-auto max-w-6xl px-6 py-28 text-center md:px-8 md:py-40 lg:px-12">
          <h2 className="mx-auto max-w-4xl font-display text-5xl font-medium leading-[1.05] tracking-tight md:text-7xl lg:text-8xl">
            Find the role that&rsquo;s{" "}
            <span className="italic">actually</span> open.
          </h2>
          <div className="mt-12 flex justify-center">
            {/* Full-width on phones like the hero CTAs (the label is ~230px of tracked mono);
                min-height instead of a fixed one so a longer count wraps inside the box. */}
            <Link
              href="/jobs"
              className="group inline-flex min-h-[56px] w-full items-center justify-between gap-3 border-2 border-background bg-background px-5 py-3 text-left font-sans text-xs font-medium uppercase tracking-[0.2em] text-foreground transition-colors duration-100 hover:bg-transparent hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-background focus-visible:outline-offset-[3px] sm:w-auto sm:justify-center sm:gap-4 sm:px-10"
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
