"use client";
import { m, useReducedMotion } from "motion/react";
import { duration, ease } from "@/lib/motion";

/**
 * Industry bar that grows to `pct`% on scroll-into-view. The final width is set on
 * the fill; scaleX (transform-only) animates it in from the left. Reduced-motion
 * shows it at full width immediately.
 */
export function BarFill({ pct }: { pct: number }) {
  const reduce = useReducedMotion();
  return (
    <div className="mt-2 h-2 w-full bg-muted">
      <m.div
        className="h-full origin-left bg-foreground"
        style={{ width: `${pct}%` }}
        initial={reduce ? false : { scaleX: 0 }}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: true, margin: "-10%" }}
        transition={{ duration: duration.slow, ease }}
      />
    </div>
  );
}
