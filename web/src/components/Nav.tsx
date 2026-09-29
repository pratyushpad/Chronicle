"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signIn, signOut } from "next-auth/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn, formatNumber } from "@/lib/utils";
import { Magnetic } from "@/components/gsap/Magnetic";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

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

/** One notifications fetch shared by the desktop bell and the mobile menu. */
function useNotifications(email: string | null | undefined) {
  const [items, setItems] = useState<Notif[]>([]);

  useEffect(() => {
    if (!email) {
      setItems([]);
      return;
    }
    let cancelled = false;
    fetch("/api/notifications")
      .then((r) => r.json())
      .then((data) => { if (!cancelled && Array.isArray(data)) setItems(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [email]);

  const markRead = useCallback((id: number) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    fetch("/api/notifications", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }).catch(() => {});
  }, []);
  const markAllRead = useCallback(() => {
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    fetch("/api/notifications", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }).catch(() => {});
  }, []);

  return { items, unread: items.filter((n) => !n.read).length, markRead, markAllRead };
}

type Notifications = ReturnType<typeof useNotifications>;

/** The notification rows, shared by the bell popover and the mobile menu. */
function NotificationItems({ notifications, onNavigate }: { notifications: Notifications; onNavigate?: () => void }) {
  const { items, markRead } = notifications;
  if (items.length === 0) {
    return <p className="px-4 py-6 text-center font-sans text-sm text-muted-foreground">No notifications yet.</p>;
  }
  return (
    <>
      {items.map((n) => {
        const { title, body, link } = notifText(n);
        const inner = (
          <div className="flex items-start gap-2">
            {!n.read && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-foreground" aria-hidden />}
            <div className={n.read ? "pl-3.5" : ""}>
              <p className="font-sans text-sm text-foreground">{title}</p>
              {body && <p className="font-sans text-xs text-muted-foreground">{body}</p>}
              <p className="mt-0.5 font-sans text-[11px] uppercase tracking-[0.1em] text-muted-foreground">{relativeTime(n.created_at)}</p>
            </div>
          </div>
        );
        const cls = "block w-full border-b border-border-light px-4 py-3 text-left transition-colors hover:bg-muted";
        return link ? (
          <Link key={n.id} href={link} className={cls} onClick={() => { markRead(n.id); onNavigate?.(); }}>{inner}</Link>
        ) : (
          <button key={n.id} className={cls} onClick={() => markRead(n.id)}>{inner}</button>
        );
      })}
    </>
  );
}

function NotificationBell({ notifications }: { notifications: Notifications }) {
  const { unread, markAllRead } = notifications;
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey); };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        className="relative p-1.5 text-muted-foreground transition-colors duration-100 hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
        title="Notifications"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center border border-input bg-foreground font-sans text-[11px] text-background" aria-hidden>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        // Never wider than the viewport, whatever width the nav is rendered at.
        <div className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] border border-input bg-background">
          <div className="flex items-center justify-between border-b border-border-light px-4 py-2">
            <span className="font-sans text-[11px] uppercase tracking-[0.15em] text-foreground">Notifications</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="font-sans text-[11px] uppercase tracking-[0.1em] text-muted-foreground hover:text-foreground">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            <NotificationItems notifications={notifications} onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}

const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2";

type NavLink = { href: string; label: string };

function isCurrent(pathname: string | null, href: string) {
  return !!pathname && (pathname === href || pathname.startsWith(`${href}/`));
}

/**
 * Below `lg`: the logo plus one "Menu" button (44px) that opens a right-hand Sheet with
 * every nav link, notifications and sign in/out. Base UI's Dialog traps focus, closes on
 * Escape / outside press, labels itself from the SheetTitle and returns focus to this
 * trigger on close. Links close it on click, and any route change closes it too.
 * `lg` rather than `md`: the signed-in desktop row is ~830px of links, which can't fit
 * a tablet width without overflowing.
 */
