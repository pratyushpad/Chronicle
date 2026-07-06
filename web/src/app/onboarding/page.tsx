"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { m, AnimatePresence, useReducedMotion, type Variants } from "motion/react";
import { cn } from "@/lib/utils";
import { duration, ease, springPress } from "@/lib/motion";

const TRACKS = [
  { key: "swe", label: "Software Engineering" },
  { key: "ml", label: "ML / AI" },
  { key: "data", label: "Data" },
  { key: "devops", label: "DevOps / Platform" },
  { key: "security", label: "Security" },
  { key: "design", label: "Design" },
  { key: "product", label: "Product" },
  { key: "research", label: "Research" },
  { key: "robotics", label: "Robotics / Embedded" },
];

const SENIORITY = [
  { key: "intern", label: "Intern" },
  { key: "new_grad", label: "New Grad" },
  { key: "mid", label: "Mid-Level" },
  { key: "senior", label: "Senior" },
  { key: "management", label: "Management" },
];

const REMOTE_PREFS = [
  { key: "any", label: "Anywhere" },
  { key: "remote", label: "Remote only" },
  { key: "hybrid", label: "Hybrid" },
  { key: "onsite", label: "On-site" },
];

const COMMON_SKILLS = [
  "Python", "TypeScript", "Java", "Go", "Rust", "React", "Next.js",
  "PyTorch", "TensorFlow", "AWS", "GCP", "Kubernetes", "PostgreSQL",
  "Spark", "Kafka", "dbt", "ROS2", "CUDA",
];

type Step = "tracks" | "seniority" | "remote" | "skills" | "about" | "sponsor";

const STEPS: Step[] = ["tracks", "seniority", "remote", "skills", "about", "sponsor"];

const inputClass =
  "w-full border border-foreground bg-background px-3 py-2 font-body text-sm text-foreground placeholder:italic placeholder:text-muted-foreground focus:outline-none focus:border-2";

