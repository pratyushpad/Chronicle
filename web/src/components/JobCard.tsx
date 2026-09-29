"use client";
import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { m, useReducedMotion } from "motion/react";
import { cn, formatLocation, formatDepartment } from "@/lib/utils";
import { formatPay, jobAge } from "@/lib/format";
import { eligibilityFacts, jobTerm } from "@/lib/eligibility";
import type { JobListItem } from "@/lib/api";
import { duration, ease } from "@/lib/motion";
import { logInteraction, type InteractionSurface } from "@/lib/interactions";

interface Props {
  job: JobListItem;
  initialSaved?: boolean;
  why?: string;
  /** When set, impressions/clicks/saves are logged against this surface. */
  surface?: InteractionSurface;
  /** When set, shows a "not interested" control; dismissals push future matches away. */
  onDismiss?: () => void;
  /**
   * Render time (epoch ms) for the "3d ago" label. Server pages pass their own render
   * time so the server HTML and hydration compute the identical string. Client-only
   * lists (for-you, saved) may omit it.
   */
  now?: number;
  /** "compact": one dense row per role (title, company, place, pay, age) for scanning. */
  density?: "comfortable" | "compact";
}

export function JobCard({ job, initialSaved = false, why, surface, onDismiss, now, density = "comfortable" }: Props) {
  const compact = density === "compact";
  const { data: session } = useSession();
  const isAuthed = !!session?.user?.email;
  const reduce = useReducedMotion();

  const [saved, setSaved] = useState(initialSaved);
  const [loadingS, setLoadingS] = useState(false);
  // Logo starts hopeful; falls back to initials on error OR a blank/placeholder favicon.
  const [logoOk, setLogoOk] = useState(true);

  useEffect(() => {
    if (isAuthed) return;
    try {
      const bm = JSON.parse(localStorage.getItem("chronicle_bookmarks") || "[]") as number[];
      setSaved(bm.includes(job.id));
    } catch {}
  }, [job.id, isAuthed]);

  useEffect(() => {
    if (surface && isAuthed) logInteraction(job.id, "impression", surface);
  }, [job.id, surface, isAuthed]);

  const toggleSave = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    if (loadingS) return;
    if (!isAuthed) {
      try {
        const bm = JSON.parse(localStorage.getItem("chronicle_bookmarks") || "[]") as number[];
        const next = saved ? bm.filter((id) => id !== job.id) : [...bm, job.id];
        localStorage.setItem("chronicle_bookmarks", JSON.stringify(next));
        setSaved(!saved);
      } catch {}
      return;
    }
    setLoadingS(true);
    try {
      await fetch(`/api/saved/${job.id}`, { method: saved ? "DELETE" : "POST" });
      if (!saved && surface) logInteraction(job.id, "save", surface);
      setSaved(!saved);
    } finally {
      setLoadingS(false);
    }
  }, [saved, job.id, isAuthed, loadingS, surface]);

  const domain = job.company_domain;
  const logoUrl = domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=128` : null;
  const showLogo = !!logoUrl && logoOk;
  const initials = job.company_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  const location = formatLocation(job.location_normalized);
  const extraLocations = (job.location_count ?? 0) > 1 ? (job.location_count as number) - 1 : 0;
  const department = formatDepartment(job.department); // "" for the "Other" catch-all
  const pay = formatPay(job);
  const age = jobAge(job, now ?? Date.now());
  const term = jobTerm(job);
  const restrictions = eligibilityFacts(job).filter((f) => f.restrictive);

  return (
    <m.article
      className={cn(
        "group relative border border-border-light bg-card transition-colors duration-100 hover:bg-muted",
        // The heavy left bar marks state only: new since the last run, or closed.
        job.is_active === false
          ? "border-l-4 border-l-negative"
          : job.is_new
            ? "border-l-4 border-l-positive"
            : null,
      )}
      whileHover={reduce ? undefined : { y: -2 }}
      whileTap={reduce ? undefined : { y: 0 }}
      transition={{ duration: duration.fast, ease }}
    >
      <Link
        href={`/jobs/${job.id}`}
        className="absolute inset-0 z-0"
        aria-label={`${job.title} at ${job.company_name}`}
        onClick={() => surface && isAuthed && logInteraction(job.id, "click", surface)}
      />
      <div className={cn("relative z-10 pointer-events-none", compact ? "px-4 py-3" : "p-5")}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            {/* Company logo — monochrome tile, initials always render behind the favicon */}
            <div className={cn("relative shrink-0 h-10 w-10 border border-border-light bg-background items-center justify-center overflow-hidden", compact ? "hidden" : "flex")}>
              <span className="font-sans text-[11px] font-semibold text-foreground">{initials}</span>
              {showLogo && (
                // eslint-disable-next-line @next/next/no-img-element -- 40px third-party favicon; next/image would proxy every logo through the optimizer and the onLoad naturalWidth check needs the raw image.
                <img
                  src={logoUrl!}
                  alt={job.company_name}
                  loading="lazy"
                  className="absolute inset-0 h-full w-full object-contain bg-background p-1.5"
                  onLoad={(e) => {
                    // Google returns a 16px globe placeholder for unknown domains — treat as blank.
                    if ((e.target as HTMLImageElement).naturalWidth <= 16) setLogoOk(false);
                  }}
                  onError={() => setLogoOk(false)}
                />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h2 className={cn("font-display leading-snug text-foreground underline-offset-4 group-hover:underline", compact ? "text-base line-clamp-1" : "text-lg line-clamp-2")}>
                {job.title}
              </h2>
              <p className="mt-1 font-sans text-xs uppercase tracking-[0.08em] text-muted-foreground">
                {job.company_name}
                {location && <span> · {location}</span>}
                {extraLocations > 0 && <span> +{extraLocations} more</span>}
                {job.remote && <span> · Remote</span>}
                {compact && job.is_active === false && (
                  <span className="font-medium text-negative"> · Closed</span>
                )}
                {compact && job.is_active !== false && job.is_new && (
                  <span className="font-medium text-positive"> · New</span>
                )}
                {compact && pay && <span className="normal-case tracking-normal text-foreground"> · {pay}</span>}
                {compact && age && (
                  <span className="normal-case tracking-normal" suppressHydrationWarning> · {age.relative ?? age.absolute}</span>
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0 pointer-events-auto">
            {onDismiss && (
              <button
                onClick={(e) => {
                  e.preventDefault();
                  if (surface && isAuthed) logInteraction(job.id, "dismiss", surface);
                  onDismiss();
                }}
                title="Not interested — show fewer like this"
                className="p-1.5 text-muted-foreground transition-colors duration-100 hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            )}
            {/* Single save control: a bookmark IS the tracker's "Saved" stage. */}
            <button onClick={toggleSave} title={saved ? "Saved — click to remove" : "Save to tracker"} disabled={loadingS}
              className={cn(
                "p-1.5 transition-colors duration-100 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2",
                saved ? "text-foreground" : "text-muted-foreground hover:text-foreground"
              )}>
              <m.svg width="16" height="16" viewBox="0 0 24 24" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                animate={reduce ? undefined : { scale: saved ? [1, 1.3, 1] : 1 }}
                transition={{ duration: duration.base, ease }}>
                <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
              </m.svg>
            </button>
          </div>
        </div>

        {why && (
          <div className="mt-2">
            <span className="inline-block bg-foreground px-2 py-0.5 font-sans text-[11px] uppercase tracking-[0.15em] text-background">
              For You
            </span>
            {/* Ink-draw: a black rule strokes in beneath the match badge, a small
                editorial flourish that says "this was chosen for you" (transform-only). */}
            <m.span
              aria-hidden
              className="mt-1 block h-px w-full origin-left bg-foreground"
              initial={reduce ? false : { scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: duration.slow, ease, delay: duration.fast }}
            />
            <p className="mt-2 font-sans text-sm italic text-muted-foreground">{why}</p>
          </div>
        )}

        {!compact && (<>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {job.is_active === false && (
            <span className="bg-negative-bg px-2 py-0.5 font-sans text-[11px] font-medium uppercase tracking-[0.15em] text-negative">
              Closed
            </span>
          )}
          {job.is_active !== false && job.is_new && (
            <span className="bg-positive-bg px-2 py-0.5 font-sans text-[11px] font-medium uppercase tracking-[0.15em] text-positive">
              New
            </span>
          )}
          {term && (
            <span className="border border-input px-2 py-0.5 font-sans text-[11px] uppercase tracking-[0.12em] text-foreground">
              {term}
            </span>
          )}
          {restrictions.map((r) => (
            <span key={r.value} className="bg-warning-bg px-2 py-0.5 font-sans text-[11px] font-medium text-warning">
              {r.value}
            </span>
          ))}
          {job.experience_level && (
            <span className="border border-input px-2 py-0.5 font-sans text-[11px] uppercase tracking-[0.12em] text-foreground">
              {job.experience_level}
            </span>
          )}
          {job.sponsorship_flag === "likely_no" && (
            <span className="border border-input px-2 py-0.5 font-sans text-[11px] uppercase tracking-[0.12em] text-foreground">
              No Sponsorship
            </span>
          )}
          {job.sponsorship_flag === "likely_yes" && (
            <span className="bg-foreground px-2 py-0.5 font-sans text-[11px] uppercase tracking-[0.12em] text-background">
              Sponsors Visa
            </span>
          )}
          {pay && (
            <span className="font-sans text-xs font-medium text-foreground">
              {pay}
            </span>
          )}
          {job.employment_type && (
            <span className="border border-border-light px-2 py-0.5 font-sans text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              {job.employment_type}
            </span>
          )}
          {department && (
            <span className="font-sans text-[11px] uppercase tracking-[0.08em] text-muted-foreground truncate max-w-[180px]">{department}</span>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between border-t border-border-light pt-3">
          {age ? (
            // Compact "3d ago" for sighted readers; the full "Posted Sep 22, 2026" /
            // "First seen by Chronicle Sep 22, 2026" for screen readers and on hover.
            <time
              dateTime={age.iso}
              title={age.label}
              className="font-sans text-[11px] uppercase tracking-[0.08em] text-muted-foreground"
            >
              {/* Only this text depends on the clock; if a caller omitted `now`, let the
                  client's value win instead of throwing a hydration error. */}
              <span aria-hidden="true" suppressHydrationWarning>
                {age.relative ?? age.absolute}
              </span>
              <span className="sr-only normal-case">{age.label}</span>
            </time>
          ) : (
            <span />
          )}
          <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
            className="pointer-events-auto inline-flex min-h-[24px] items-center font-sans text-[11px] uppercase tracking-[0.15em] text-foreground underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2">
            Apply →
          </a>
        </div>
        </>)}
      </div>
    </m.article>
  );
}