function MobileMenu({
  links,
  status,
  userImage,
  notifications,
  companyCount,
}: {
  links: NavLink[];
  status: "authenticated" | "unauthenticated" | "loading";
  userImage?: string | null;
  notifications: Notifications;
  companyCount?: number | null;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [showNotifs, setShowNotifs] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const { unread, markAllRead } = notifications;

  // Back/forward and links outside the sheet change the route without a click in here.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setShowNotifs(false);
      }}
    >
      <SheetTrigger
        className={cn(
          "relative inline-flex h-11 items-center gap-2 border border-input px-3 font-sans text-xs uppercase tracking-[0.12em] text-foreground",
          "transition-[color,background-color,transform] duration-fast ease-house hover:bg-foreground hover:text-background motion-safe:active:scale-[0.97]",
          FOCUS_RING,
        )}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        Menu
        {status === "authenticated" && unread > 0 && (
          <>
            <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-[1rem] items-center justify-center border border-background bg-foreground px-0.5 font-sans text-[11px] text-background" aria-hidden>
              {unread > 9 ? "9+" : unread}
            </span>
            <span className="sr-only">, {unread} unread notification{unread === 1 ? "" : "s"}</span>
          </>
        )}
      </SheetTrigger>

      <SheetContent side="right" className="gap-0 overflow-y-auto border-l border-border-light bg-background">
        <div className="flex h-16 shrink-0 items-center border-b border-border-light px-6">
          <SheetTitle className="font-sans text-xs font-medium uppercase tracking-[0.2em]">Menu</SheetTitle>
        </div>

        <nav aria-label="Main">
          <ul className="divide-y divide-border-light">
            {links.map((l) => {
              const current = isCurrent(pathname, l.href);
              return (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    onClick={close}
                    aria-current={current ? "page" : undefined}
                    className={cn(
                      "flex min-h-[52px] items-center justify-between gap-4 px-6 font-sans text-sm uppercase tracking-[0.12em] transition-colors duration-100 hover:bg-muted",
                      current ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                      FOCUS_RING,
                    )}
                  >
                    {l.label}
                    {current ? (
                      <span className="h-2 w-2 shrink-0 bg-foreground" aria-hidden />
                    ) : (
                      <span aria-hidden>→</span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {status === "authenticated" && (
          <section className="mt-2 border-t border-border-light" aria-label="Notifications">
            <div className="flex items-center justify-between gap-2 px-6">
              <button
                type="button"
                aria-expanded={showNotifs}
                aria-controls="mobile-notifications"
                onClick={() => setShowNotifs((v) => !v)}
                className={cn(
                  "flex min-h-[52px] flex-1 items-center gap-2 font-sans text-sm uppercase tracking-[0.12em] text-foreground",
                  FOCUS_RING,
                )}
              >
                Notifications
                {unread > 0 && (
                  <span className="bg-foreground px-1.5 py-0.5 font-sans text-[11px] text-background">
                    {unread > 9 ? "9+" : unread} new
                  </span>
                )}
                <span className="ml-auto text-muted-foreground" aria-hidden>
                  {showNotifs ? "−" : "+"}
                </span>
              </button>
            </div>
            <div id="mobile-notifications" hidden={!showNotifs} className="border-t border-border-light">
                {unread > 0 && (
                  <div className="flex justify-end px-6 pt-2">
                    <button
                      onClick={markAllRead}
                      className={cn("min-h-[44px] font-sans text-[11px] uppercase tracking-[0.1em] text-muted-foreground hover:text-foreground", FOCUS_RING)}
                    >
                      Mark all read
                    </button>
                  </div>
                )}
                <NotificationItems notifications={notifications} onNavigate={close} />
            </div>
          </section>
        )}

        <div className="mt-auto flex flex-col gap-4 border-t border-border-light px-6 py-6">
          {status === "authenticated" ? (
            <button
              onClick={() => signOut({ callbackUrl: "/" })}
              className={cn(
                "flex min-h-[48px] w-full items-center justify-center gap-2 border border-input px-4 font-sans text-xs uppercase tracking-[0.15em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background",
                FOCUS_RING,
              )}
            >
              {userImage && (
                // eslint-disable-next-line @next/next/no-img-element -- 16px Google avatar; next/image would route it through the optimizer for no gain.
                <img src={userImage} alt="" className="h-4 w-4 object-cover" />
              )}
              Sign out
            </button>
          ) : status === "unauthenticated" ? (
            <button
              onClick={() => signIn("google")}
              className={cn(
                "flex min-h-[48px] w-full items-center justify-center bg-foreground px-4 font-sans text-xs font-medium uppercase tracking-[0.15em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground hover:shadow-[inset_0_0_0_2px_var(--foreground)]",
                FOCUS_RING,
              )}
            >
              Sign in
            </button>
          ) : null}
          <ThemeToggle className="justify-center" />
          {companyCount != null && (
            <p className="font-sans text-[11px] uppercase tracking-[0.15em] text-muted-foreground">
              {formatNumber(companyCount)} companies indexed
            </p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function Nav({ companyCount }: { companyCount?: number | null }) {
  const { data: session, status } = useSession();
  const notifications = useNotifications(status === "authenticated" ? session?.user?.email : null);

  // Sync user to DB on first sign-in
  useEffect(() => {
    if (session?.user?.email) {
      fetch("/api/user/sync", { method: "POST" }).catch(() => {});
    }
  }, [session?.user?.email]);

  const linkClass =
    "px-2 py-1 font-sans text-xs uppercase tracking-[0.12em] text-muted-foreground transition-colors duration-100 hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2";

  const links: NavLink[] = [
    { href: "/jobs", label: "Roles" },
    { href: "/companies", label: "Companies" },
    ...(status === "authenticated"
      ? [
          { href: "/for-you", label: "For You" },
          { href: "/saved", label: "Saved" },
          { href: "/tracker", label: "Tracker" },
          { href: "/settings", label: "Settings" },
        ]
      : status === "unauthenticated"
        ? [{ href: "/tracker", label: "Tracker" }]
        : []),
  ];

  return (
    <nav className="sticky top-0 z-50 border-b border-border-light bg-background">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6 md:px-8 lg:px-12">
        <Link
          href="/"
          className="font-display text-2xl font-medium tracking-tight text-foreground transition-opacity duration-100 hover:opacity-70 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
        >
          Chronicle
        </Link>

        {/* Desktop (lg+) — the original row. */}
        <div className="hidden items-center gap-1 sm:gap-3 lg:flex">
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
              <NotificationBell notifications={notifications} />
              <button
                onClick={() => signOut({ callbackUrl: "/" })}
                className="flex items-center gap-2 border border-input px-3 py-1.5 font-sans text-xs uppercase tracking-[0.12em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
              >
                {session.user?.image && (
                  // eslint-disable-next-line @next/next/no-img-element -- 16px Google avatar; next/image would route it through the optimizer for no gain.
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
              <Magnetic>
                <button
                  onClick={() => signIn("google")}
                  className="inline-flex min-h-[36px] items-center justify-center bg-foreground px-5 font-sans text-xs font-medium uppercase tracking-[0.15em] text-background transition-colors duration-100 hover:bg-background hover:text-foreground hover:shadow-[inset_0_0_0_2px_var(--foreground)] focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2"
                >
                  Sign in
                </button>
              </Magnetic>
            </>
          ) : (
            // Session still loading: hold the signed-out row's width (invisible, inert)
            // so Roles/Companies don't shift left when the auth controls arrive.
            <div aria-hidden className="invisible flex items-center gap-1 sm:gap-3">
              <span className={linkClass}>Tracker</span>
              <span className="inline-flex min-h-[36px] items-center px-5 font-sans text-xs font-medium uppercase tracking-[0.15em]">
                Sign in
              </span>
            </div>
          )}

          <ThemeToggle />
          {companyCount != null && (
            // Signed in, the row needs xl to fit its six links + badge; the count is also
            // in the mobile menu.
            <span
              className={cn(
                "ml-1 hidden font-sans text-xs uppercase tracking-[0.12em] text-muted-foreground",
                status === "authenticated" ? "xl:inline" : "sm:inline",
              )}
            >
              / {formatNumber(companyCount)} companies
            </span>
          )}
        </div>

        {/* Below lg — logo + Menu; this row never depends on the session, so it can't jump. */}
        <div className="lg:hidden">
          <MobileMenu
            links={links}
            status={status}
            userImage={session?.user?.image}
            notifications={notifications}
            companyCount={companyCount}
          />
        </div>
      </div>
    </nav>
  );
}
