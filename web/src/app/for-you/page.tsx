"use client";
import { useState, useEffect } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import { JobCard } from "@/components/JobCard";
import { SectionLabel } from "@/components/SectionLabel";
import type { JobListItem } from "@/lib/api";

interface Rec { job: JobListItem; score: number; why: string; }

export default function ForYouPage() {
  const { data: session, status } = useSession();
  const [recs, setRecs] = useState<Rec[]>([]);
  const [hasProfile, setHasProfile] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated") { setLoading(false); return; }

    fetch("/api/user/profile")
      .then((r) => r.json())
      .then(async (profile) => {
        if (!profile || !profile.tracks?.length) {
          setHasProfile(false);
          setLoading(false);
          return;
        }
        setHasProfile(true);
        const recsRes = await fetch("/api/recommendations");
        const data = await recsRes.json();
        if (Array.isArray(data)) setRecs(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [status, session]);

  if (status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-32 text-center">
        <p className="font-display text-3xl text-foreground mb-4">Sign in to see your matches</p>
        <button onClick={() => signIn("google")} className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all">
          Sign in with Google
        </button>
      </main>
    );
  }

  if (loading) {
    return <main className="mx-auto max-w-3xl px-6 py-32 text-center"><p className="font-body text-muted-foreground">Loading your matches…</p></main>;
  }

  if (hasProfile === false) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-32 text-center">
        <p className="font-display text-3xl text-foreground mb-3">Tell us what you're looking for</p>
        <p className="font-body text-muted-foreground mb-8">Answer 5 quick questions and we'll surface the roles most likely to fit.</p>
        <Link href="/onboarding" className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all">
          Set up my profile →
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <div className="flex items-center justify-between mb-8">
        <div>
          <SectionLabel>For You</SectionLabel>
          <h1 className="font-display text-4xl text-foreground mt-4">Your top matches</h1>
          <p className="mt-2 font-body text-sm text-muted-foreground">
            Scored by track fit, shared skills, seniority, and recency. Every match shows why it ranked.
          </p>
        </div>
        <Link href="/onboarding" className="font-body text-xs text-muted-foreground hover:text-accent transition-colors shrink-0">
          Edit profile →
        </Link>
      </div>

      {recs.length === 0 ? (
        <div className="text-center py-24">
          <p className="font-display text-2xl text-foreground mb-2">No matches yet</p>
          <p className="font-body text-muted-foreground mb-6">Try updating your profile with more tracks or skills.</p>
          <Link href="/onboarding" className="font-body text-sm text-accent hover:underline">Update profile →</Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {recs.map(({ job, why }) => (
            <JobCard key={job.id} job={job} why={why} />
          ))}
        </div>
      )}

      <div className="mt-12 text-center">
        <p className="font-mono text-xs text-muted-foreground">
          Scores are computed from your profile — no ML, fully explainable.{" "}
          <Link href="/onboarding" className="text-accent hover:underline">Refine your profile</Link>
        </p>
      </div>
    </main>
  );
}
