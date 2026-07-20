"use client";
import { useEffect, useState } from "react";
import { useSession, signOut } from "next-auth/react";
import { SectionLabel } from "@/components/SectionLabel";
import { ResumeDropzone } from "@/components/ResumeDropzone";
import { cn } from "@/lib/utils";

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

const labelCls = "font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground";
const inputCls =
  "w-full border border-foreground bg-background px-3 py-2 font-body text-sm text-foreground focus:outline-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2";
const btnSolid =
  "inline-flex min-h-[36px] items-center justify-center bg-foreground px-5 font-mono text-xs font-medium uppercase tracking-[0.12em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground hover:shadow-[inset_0_0_0_2px_var(--foreground)] disabled:opacity-50";
const btnOutline =
  "inline-flex min-h-[36px] items-center justify-center border border-foreground px-5 font-mono text-xs uppercase tracking-[0.12em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background disabled:opacity-50";

interface Profile {
  location?: string | null;
  remote_pref?: string | null;
  seniority_pref?: string[] | null;
  tracks?: string[] | null;
  tech_tags?: string[] | null;
  salary_floor?: number | null;
  needs_sponsorship?: boolean | null;
  about?: string | null;
  resume_chars?: number | null;
  resume_updated_at?: string | null;
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "min-h-[40px] border px-4 py-1.5 font-body text-sm transition-colors duration-100 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2",
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border-light text-foreground hover:border-foreground",
      )}
    >
      {label}
    </button>
  );
}

