"use client";
import Link from "next/link";
import { useSession, signIn, signOut } from "next-auth/react";
import { useEffect, useRef, useState } from "react";
import { formatNumber } from "@/lib/utils";

interface Notif {
  id: number;
  type: string;
  payload: Record<string, any>;
  read: boolean;
  created_at: string;
}

function relativeTime(iso: string): string {
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "";
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function notifText(n: Notif): { title: string; body: string; link: string | null } {
  const p = n.payload || {};
  const title = p.title || n.type.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
  const body = p.message || (p.count != null ? `${p.count} new role${p.count === 1 ? "" : "s"}${p.search_name ? ` for "${p.search_name}"` : ""}` : "");
  const link = p.url || p.link || (p.job_id ? `/jobs/${p.job_id}` : null);
  return { title, body, link };
}

function NotificationBell({ email }: { email: string }) {
  const [items, setItems] = useState<Notif[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const unread = items.filter((n) => !n.read).length;

  useEffect(() => {
    fetch("/api/notifications")
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setItems(data); })
      .catch(() => {});
  }, [email]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const markRead = (id: number) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    fetch("/api/notifications", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }).catch(() => {});
  };
  const markAllRead = () => {
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    fetch("/api/notifications", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }).catch(() => {});
  };

  return (
    <div className="relative" ref={ref}>
      <button
        className="relative p-1.5 text-muted-foreground transition-colors duration-100 hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
        title="Notifications"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center border border-foreground bg-foreground font-mono text-[8px] text-background">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 border-2 border-foreground bg-background">
          <div className="flex items-center justify-between border-b border-foreground px-4 py-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-foreground">Notifications</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground hover:text-foreground">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-6 text-center font-body text-sm text-muted-foreground">No notifications yet.</p>
            ) : (
              items.map((n) => {
                const { title, body, link } = notifText(n);
                const inner = (
                  <>
                    <div className="flex items-start gap-2">
                      {!n.read && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-foreground" aria-hidden />}
                      <div className={n.read ? "pl-3.5" : ""}>
                        <p className="font-body text-sm text-foreground">{title}</p>
                        {body && <p className="font-body text-xs text-muted-foreground">{body}</p>}
                        <p className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">{relativeTime(n.created_at)}</p>
                      </div>
                    </div>
                  </>
                );
                const cls = "block w-full border-b border-border-light px-4 py-3 text-left transition-colors hover:bg-muted";
                return link ? (
                  <Link key={n.id} href={link} className={cls} onClick={() => { markRead(n.id); setOpen(false); }}>{inner}</Link>
                ) : (
                  <button key={n.id} className={cls} onClick={() => markRead(n.id)}>{inner}</button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function Nav({ companyCount }: { companyCount?: number | null }) {
  const { data: session, status } = useSession();

  // Sync user to DB on first sign-in
  useEffect(() => {
    if (session?.user?.email) {
      fetch("/api/user/sync", { method: "POST" }).catch(() => {});
    }
  }, [session?.user?.email]);

  const linkClass =
    "px-2 py-1 font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground transition-colors duration-100 hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2";

  return (
    <nav className="sticky top-0 z-50 border-b-2 border-foreground bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6 md:px-8 lg:px-12">
        <Link
          href="/"
          className="font-display text-2xl font-medium tracking-tight text-foreground transition-opacity duration-100 hover:opacity-70 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
        >
          Chronicle
        </Link>

        <div className="flex items-center gap-1 sm:gap-3">
          <Link href="/jobs" className={linkClass}>
            Roles
          </Link>
          <Link href="/companies" className={linkClass}>
            Companies
          </Link>

          {status === "authenticated" ? (
            <>
              <Link href="/for-you" className={linkClass}>
                For You
              </Link>
              <Link href="/saved" className={linkClass}>
                Saved
              </Link>
              <Link href="/tracker" className={linkClass}>
                Tracker
              </Link>
              <Link href="/settings" className={linkClass}>
                Settings
              </Link>
              <NotificationBell email={session.user!.email!} />
              <button
                onClick={() => signOut({ callbackUrl: "/" })}
                className="flex items-center gap-2 border border-foreground px-3 py-1.5 font-mono text-xs uppercase tracking-[0.12em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
              >
                {session.user?.image && (
                  <img src={session.user.image} alt="" className="h-4 w-4 object-cover" />
                )}
                Sign out
              </button>
            </>
          ) : status === "unauthenticated" ? (
            <>
              <Link href="/tracker" className={linkClass}>
                Tracker
              </Link>
              <button
                onClick={() => signIn("google")}
                className="inline-flex min-h-[36px] items-center justify-center bg-foreground px-5 font-mono text-xs font-medium uppercase tracking-[0.15em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground hover:shadow-[inset_0_0_0_2px_var(--foreground)] focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
              >
                Sign in
              </button>
            </>
          ) : null}

          {companyCount != null && (
            <span className="ml-1 hidden font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground sm:inline">
              / {formatNumber(companyCount)} companies
            </span>
          )}
        </div>
      </div>
    </nav>
  );
}
