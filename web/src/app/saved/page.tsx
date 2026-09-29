"use client";
import { useState, useEffect } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import { JobCard } from "@/components/JobCard";
import { SectionLabel } from "@/components/SectionLabel";
import { getMeta, type JobListItem } from "@/lib/api";

// Shapes of the API's SavedJobOut and SavedSearchOut (the Next routes pass them through).
interface SavedJob {
  job_id: number;
  job: JobListItem;
}
interface SavedSearch {
  id: number;
  name: string;
  alert_frequency: "off" | "daily" | "weekly";
}

const CTA_BUTTON =
  "inline-flex min-h-[44px] items-center border border-input bg-foreground px-8 font-sans text-xs font-medium uppercase tracking-[0.2em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px]";
const INPUT_CLS =
  "border border-input bg-background px-3 py-2 font-sans text-sm text-foreground focus:outline-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2";
const LABEL_CLS = "font-sans text-[11px] uppercase tracking-[0.15em] text-muted-foreground";

export default function SavedPage() {
  const { data: session, status } = useSession();
  const [saved, setSaved] = useState<SavedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [alertSearch, setAlertSearch] = useState("");
  const [alertFreq, setAlertFreq] = useState<"daily" | "weekly">("daily");
  const [alertCreated, setAlertCreated] = useState(false);
  const [alertHint, setAlertHint] = useState(false);
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  // Email digests only when the server can send them (/meta.email_alerts); until then the
  // page promises in-app notifications only. Unknown (loading, older API) counts as no.
  const [emailAlerts, setEmailAlerts] = useState(false);

  useEffect(() => {
    getMeta()
      .then((m) => setEmailAlerts(m.email_alerts === true))
      .catch(() => setEmailAlerts(false));
  }, []);

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
    if (!alertSearch.trim()) { setAlertHint(true); return; }
    setAlertHint(false);
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
        <button onClick={() => signIn("google")} className={CTA_BUTTON}>
          Sign in with Google
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <SectionLabel className="mb-8">Saved Jobs</SectionLabel>

      {/* Alerts box */}
      <div className="mb-12 border border-input p-6">
        <h2 className="font-display text-xl text-foreground mb-1">Alerts</h2>
        <p className="font-sans text-sm text-muted-foreground mb-4">
          When new roles match a keyword after an ingest run, you get an in-app
          notification{emailAlerts ? " and an email digest" : ""}.
        </p>
        <div className="flex gap-3 flex-wrap">
          <input
            value={alertSearch}
            onChange={(e) => { setAlertSearch(e.target.value); if (alertHint) setAlertHint(false); }}
            onKeyDown={(e) => e.key === "Enter" && createAlert()}
            placeholder="e.g. Machine Learning Engineer"
            className={`${INPUT_CLS} flex-1 min-w-[200px]`}
          />
          <select
            value={alertFreq}
            onChange={(e) => setAlertFreq(e.target.value === "weekly" ? "weekly" : "daily")}
            className={INPUT_CLS}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
          <button
            onClick={createAlert}
            disabled={!alertSearch.trim()}
            className="inline-flex min-h-[44px] items-center bg-foreground px-5 font-sans text-xs font-medium uppercase tracking-[0.12em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground hover:shadow-[inset_0_0_0_2px_var(--foreground)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {alertCreated ? "✓ Alert set" : "Set alert"}
          </button>
        </div>
        {alertHint && (
          <p className={`mt-2 ${LABEL_CLS}`}>Enter a keyword to set an alert.</p>
        )}

        {searches.length > 0 && (
          <div className="mt-4 space-y-2">
            {searches.map((s) => (
              <div key={s.id} className="flex items-center justify-between border border-border-light px-3 py-2">
                <span className="font-sans text-sm text-foreground">{s.name}</span>
                <div className="flex items-center gap-3">
                  <span className={LABEL_CLS}>{s.alert_frequency}</span>
                  <button
                    onClick={() => deleteSearch(s.id)}
                    aria-label={`Delete alert ${s.name}`}
                    className="font-sans text-xs text-muted-foreground hover:text-foreground"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Saved jobs list */}
      {loading ? (
        <p className="font-sans text-muted-foreground">Loading…</p>
      ) : saved.length === 0 ? (
        <div className="text-center py-16">
          <p className="font-display text-2xl text-foreground mb-2">No saved jobs yet</p>
          <p className="font-sans text-muted-foreground mb-6">Click the bookmark icon on any role to save it here.</p>
          <Link href="/jobs" className="font-sans text-sm text-foreground underline underline-offset-4 hover:no-underline">Browse roles →</Link>
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