export default function SettingsPage() {
  const { data: session, status } = useSession();

  const [profile, setProfile] = useState<Profile>({});
  const [customSkill, setCustomSkill] = useState("");
  const [savedMsg, setSavedMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status !== "authenticated") return;
    fetch("/api/user/profile")
      .then((r) => r.json())
      .then((d) => { if (d) setProfile(d); })
      .catch(() => {});
  }, [status]);

  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setProfile((p) => ({ ...p, [k]: v }));
  const toggleIn = (key: "tracks" | "seniority_pref" | "tech_tags", val: string) =>
    setProfile((p) => {
      const cur = p[key] ?? [];
      return { ...p, [key]: cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val] };
    });
  const addSkill = () => {
    const s = customSkill.trim();
    if (!s) return;
    setProfile((p) => ({ ...p, tech_tags: [...(p.tech_tags ?? []), s].filter((v, i, a) => a.indexOf(v) === i) }));
    setCustomSkill("");
  };

  const save = async () => {
    setBusy(true);
    setSavedMsg("");
    try {
      const res = await fetch("/api/user/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location: profile.location ?? null,
          remote_pref: profile.remote_pref ?? null,
          seniority_pref: profile.seniority_pref ?? [],
          tracks: profile.tracks ?? [],
          tech_tags: profile.tech_tags ?? [],
          salary_floor: profile.salary_floor ?? null,
          needs_sponsorship: profile.needs_sponsorship ?? null,
          about: profile.about ?? null,
        }),
      });
      setSavedMsg(res.ok ? "Saved." : "Save failed.");
    } catch {
      setSavedMsg("Save failed — check your connection.");
    } finally {
      setBusy(false);
    }
  };

  if (status === "loading") return <main className="mx-auto max-w-2xl px-6 py-20" />;
  if (status !== "authenticated") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-20">
        <p className="font-body text-muted-foreground">Sign in to manage your settings.</p>
      </main>
    );
  }

  const skillSet = new Set(profile.tech_tags ?? []);
  const customSkills = (profile.tech_tags ?? []).filter((s) => !COMMON_SKILLS.includes(s));

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="mb-2 font-display text-4xl text-foreground">Settings</h1>
      <p className="mb-12 font-body text-muted-foreground">
        Tune what powers your <strong className="text-foreground">For You</strong> feed and matches.
      </p>

      {/* ── Matching profile ── */}
      <section className="mb-16">
        <SectionLabel className="mb-6">Matching Profile</SectionLabel>
        <p className="mb-6 font-body text-sm text-muted-foreground">
          The more it knows, the better the matches.
        </p>

        <label className={`${labelCls} mb-1 block`}>What are you looking for?</label>
        <textarea
          className={`${inputCls} h-28 resize-y py-2`}
          placeholder="e.g. Early-stage startups doing systems or ML infra work. Small teams, high ownership. Not interested in crypto or adtech."
          value={profile.about ?? ""}
          onChange={(e) => set("about", e.target.value)}
        />
        <p className="mt-1 mb-6 font-body text-xs text-muted-foreground">
          Free text — it&rsquo;s embedded directly into your matching vector, so write it like you&rsquo;d tell a friend.
        </p>

        <label className={`${labelCls} mb-1 block`}>Resume</label>
        <ResumeDropzone
          resume_chars={profile.resume_chars ?? null}
          resume_updated_at={profile.resume_updated_at ?? null}
          onChange={(info) => setProfile((p) => ({ ...p, ...info }))}
        />
      </section>

      {/* ── Preferences ── */}
      <section className="mb-16">
        <SectionLabel className="mb-6">Preferences</SectionLabel>

        <label className={`${labelCls} mb-2 block`}>Role tracks</label>
        <div className="mb-6 flex flex-wrap gap-2">
          {TRACKS.map((t) => (
            <Chip key={t.key} label={t.label} active={(profile.tracks ?? []).includes(t.key)} onClick={() => toggleIn("tracks", t.key)} />
          ))}
        </div>

        <label className={`${labelCls} mb-2 block`}>Seniority</label>
        <div className="mb-6 flex flex-wrap gap-2">
          {SENIORITY.map((s) => (
            <Chip key={s.key} label={s.label} active={(profile.seniority_pref ?? []).includes(s.key)} onClick={() => toggleIn("seniority_pref", s.key)} />
          ))}
        </div>

        <label className={`${labelCls} mb-2 block`}>Work style</label>
        <div className="mb-6 flex flex-wrap gap-2">
          {REMOTE_PREFS.map((r) => (
            <Chip key={r.key} label={r.label} active={(profile.remote_pref ?? "any") === r.key} onClick={() => set("remote_pref", r.key)} />
          ))}
        </div>

        <label className={`${labelCls} mb-2 block`}>Skills</label>
        <div className="mb-3 flex flex-wrap gap-2">
          {COMMON_SKILLS.map((s) => (
            <Chip key={s} label={s} active={skillSet.has(s)} onClick={() => toggleIn("tech_tags", s)} />
          ))}
          {customSkills.map((s) => (
            <Chip key={s} label={s} active onClick={() => toggleIn("tech_tags", s)} />
          ))}
        </div>
        <div className="mb-6 flex gap-2">
          <input
            className={inputCls}
            placeholder="Add another skill…"
            value={customSkill}
            onChange={(e) => setCustomSkill(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSkill(); } }}
          />
          <button type="button" onClick={addSkill} className={btnOutline}>Add</button>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <label className={`${labelCls} mb-1 block`}>Preferred location</label>
            <input
              className={inputCls}
              placeholder="e.g. San Francisco, or Remote"
              value={profile.location ?? ""}
              onChange={(e) => set("location", e.target.value)}
            />
          </div>
          <div>
            <label className={`${labelCls} mb-1 block`}>Minimum salary (USD)</label>
            <input
              type="number"
              className={inputCls}
              placeholder="e.g. 120000"
              value={profile.salary_floor ?? ""}
              onChange={(e) => set("salary_floor", e.target.value ? Number(e.target.value) : null)}
            />
          </div>
        </div>

        <label className={`${labelCls} mb-2 mt-6 block`}>Visa sponsorship</label>
        <div className="flex flex-wrap gap-2">
          <Chip label="I need sponsorship" active={profile.needs_sponsorship === true} onClick={() => set("needs_sponsorship", profile.needs_sponsorship === true ? null : true)} />
          <Chip label="I don't need it" active={profile.needs_sponsorship === false} onClick={() => set("needs_sponsorship", profile.needs_sponsorship === false ? null : false)} />
        </div>

        <div className="mt-8 flex items-center gap-4">
          <button onClick={save} disabled={busy} className={btnSolid}>
            {busy ? "Saving…" : "Save changes"}
          </button>
          {savedMsg && <span className={labelCls}>{savedMsg}</span>}
        </div>
      </section>

      {/* ── Account ── */}
      <section>
        <SectionLabel className="mb-6">Account</SectionLabel>
        <p className="mb-4 font-body text-sm text-muted-foreground">
          Signed in as <strong className="text-foreground">{session?.user?.email}</strong>
        </p>
        <button onClick={() => signOut({ callbackUrl: "/" })} className={btnOutline}>
          Sign out
        </button>
      </section>
    </main>
  );
}
