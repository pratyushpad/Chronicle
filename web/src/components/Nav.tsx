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
      className="relative p-1.5 text-muted-foreground transition-colors duration-100 hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
      title="Notifications"
      onClick={() => {
        // mark all read
        fetch("/api/notifications", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) })
          .then(() => setUnread(0));
      }}
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

          <span className="ml-1 hidden font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground sm:inline">
            / 201 companies
          </span>
        </div>
      </div>
    </nav>
  );
}
