"use client";

import { useRef } from "react";
import { gsap, useGSAP } from "@/lib/gsapConfig";
import { formatNumber } from "@/lib/utils";

/**
 * A large stat that counts up scrubbed to scroll position — the number climbs as the
 * viewer scrolls the stat through the top of the viewport, so the reveal is tied to
 * their own motion rather than a fixed timer.
 *
 * CLS guard (same pattern as motion/CountUp): an invisible sizer holds the final
 * formatted string so the box is always sized to the widest value and the changing
 * digit/comma widths never shift layout. Server-renders the final value so no-JS and
 * reduced-motion both show the real number immediately.
 */
export function ScrubCounter({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const numRef = useRef<HTMLSpanElement>(null);

  useGSAP(
    () => {
      const paint = (n: number) => {
        if (numRef.current) numRef.current.textContent = formatNumber(Math.round(n));
      };
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const obj = { v: 0 };
        paint(0);
        const tween = gsap.to(obj, {
          v: value,
          ease: "none",
          onUpdate: () => paint(obj.v),
          scrollTrigger: {
            trigger: ref.current!,
            start: "top 85%",
            end: "top 45%",
            scrub: 0.5,
          },
        });
        return () => {
          tween.scrollTrigger?.kill();
          tween.kill();
          paint(value); // restore final value if motion is disabled mid-session
        };
      });
    },
    { scope: ref },
  );

  return (
    <span
      ref={ref}
      className={className}
      style={{ display: "inline-grid", fontVariantNumeric: "tabular-nums" }}
    >
      <span aria-hidden style={{ gridArea: "1 / 1", visibility: "hidden" }}>
        {formatNumber(value)}
      </span>
      <span ref={numRef} style={{ gridArea: "1 / 1" }}>
        {formatNumber(value)}
      </span>
    </span>
  );
}
