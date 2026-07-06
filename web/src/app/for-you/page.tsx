"use client";
import { useState, useEffect } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import { m, AnimatePresence, useReducedMotion } from "motion/react";
import { JobCard } from "@/components/JobCard";
import { JobListSkeleton } from "@/components/JobCardSkeleton";
import { SectionLabel } from "@/components/SectionLabel";
import { duration, ease, staggerContainer, staggerItem } from "@/lib/motion";
import type { JobListItem } from "@/lib/api";

interface Rec { job: JobListItem; score: number; why: string; }

const CTA_BUTTON =
  "inline-flex min-h-[44px] items-center border-2 border-foreground bg-foreground px-8 font-mono text-xs font-medium uppercase tracking-[0.2em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px]";

export default function ForYouPage() {
  const { data: session, status } = useSession();
  const reduce = useReducedMotion();
  const [recs, setRecs] = useState<Rec[]>([]);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
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
        <button onClick={() => signIn("google")} className={CTA_BUTTON}>
          Sign in with Google
        </button>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <SectionLabel>For You</SectionLabel>
        <h1 className="font-display text-4xl text-foreground mt-4 mb-8">Your top matches</h1>
        <JobListSkeleton count={5} />
      </main>
    );
  }

  if (hasProfile === false) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-32 text-center">
        <p className="font-display text-3xl text-foreground mb-3">Tell us what you're looking for</p>
        <p className="font-body text-muted-foreground mb-8">Answer 6 quick questions and we'll surface the roles most likely to fit.</p>
        <Link href="/onboarding" className={CTA_BUTTON}>
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
        <Link href="/onboarding" className="font-body text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0 underline-offset-4 hover:underline">
          Edit profile →
        </Link>
      </div>

      {recs.filter((r) => !dismissed.has(r.job.id)).length === 0 ? (
        <div className="text-center py-24">
          <p className="font-display text-2xl text-foreground mb-2">No matches yet</p>
          <p className="font-body text-muted-foreground mb-6">Try updating your profile with more tracks or skills.</p>
          <Link href="/onboarding" className="font-body text-sm text-foreground underline underline-offset-4 hover:no-underline">Update profile →</Link>
        </div>
      ) : (
        <m.div
          className="flex flex-col gap-4"
          variants={staggerContainer}
          initial={reduce ? false : "hidden"}
          animate="visible"
        >
          <AnimatePresence initial={false}>
            {recs
              .filter((r) => !dismissed.has(r.job.id))
              .map(({ job, why }) => (
                <m.div
                  key={job.id}
                  variants={staggerItem}
                  // Dismiss slides the card out (transform/opacity only); the list
                  // re-flows into the gap. Reduced-motion just fades.
                  exit={reduce ? { opacity: 0 } : { opacity: 0, x: 24 }}
                  transition={{ duration: duration.base, ease }}
                >
                  <JobCard
                    job={job}
                    why={why}
                    surface="feed"
                    onDismiss={() => setDismissed((d) => new Set(d).add(job.id))}
                  />
                </m.div>
              ))}
          </AnimatePresence>
        </m.div>
      )}

      <div className="mt-12 text-center">
        <p className="font-mono text-xs text-muted-foreground">
          Matched from your profile, resume, and activity — every card says why.{" "}
          <Link href="/settings" className="text-foreground underline underline-offset-4 hover:no-underline">Refine your profile</Link>
        </p>
      </div>
    </main>
  );
}
