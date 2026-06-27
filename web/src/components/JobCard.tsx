"use client";
import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { cn, formatDate } from "@/lib/utils";
import type { JobListItem } from "@/lib/api";

interface Props {
  job: JobListItem;
  initialSaved?: boolean;
  initialTracked?: boolean;
  why?: string;
}

const EXPERIENCE_COLORS: Record<string, string> = {
  Internship: "text-blue-600 border-blue-200 bg-blue-50",
  "Entry Level": "text-green-700 border-green-200 bg-green-50",
  "Mid Level": "text-foreground border-border",
  Senior: "text-accent border-amber-200 bg-amber-50",
  Management: "text-purple-700 border-purple-200 bg-purple-50",
};

export function JobCard({ job, initialSaved = false, initialTracked = false, why }: Props) {
  const { data: session } = useSession();
  const isAuthed = !!session?.user?.email;

  const [saved, setSaved] = useState(initialSaved);
  const [tracked, setTracked] = useState(initialTracked);
  const [loadingS, setLoadingS] = useState(false);
  const [loadingT, setLoadingT] = useState(false);

  useEffect(() => {
    if (isAuthed) return;
    try {
      const bm = JSON.parse(localStorage.getItem("chronicle_bookmarks") || "[]") as number[];
      setSaved(bm.includes(job.id));
      const tr = JSON.parse(localStorage.getItem("chronicle_tracker") || "[]") as Array<{ job: { id: number } }>;
      setTracked(tr.some((t) => t.job.id === job.id));
    } catch {}
  }, [job.id, isAuthed]);

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
      setSaved(!saved);
    } finally {
      setLoadingS(false);
    }
  }, [saved, job.id, isAuthed, loadingS]);

  const addToTracker = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    if (loadingT || tracked) return;
    if (!isAuthed) {
      try {
        const tr = JSON.parse(localStorage.getItem("chronicle_tracker") || "[]") as Array<{ job: JobListItem; status: string; addedAt: string }>;
        if (!tr.some((t) => t.job.id === job.id)) {
          tr.unshift({ job, status: "saved", addedAt: new Date().toISOString() });
          localStorage.setItem("chronicle_tracker", JSON.stringify(tr));
          setTracked(true);
        }
      } catch {}
      return;
    }
    setLoadingT(true);
    try {
      await fetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: job.id, status: "saved" }),
      });
      setTracked(true);
    } finally {
      setLoadingT(false);
    }
  }, [tracked, job, isAuthed, loadingT]);

  const expClass = job.experience_level
    ? (EXPERIENCE_COLORS[job.experience_level] ?? "text-muted-foreground border-border")
    : "";

  return (
    <article className="group relative rounded-lg border border-border border-t-2 border-t-accent bg-card shadow-sm transition-all duration-200 hover:shadow-md">
      <Link href={`/jobs/${job.id}`} className="absolute inset-0 rounded-lg z-0" aria-label={`${job.title} at ${job.company_name}`} />
      <div className="relative z-10 p-5 pointer-events-none">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-display text-lg leading-snug text-foreground line-clamp-2 group-hover:text-accent transition-colors">
              {job.title}
            </h3>
            <p className="mt-1 font-body text-sm text-muted-foreground">
              {job.company_name}
              {job.location_normalized && <span> · {job.location_normalized}</span>}
              {job.remote && <span> · Remote</span>}
            </p>
          </div>

          <div className="flex items-center gap-1 shrink-0 pointer-events-auto">
            <button onClick={addToTracker} title={tracked ? "In tracker" : "Add to tracker"} disabled={loadingT}
              className={cn("p-1.5 rounded transition-colors", tracked ? "text-accent" : "text-muted-foreground hover:text-accent")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill={tracked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
              </svg>
            </button>
            <button onClick={toggleSave} title={saved ? "Remove bookmark" : "Bookmark"} disabled={loadingS}
              className={cn("p-1.5 rounded transition-colors", saved ? "text-accent" : "text-muted-foreground hover:text-accent")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
              </svg>
            </button>
          </div>
        </div>

        {why && <p className="mt-2 font-body text-xs text-accent/80 italic">{why}</p>}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {job.is_new && (
            <span className="font-mono text-[10px] uppercase tracking-[0.15em] border border-accent text-accent px-2 py-0.5 rounded">New</span>
          )}
          {job.experience_level && (
            <span className={cn("font-mono text-[10px] uppercase tracking-[0.12em] border px-2 py-0.5 rounded", expClass)}>
              {job.experience_level}
            </span>
          )}
          {(job as any).sponsorship_flag === "likely_no" && (
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] border border-orange-200 text-orange-600 bg-orange-50 px-2 py-0.5 rounded">
              No Sponsorship
            </span>
          )}
          {(job as any).salary_min && (
            <span className="font-mono text-[10px] text-muted-foreground">
              ${Math.round((job as any).salary_min / 1000)}k{(job as any).salary_max ? `–$${Math.round((job as any).salary_max / 1000)}k` : "+"}
            </span>
          )}
          {job.employment_type && (
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] border border-border text-muted-foreground px-2 py-0.5 rounded">
              {job.employment_type}
            </span>
          )}
          {job.department && (
            <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[160px]">{job.department}</span>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between">
          <span className="font-mono text-[10px] text-muted-foreground">
            {formatDate(job.posted_at ?? job.first_seen_at)}
          </span>
          <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
            className="pointer-events-auto font-body text-xs text-accent hover:underline">
            Apply →
          </a>
        </div>
      </div>
    </article>
  );
}
