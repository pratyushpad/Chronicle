"use client";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { SectionLabel } from "@/components/SectionLabel";

const API_BASE =
  process.env.NEXT_PUBLIC_EXTENSION_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8002";

const labelCls = "font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground";
const inputCls =
  "w-full border border-foreground bg-background px-3 py-2 font-body text-sm text-foreground focus:outline-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2";
const btnSolid =
  "inline-flex min-h-[36px] items-center justify-center bg-foreground px-5 font-mono text-xs font-medium uppercase tracking-[0.12em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground hover:shadow-[inset_0_0_0_2px_var(--foreground)] disabled:opacity-50";
const btnOutline =
  "inline-flex min-h-[36px] items-center justify-center border border-foreground px-5 font-mono text-xs uppercase tracking-[0.12em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background disabled:opacity-50";

interface Profile {
  full_name?: string | null;
  location?: string | null;
  phone?: string | null;
  work_authorization?: string | null;
  links?: Record<string, string> | null;
}

export default function SettingsPage() {
  const { status } = useSession();

  // ── Extension token state ──
  const [connected, setConnected] = useState<boolean | null>(null);
  const [token, setToken] = useState<string | null>(null); // shown once after generate
  const [copied, setCopied] = useState(false);
  const [tokenBusy, setTokenBusy] = useState(false);

  // ── Autofill profile state ──
  const [profile, setProfile] = useState<Profile>({});
  const [savedMsg, setSavedMsg] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);

  useEffect(() => {
    if (status !== "authenticated") return;
    fetch("/api/user/extension-token")
      .then((r) => r.json())
      .then((d) => setConnected(!!d?.connected))
      .catch(() => setConnected(false));
    fetch("/api/user/profile")
      .then((r) => r.json())
      .then((d) => { if (d) setProfile(d); })
      .catch(() => {});
  }, [status]);

  const generate = async () => {
    setTokenBusy(true);
    setCopied(false);
    const res = await fetch("/api/user/extension-token", { method: "POST" });
    if (res.ok) {
      const d = await res.json();
      setToken(d.token);
      setConnected(true);
    }
    setTokenBusy(false);
  };

  const revoke = async () => {
    setTokenBusy(true);
    const res = await fetch("/api/user/extension-token", { method: "DELETE" });
    if (res.ok) {
      setToken(null);
      setConnected(false);
    }
    setTokenBusy(false);
  };

  const copyToken = async () => {
    if (!token) return;
    await navigator.clipboard.writeText(token);
    setCopied(true);
  };

  const setLink = (key: string, value: string) =>
    setProfile((p) => ({ ...p, links: { ...(p.links ?? {}), [key]: value } }));

  const saveProfile = async () => {
    setProfileBusy(true);
    setSavedMsg("");
    const res = await fetch("/api/user/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: profile.full_name ?? null,
        location: profile.location ?? null,
        phone: profile.phone ?? null,
        work_authorization: profile.work_authorization ?? null,
        links: profile.links ?? null,
      }),
    });
    setSavedMsg(res.ok ? "Saved." : "Save failed.");
    setProfileBusy(false);
  };

  if (status === "loading") {
    return <main className="mx-auto max-w-2xl px-6 py-20" />;
  }
  if (status !== "authenticated") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-20">
        <p className="font-body text-muted-foreground">Sign in to manage your settings.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="mb-2 font-display text-4xl text-foreground">Settings</h1>
      <p className="mb-12 font-body text-muted-foreground">
        Connect the Chronicle browser extension and manage the profile it uses to autofill applications.
      </p>

      {/* ── Extension token ── */}
      <section className="mb-16">
        <SectionLabel className="mb-6">Browser Extension</SectionLabel>

        <div className="mb-4 flex items-center gap-2">
          <span
            className={`h-2 w-2 ${connected ? "bg-foreground" : "border border-foreground"}`}
            aria-hidden
          />
          <span className={labelCls}>
            {connected === null ? "Checking…" : connected ? "Token active" : "Not connected"}
          </span>
        </div>

        <p className="mb-4 font-body text-sm text-muted-foreground">
          Generate a token, then paste it into the extension popup to connect. The token is shown{" "}
          <strong className="text-foreground">once</strong> — copy it now. Generating a new token
          revokes the old one. The extension fills forms only and never submits on your behalf.
        </p>

        {token && (
          <div className="mb-4 border border-foreground p-4">
            <p className={`${labelCls} mb-2`}>Your new token — copy it now</p>
            <code className="block break-all font-mono text-xs text-foreground">{token}</code>
            <div className="mt-3 flex items-center gap-3">
              <button onClick={copyToken} className={btnOutline}>
                {copied ? "Copied ✓" : "Copy"}
              </button>
              <span className={`${labelCls} font-body normal-case`}>
                API endpoint: <code className="font-mono">{API_BASE}</code>
              </span>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button onClick={generate} disabled={tokenBusy} className={btnSolid}>
            {connected ? "Regenerate token" : "Generate token"}
          </button>
          {connected && (
            <button onClick={revoke} disabled={tokenBusy} className={btnOutline}>
              Revoke
            </button>
          )}
        </div>
      </section>

      {/* ── Autofill profile ── */}
      <section>
        <SectionLabel className="mb-6">Autofill Profile</SectionLabel>
        <p className="mb-6 font-body text-sm text-muted-foreground">
          These fields are what the extension fills into Greenhouse, Lever, and Ashby application forms.
        </p>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <label className={`${labelCls} mb-1 block`}>Full name</label>
            <input
              className={inputCls}
              value={profile.full_name ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))}
            />
          </div>
          <div>
            <label className={`${labelCls} mb-1 block`}>Phone</label>
            <input
              className={inputCls}
              value={profile.phone ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, phone: e.target.value }))}
            />
          </div>
          <div>
            <label className={`${labelCls} mb-1 block`}>Location</label>
            <input
              className={inputCls}
              value={profile.location ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, location: e.target.value }))}
            />
          </div>
          <div>
            <label className={`${labelCls} mb-1 block`}>Work authorization</label>
            <input
              className={inputCls}
              placeholder="e.g. US Citizen, H-1B, Need sponsorship"
              value={profile.work_authorization ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, work_authorization: e.target.value }))}
            />
          </div>
          <div>
            <label className={`${labelCls} mb-1 block`}>LinkedIn URL</label>
            <input
              className={inputCls}
              value={profile.links?.linkedin ?? ""}
              onChange={(e) => setLink("linkedin", e.target.value)}
            />
          </div>
          <div>
            <label className={`${labelCls} mb-1 block`}>GitHub URL</label>
            <input
              className={inputCls}
              value={profile.links?.github ?? ""}
              onChange={(e) => setLink("github", e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={`${labelCls} mb-1 block`}>Portfolio / website URL</label>
            <input
              className={inputCls}
              value={profile.links?.portfolio ?? ""}
              onChange={(e) => setLink("portfolio", e.target.value)}
            />
          </div>
        </div>

        <div className="mt-6 flex items-center gap-4">
          <button onClick={saveProfile} disabled={profileBusy} className={btnSolid}>
            {profileBusy ? "Saving…" : "Save profile"}
          </button>
          {savedMsg && <span className={labelCls}>{savedMsg}</span>}
        </div>
      </section>
    </main>
  );
}
