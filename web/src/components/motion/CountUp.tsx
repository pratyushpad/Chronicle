"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion, animate } from "motion/react";
import { formatNumber } from "@/lib/utils";
import { duration as durationTokens, ease } from "@/lib/motion";

interface CountUpProps {
  value: number;
  className?: string;
  /** Animation length in seconds. Defaults to the `slow` token. */
  durationS?: number;
}

/**
 * Counts a number up from 0 → `value` when it scrolls into view, formatted with the
 * app's `formatNumber` (comma grouping). Reduced-motion renders the final value at once.
 *
 * CLS guard: an invisible sizer holds the final formatted string in the same grid cell,
 * so the box is always sized to the final width and the animating digits/commas — which
 * change width mid-count — never shift surrounding layout. `tabular-nums` keeps digits
 * from jittering during the count.
 */
export function CountUp({ value, className, durationS = durationTokens.slow }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10%" });
  const reduce = useReducedMotion();
  const [display, setDisplay] = useState(0);
  // Track the last shown number so a changing `value` (e.g. the tracker funnel as
  // cards move) tweens from where it is, instead of snapping back to 0 each time.
  const shown = useRef(0);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      shown.current = value;
      setDisplay(value);
      return;
    }
    const controls = animate(shown.current, value, {
      duration: durationS,
      ease,
      onUpdate: (v) => {
        const r = Math.round(v);
        shown.current = r;
        setDisplay(r);
      },
    });
    return () => controls.stop();
  }, [inView, reduce, value, durationS]);

  return (
    <span
      ref={ref}
      className={className}
      style={{ display: "inline-grid", fontVariantNumeric: "tabular-nums" }}
    >
      {/* Sizer: reserves the final width so the count never causes layout shift. */}
      <span aria-hidden style={{ gridArea: "1 / 1", visibility: "hidden" }}>
        {formatNumber(value)}
      </span>
      <span style={{ gridArea: "1 / 1" }}>{formatNumber(display)}</span>
    </span>
  );
}
