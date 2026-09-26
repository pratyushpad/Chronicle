"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";

type Choice = "system" | "light" | "dark";
const KEY = "chronicle-theme";
const ORDER: Choice[] = ["system", "light", "dark"];
const LABEL: Record<Choice, string> = { system: "Auto", light: "Light", dark: "Dark" };

// One store for every toggle on the page (the nav renders one for desktop and one in the
// mobile sheet): the saved choice in localStorage, with an event so all instances and
// other tabs stay in step.
const EVENT = "chronicle-theme-change";

function read(): Choice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function apply(choice: Choice) {
  const dark =
    choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** Cycles Auto (follow the system) → Light → Dark. app/layout.tsx applies the saved
 *  choice before first paint; this keeps it applied as things change. */
export function ThemeToggle({ className }: { className?: string }) {
  // Server and first client render both say "system", so hydration never mismatches.
  const choice = useSyncExternalStore(subscribe, read, () => "system" as Choice);

  useEffect(() => {
    apply(choice);
    if (choice !== "system") return;
    // Following the system: follow it live. Re-read the store first, in case another
    // instance or tab has just picked a theme.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply(read());
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  const cycle = useCallback(() => {
    const next = ORDER[(ORDER.indexOf(read()) + 1) % ORDER.length];
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {}
    apply(next);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={`Theme: ${LABEL[choice]}. Change theme`}
      title="Theme: Auto follows your system setting"
      className={cn(
        "inline-flex min-h-[36px] items-center gap-2 px-2 font-sans text-xs uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2",
        className,
      )}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
        <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor" />
      </svg>
      {LABEL[choice]}
    </button>
  );
}
