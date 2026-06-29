"use client";
import { useState, useEffect } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import { JobCard } from "@/components/JobCard";
import { SectionLabel } from "@/components/SectionLabel";

export default function SavedPage() {
  const { data: session, status } = useSession();
  const [saved, setSaved] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [alertSearch, setAlertSearch] = useState("");
  const [alertFreq, setAlertFreq] = useState<"daily" | "weekly">("daily");
  const [alertCreated, setAlertCreated] = useState(false);
  const [searches, setSearches] = useState<any[]>([]);

  useEffect(() => {
    if (status !== "authenticated") { setLoading(false); return; }
    Promise.all([
      fetch("/api/saved").then((r) => r.json()),
      fetch("/api/searches").then((r) => r.json()),
    ]).then(([s, q]) => {
      setSaved(Array.isArray(s) ? s : []);
      setSearches(Array.isArray(q) ? q : []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [status]);

  const createAlert = async () => {
    if (!alertSearch.trim()) return;
    const res = await fetch("/api/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: alertSearch.trim(),
        query_json: { q: alertSearch.trim() },
        alert_frequency: alertFreq,
      }),
    });
    if (res.ok) {
      const s = await res.json();
      setSearches((prev) => [s, ...prev]);
      setAlertSearch("");
      setAlertCreated(true);
      setTimeout(() => setAlertCreated(false), 3000);
    }
  };

  const deleteSearch = async (id: number) => {
    await fetch("/api/searches", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    setSearches((prev) => prev.filter((s) => s.id !== id));
  };

  if (status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-32 text-center">
        <p className="font-display text-3xl text-foreground mb-4">Sign in to view saved jobs</p>
        <button onClick={() => signIn("google")} className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all">
          Sign in with Google
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <SectionLabel className="mb-8">Saved Jobs</SectionLabel>

      {/* Email alerts box */}
      <div className="mb-12 rounded-lg border border-border bg-card p-6">
        <h2 className="font-display text-xl text-foreground mb-1">Email alerts</h2>
        <p className="font-body text-sm text-muted-foreground mb-4">
          Get notified when new roles match a keyword — sent after each ingest run.
        </p>
        <div className="flex gap-3 flex-wrap">
          <input
            value={alertSearch}
            onChange={(e) => setAlertSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createAlert()}
            placeholder="e.g. Machine Learning Engineer"
            className="flex-1 min-w-[200px] rounded-md border border-border bg-background px-3 py-2 font-body text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <select
            value={alertFreq}
            onChange={(e) => setAlertFreq(e.target.value as any)}
            className="rounded-md border border-border bg-background px-3 py-2 font-body text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <option value="daily">Daily digest</option>
            <option value="weekly">Weekly digest</option>
          </select>
          <button onClick={createAlert}
            className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-5 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all">
            {alertCreated ? "✓ Alert set" : "Set alert"}
          </button>
        </div>

        {searches.length > 0 && (
          <div className="mt-4 space-y-2">
            {searches.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded border border-border px-3 py-2">
                <span className="font-body text-sm text-foreground">{s.name}</span>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-accent">{s.alert_frequency}</span>
                  <button onClick={() => deleteSearch(s.id)} className="font-mono text-xs text-muted-foreground hover:text-foreground">✕</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Saved jobs list */}
      {loading ? (
        <p className="font-body text-muted-foreground">Loading…</p>
      ) : saved.length === 0 ? (
        <div className="text-center py-16">
          <p className="font-display text-2xl text-foreground mb-2">No saved jobs yet</p>
          <p className="font-body text-muted-foreground mb-6">Click the bookmark icon on any role to save it here.</p>
          <Link href="/jobs" className="font-body text-sm text-accent hover:underline">Browse roles →</Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {saved.map((s) => (
            <JobCard key={s.job_id} job={s.job} initialSaved={true} />
          ))}
        </div>
      )}
    </main>
  );
}
