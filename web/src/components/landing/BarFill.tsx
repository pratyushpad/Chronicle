"use client";
import { useRef } from "react";
import { useInView } from "motion/react";

/**
 * Industry bar that grows to `pct`% on scroll-into-view. The final width is set on the
 * fill and the server renders it full; scaleX (transform-only) grows it from the left
 * via the `data-reveal="grow-x"` rules in globals.css, which exist only for readers who
 * allow motion and have JS. Reduced-motion and no-JS readers see the full bar at once.
 */
export function BarFill({ pct }: { pct: number }) {
  // Observe the untransformed track, not the fill (a scaleX(0) box has no area).
  const trackRef = useRef<HTMLDivElement>(null);
  const inView = useInView(trackRef, { once: true, margin: "-10%" });
  return (
    <div ref={trackRef} className="mt-2 h-2 w-full bg-muted">
      <div
        data-reveal="grow-x"
        data-revealed={inView ? "" : undefined}
        className="h-full origin-left bg-foreground"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
