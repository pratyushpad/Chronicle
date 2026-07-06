"use client";

import { m, useReducedMotion } from "motion/react";
import { duration, ease } from "@/lib/motion";

/**
 * App Router `template.tsx` re-mounts on every navigation, so a plain enter
 * transition gives us a subtle fade + 8px rise on route change — never a jarring cut.
 * (We intentionally do NOT attempt exit animations here: App Router unmounts the old
 * template before the new one mounts, so page-level AnimatePresence exits don't fire.)
 */
export default function Template({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <m.div
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={{ duration: duration.base, ease }}
    >
      {children}
    </m.div>
  );
}
