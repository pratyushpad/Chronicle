"use client";
import Link from "next/link";
import { useSession, signIn, signOut } from "next-auth/react";
import { useEffect, useState } from "react";

function NotificationBell({ email }: { email: string }) {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    fetch("/api/notifications")
      .then((r) => r.json())
      .then((data: Array<{ read: boolean }>) => {
        if (Array.isArray(data)) setUnread(data.filter((n) => !n.read).length);
      })
      .catch(() => {});
  }, [email]);

  return (
    <button
      className="relative p-1.5 text-muted-foreground hover:text-foreground transition-colors"
      title="Notifications"
      onClick={() => {
        // mark all read
        fetch("/api/notifications", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) })
          .then(() => setUnread(0));
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {unread > 0 && (
        <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 flex items-center justify-center rounded-full bg-accent text-[8px] text-white font-mono">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </button>
  );
}

export function Nav() {
  const { data: session, status } = useSession();

  // Sync user to DB on first sign-in
  useEffect(() => {
    if (session?.user?.email) {
      fetch("/api/user/sync", { method: "POST" }).catch(() => {});
    }
  }, [session?.user?.email]);

  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
        <Link href="/" className="font-display text-xl text-foreground transition-colors hover:text-accent">
          Folio
        </Link>

        <div className="flex items-center gap-1 sm:gap-3">
          <Link href="/jobs" className="font-body text-sm text-muted-foreground transition-colors hover:text-foreground px-2 py-1">
            Roles
          </Link>
          <Link href="/companies" className="font-body text-sm text-muted-foreground transition-colors hover:text-foreground px-2 py-1">
            Companies
          </Link>

          {status === "authenticated" ? (
            <>
              <Link href="/for-you" className="font-body text-sm text-muted-foreground transition-colors hover:text-foreground px-2 py-1">
                For You
              </Link>
              <Link href="/saved" className="font-body text-sm text-muted-foreground transition-colors hover:text-foreground px-2 py-1">
                Saved
              </Link>
              <Link href="/tracker" className="font-body text-sm text-muted-foreground transition-colors hover:text-foreground px-2 py-1">
                Tracker
              </Link>
              <NotificationBell email={session.user!.email!} />
              <button
                onClick={() => signOut({ callbackUrl: "/" })}
                className="flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs font-body text-muted-foreground hover:border-accent hover:text-accent transition-colors"
              >
                {session.user?.image && (
                  <img src={session.user.image} alt="" className="h-4 w-4 rounded-full object-cover" />
                )}
                Sign out
              </button>
            </>
          ) : status === "unauthenticated" ? (
            <>
              <Link href="/tracker" className="font-body text-sm text-muted-foreground transition-colors hover:text-foreground px-2 py-1">
                Tracker
              </Link>
              <button
                onClick={() => signIn("google")}
                className="inline-flex min-h-[36px] items-center justify-center rounded-md bg-accent px-4 font-body text-xs font-medium text-white transition-all hover:bg-accent-secondary"
              >
                Sign in
              </button>
            </>
          ) : null}

          <span className="hidden sm:inline text-border ml-1">|</span>
          <span className="hidden sm:inline font-mono text-xs tracking-[0.1em] text-muted-foreground">
            201 companies
          </span>
        </div>
      </div>
    </nav>
  );
}
