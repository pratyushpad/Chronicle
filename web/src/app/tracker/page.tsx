"use client";
import { useState, useEffect, useCallback } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";

type AppStatus = "saved" | "applied" | "interviewing" | "offer" | "rejected" | "archived";

interface TrackedApp {
  id: number;
  job_id: number;
  status: AppStatus;
  notes: string | null;
  next_action: string | null;
  applied_at: string | null;
  updated_at: string;
  job: { id: number; title: string; company_name: string; apply_url: string };
}

const COLUMNS: { key: AppStatus; label: string }[] = [
  { key: "saved", label: "Saved" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
];

const NEXT_STATUS: Partial<Record<AppStatus, AppStatus>> = {
  saved: "applied",
  applied: "interviewing",
  interviewing: "offer",
};

export default function TrackerPage() {
  const { data: session, status } = useSession();
  const [apps, setApps] = useState<TrackedApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    if (status !== "authenticated") { setLoading(false); return; }
    const res = await fetch("/api/applications");
    if (res.ok) setApps(await res.json());
    setLoading(false);
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (appId: number, newStatus: AppStatus) => {
    const res = await fetch(`/api/applications/${appId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (res.ok) setApps((prev) => prev.map((a) => a.id === appId ? { ...a, status: newStatus } : a));
  };

  const saveNotes = async (appId: number) => {
    const note = notes[appId];
    if (note === undefined) return;
    await fetch(`/api/applications/${appId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: note }),
    });
    setApps((prev) => prev.map((a) => a.id === appId ? { ...a, notes: note } : a));
    setNotes((p) => { const n = { ...p }; delete n[appId]; return n; });
  };

  const remove = async (appId: number) => {
    await fetch(`/api/applications/${appId}`, { method: "DELETE" });
    setApps((prev) => prev.filter((a) => a.id !== appId));
  };

  if (status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-32 text-center">
        <p className="font-display text-3xl text-foreground mb-4">Sign in to track applications</p>
        <p className="font-body text-muted-foreground mb-8">Your tracker syncs across devices when you're signed in.</p>
        <button onClick={() => signIn("google")}
          className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all">
          Sign in with Google
        </button>
      </main>
    );
  }

  const funnel = { total: apps.length, applied: apps.filter((a) => a.status === "applied").length, interviewing: apps.filter((a) => a.status === "interviewing").length, offers: apps.filter((a) => a.status === "offer").length };

  return (
    <main className="px-4 py-12">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center justify-between mb-6">
          <h1 className="font-display text-3xl text-foreground">Application Tracker</h1>
          <Link href="/jobs" className="font-body text-sm text-accent hover:underline">+ Add roles →</Link>
        </div>

        {funnel.total > 0 && (
          <div className="flex gap-8 mb-10">
            {[{ label: "Total", v: funnel.total }, { label: "Applied", v: funnel.applied }, { label: "Interviewing", v: funnel.interviewing }, { label: "Offers", v: funnel.offers }].map(({ label, v }) => (
              <div key={label} className="text-center">
                <div className="font-display text-2xl text-accent">{v}</div>
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        )}

        {loading ? (
          <div className="font-body text-muted-foreground">Loading…</div>
        ) : apps.length === 0 ? (
          <div className="text-center py-24">
            <p className="font-display text-2xl text-foreground mb-2">No applications yet</p>
            <p className="font-body text-muted-foreground mb-6">Bookmark any role to start tracking — it lands in your Saved column.</p>
            <Link href="/jobs" className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all">
              Browse Open Roles
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {COLUMNS.map(({ key, label }) => {
              const items = apps.filter((a) => a.status === key);
              return (
                <div key={key}>
                  <div className="mb-3 flex items-center gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">{label}</span>
                    <span className="font-mono text-[9px] text-muted-foreground">({items.length})</span>
                  </div>
                  <div className="space-y-3">
                    {items.map((app) => {
                      const next = NEXT_STATUS[app.status];
                      return (
                        <div key={app.id} className="rounded-lg border border-border border-t-2 border-t-accent bg-card p-4 shadow-sm">
                          <Link href={`/jobs/${app.job.id}`} className="block group">
                            <p className="font-display text-sm leading-snug text-foreground group-hover:text-accent transition-colors line-clamp-2">{app.job.title}</p>
                            <p className="mt-0.5 font-body text-xs text-muted-foreground">{app.job.company_name}</p>
                          </Link>
                          <textarea
                            placeholder="Notes…"
                            value={notes[app.id] ?? app.notes ?? ""}
                            onChange={(e) => setNotes((p) => ({ ...p, [app.id]: e.target.value }))}
                            onBlur={() => saveNotes(app.id)}
                            rows={2}
                            className="mt-3 w-full resize-none rounded border border-border bg-background px-2 py-1.5 font-body text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-accent"
                          />
                          <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                            {next && (
                              <button onClick={() => updateStatus(app.id, next)}
                                className="font-mono text-[9px] uppercase tracking-[0.1em] px-2 py-1 rounded border border-accent text-accent hover:bg-accent hover:text-white transition-colors">
                                → {next}
                              </button>
                            )}
                            {app.status !== "rejected" && (
                              <button onClick={() => updateStatus(app.id, "rejected")}
                                className="font-mono text-[9px] uppercase tracking-[0.1em] px-2 py-1 border border-border text-muted-foreground hover:text-foreground transition-colors">
                                Reject
                              </button>
                            )}
                            <a href={app.job.apply_url} target="_blank" rel="noopener noreferrer"
                              className="ml-auto font-mono text-[9px] text-accent hover:underline">Apply →</a>
                            <button onClick={() => remove(app.id)} className="font-mono text-[9px] text-muted-foreground hover:text-foreground transition-colors">✕</button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
