"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

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

type Step = "tracks" | "seniority" | "remote" | "skills" | "sponsor";

const STEPS: Step[] = ["tracks", "seniority", "remote", "skills", "sponsor"];

function Toggle({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`min-h-[44px] rounded-md border px-4 py-2 font-body text-sm transition-all ${
        active
          ? "border-accent bg-accent/10 text-accent"
          : "border-border text-foreground hover:border-accent"
      }`}
    >
      {label}
    </button>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const [step, setStep] = useState(0);
  const [tracks, setTracks] = useState<string[]>([]);
  const [seniority, setSeniority] = useState<string[]>([]);
  const [remotePref, setRemotePref] = useState("any");
  const [skills, setSkills] = useState<string[]>([]);
  const [customSkill, setCustomSkill] = useState("");
  const [needsSponsorship, setNeedsSponsorship] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  const current = STEPS[step];

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
      }),
    });
    setSaving(false);
    router.push("/for-you");
  };

  return (
    <main className="mx-auto max-w-xl px-6 py-20">
      {/* Progress */}
      <div className="mb-12 flex gap-1.5">
        {STEPS.map((_, i) => (
          <div key={i} className={`h-0.5 flex-1 rounded-full transition-colors ${i <= step ? "bg-accent" : "bg-border"}`} />
        ))}
      </div>

      {current === "tracks" && (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-accent mb-3">Step 1 of 5</p>
          <h1 className="font-display text-4xl text-foreground mb-2">What do you work on?</h1>
          <p className="font-body text-muted-foreground mb-8">Select all tracks that apply.</p>
          <div className="flex flex-wrap gap-3">
            {TRACKS.map((t) => <Toggle key={t.key} label={t.label} active={tracks.includes(t.key)} onClick={() => toggle(tracks, setTracks, t.key)} />)}
          </div>
        </div>
      )}

      {current === "seniority" && (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-accent mb-3">Step 2 of 5</p>
          <h1 className="font-display text-4xl text-foreground mb-2">Where are you in your career?</h1>
          <p className="font-body text-muted-foreground mb-8">Select all that apply.</p>
          <div className="flex flex-wrap gap-3">
            {SENIORITY.map((s) => <Toggle key={s.key} label={s.label} active={seniority.includes(s.key)} onClick={() => toggle(seniority, setSeniority, s.key)} />)}
          </div>
        </div>
      )}

      {current === "remote" && (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-accent mb-3">Step 3 of 5</p>
          <h1 className="font-display text-4xl text-foreground mb-2">Remote or on-site?</h1>
          <p className="font-body text-muted-foreground mb-8">We'll use this to rank your recommendations.</p>
          <div className="flex flex-wrap gap-3">
            {REMOTE_PREFS.map((r) => <Toggle key={r.key} label={r.label} active={remotePref === r.key} onClick={() => setRemotePref(r.key)} />)}
          </div>
        </div>
      )}

      {current === "skills" && (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-accent mb-3">Step 4 of 5</p>
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
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 font-body text-sm focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
        </div>
      )}

      {current === "sponsor" && (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-accent mb-3">Step 5 of 5</p>
          <h1 className="font-display text-4xl text-foreground mb-2">Do you need visa sponsorship?</h1>
          <p className="font-body text-muted-foreground mb-8">We'll de-rank roles that mention sponsorship restrictions.</p>
          <div className="flex gap-4">
            {[{ v: false, label: "No" }, { v: true, label: "Yes" }, { v: null, label: "Prefer not to say" }].map(({ v, label }) => (
              <Toggle key={label} label={label} active={needsSponsorship === v} onClick={() => setNeedsSponsorship(v)} />
            ))}
          </div>
        </div>
      )}

      {/* Nav */}
      <div className="mt-12 flex items-center justify-between">
        <button
          onClick={() => setStep((s) => s - 1)}
          disabled={step === 0}
          className="font-body text-sm text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
        >
          ← Back
        </button>
        {step < STEPS.length - 1 ? (
          <button
            onClick={() => setStep((s) => s + 1)}
            className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all"
          >
            Continue →
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="inline-flex min-h-[44px] items-center rounded-md bg-accent px-8 font-body text-sm font-medium text-white hover:bg-accent-secondary transition-all disabled:opacity-60"
          >
            {saving ? "Saving…" : "See my matches →"}
          </button>
        )}
      </div>
    </main>
  );
}