function Toggle({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  const reduce = useReducedMotion();
  return (
    <m.button
      onClick={onClick}
      whileTap={reduce ? undefined : { scale: 0.96 }}
      transition={springPress}
      aria-pressed={active}
      className={cn(
        "min-h-[44px] border px-4 py-2 font-body text-sm transition-colors duration-100 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2",
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border-light text-foreground hover:border-foreground"
      )}
    >
      {label}
    </m.button>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const reduce = useReducedMotion();

  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const [tracks, setTracks] = useState<string[]>([]);
  const [seniority, setSeniority] = useState<string[]>([]);
  const [remotePref, setRemotePref] = useState("any");
  const [skills, setSkills] = useState<string[]>([]);
  const [customSkill, setCustomSkill] = useState("");
  const [needsSponsorship, setNeedsSponsorship] = useState<boolean | null>(null);
  const [about, setAbout] = useState("");
  const [saving, setSaving] = useState(false);

  const current = STEPS[step];

  const go = (delta: number) => {
    setDirection(delta);
    setStep((s) => s + delta);
  };

  const toggle = <T extends string>(arr: T[], set: (v: T[]) => void, val: T) => {
    set(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  };

  const handleSubmit = async () => {
    setSaving(true);
    await fetch("/api/user/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: session?.user?.name ?? null,
        tracks,
        seniority_pref: seniority,
        remote_pref: remotePref,
        tech_tags: skills,
        needs_sponsorship: needsSponsorship,
        about: about.trim() || null,
      }),
    });
    setSaving(false);
    router.push("/for-you");
  };

  // Direction-aware slide: forward enters from the right, back from the left.
  const stepVariants: Variants = {
    enter: (dir: number) => (reduce ? { opacity: 0 } : { opacity: 0, x: dir > 0 ? 24 : -24 }),
    center: { opacity: 1, x: 0 },
    exit: (dir: number) => (reduce ? { opacity: 0 } : { opacity: 0, x: dir > 0 ? -24 : 24 }),
  };

  const stepLabel = (
    <p className="font-mono text-xs uppercase tracking-[0.15em] text-foreground mb-3">
      Step {step + 1} of {STEPS.length}
    </p>
  );

  const stepContent = (
    <>
      {current === "tracks" && (
        <div>
          {stepLabel}
          <h1 className="font-display text-4xl text-foreground mb-2">What do you work on?</h1>
          <p className="font-body text-muted-foreground mb-8">Select all tracks that apply.</p>
          <div className="flex flex-wrap gap-3">
            {TRACKS.map((t) => <Toggle key={t.key} label={t.label} active={tracks.includes(t.key)} onClick={() => toggle(tracks, setTracks, t.key)} />)}
          </div>
        </div>
      )}

      {current === "seniority" && (
        <div>
          {stepLabel}
          <h1 className="font-display text-4xl text-foreground mb-2">Where are you in your career?</h1>
          <p className="font-body text-muted-foreground mb-8">Select all that apply.</p>
          <div className="flex flex-wrap gap-3">
            {SENIORITY.map((s) => <Toggle key={s.key} label={s.label} active={seniority.includes(s.key)} onClick={() => toggle(seniority, setSeniority, s.key)} />)}
          </div>
        </div>
      )}

      {current === "remote" && (
        <div>
          {stepLabel}
          <h1 className="font-display text-4xl text-foreground mb-2">Remote or on-site?</h1>
          <p className="font-body text-muted-foreground mb-8">We'll use this to rank your recommendations.</p>
          <div className="flex flex-wrap gap-3">
            {REMOTE_PREFS.map((r) => <Toggle key={r.key} label={r.label} active={remotePref === r.key} onClick={() => setRemotePref(r.key)} />)}
          </div>
        </div>
      )}

      {current === "skills" && (
        <div>
          {stepLabel}
          <h1 className="font-display text-4xl text-foreground mb-2">Your tech stack</h1>
          <p className="font-body text-muted-foreground mb-8">Pick skills from your resume — we'll match them against job requirements.</p>
          <div className="flex flex-wrap gap-3 mb-6">
            {COMMON_SKILLS.map((s) => <Toggle key={s} label={s} active={skills.includes(s.toLowerCase())} onClick={() => toggle(skills, setSkills, s.toLowerCase())} />)}
          </div>
          <div className="flex gap-2">
            <input
              value={customSkill}
              onChange={(e) => setCustomSkill(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && customSkill.trim()) {
                  toggle(skills, setSkills, customSkill.trim().toLowerCase());
                  setCustomSkill("");
                }
              }}
              placeholder="Add a skill (press Enter)"
              className={inputClass}
            />
          </div>
        </div>
      )}

      {current === "about" && (
        <div>
          {stepLabel}
          <h1 className="font-display text-4xl text-foreground mb-2">What are you looking for?</h1>
          <p className="font-body text-muted-foreground mb-8">
            In your own words — team size, problem space, dealbreakers. This feeds your matches
            directly. Optional, and you can add a resume later in Settings.
          </p>
          <textarea
            value={about}
            onChange={(e) => setAbout(e.target.value)}
            placeholder="e.g. Early-stage startups doing systems or ML infra work. Small teams, high ownership. Not interested in crypto or adtech."
            className={cn(inputClass, "h-36 resize-y")}
          />
        </div>
      )}

      {current === "sponsor" && (
        <div>
          {stepLabel}
          <h1 className="font-display text-4xl text-foreground mb-2">Do you need visa sponsorship?</h1>
          <p className="font-body text-muted-foreground mb-8">We'll de-rank roles that mention sponsorship restrictions.</p>
          <div className="flex gap-4">
            {[{ v: false, label: "No" }, { v: true, label: "Yes" }, { v: null, label: "Prefer not to say" }].map(({ v, label }) => (
              <Toggle key={label} label={label} active={needsSponsorship === v} onClick={() => setNeedsSponsorship(v)} />
            ))}
          </div>
        </div>
      )}
    </>
  );

  return (
    <main className="mx-auto max-w-xl px-6 py-20">
      {/* Progress — each segment's black fill draws in as you advance. */}
      <div className="mb-12 flex gap-1.5">
        {STEPS.map((_, i) => (
          <div key={i} className="h-0.5 flex-1 overflow-hidden bg-border-light">
            <m.div
              className="h-full w-full origin-left bg-foreground"
              initial={false}
              animate={{ scaleX: i <= step ? 1 : 0 }}
              transition={{ duration: duration.base, ease }}
            />
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait" custom={direction} initial={false}>
        <m.div
          key={step}
          custom={direction}
          variants={stepVariants}
          initial="enter"
          animate="center"
          exit="exit"
          transition={{ duration: duration.base, ease }}
        >
          {stepContent}
        </m.div>
      </AnimatePresence>

      {/* Nav */}
      <div className="mt-12 flex items-center justify-between">
        <button
          onClick={() => go(-1)}
          disabled={step === 0}
          className="font-body text-sm text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
        >
          ← Back
        </button>
        {step < STEPS.length - 1 ? (
          <button
            onClick={() => go(1)}
            className="inline-flex min-h-[44px] items-center border-2 border-foreground bg-foreground px-8 font-mono text-xs font-medium uppercase tracking-[0.2em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px]"
          >
            Continue →
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="inline-flex min-h-[44px] items-center border-2 border-foreground bg-foreground px-8 font-mono text-xs font-medium uppercase tracking-[0.2em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground disabled:opacity-60 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-[3px]"
          >
            {saving ? "Saving…" : "See my matches →"}
          </button>
        )}
      </div>
    </main>
  );
}
