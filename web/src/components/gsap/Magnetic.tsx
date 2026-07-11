"use client";

import { useRef } from "react";
import { gsap, useGSAP } from "@/lib/gsapConfig";
import { cn } from "@/lib/utils";

/**
 * Wraps an interactive element so it drifts toward the pointer while hovered and springs
 * back on leave — a restrained magnetic pull for primary CTAs. Uses gsap.quickTo for a
 * smoothed, allocation-free follow.
 *
 * Gated to fine pointers (mouse) and prefers-reduced-motion: no-preference, so touch and
 * reduced-motion users get a plain, static element. Handlers are contextSafe + removed on
 * cleanup, so nothing leaks across route changes.
 */
export function Magnetic({
  children,
  className,
  strength = 0.35,
}: {
  children: React.ReactNode;
  className?: string;
  strength?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useGSAP(
    (_ctx, contextSafe) => {
      const el = ref.current;
      if (!el || !contextSafe) return;
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference) and (pointer: fine)", () => {
        const xTo = gsap.quickTo(el, "x", { duration: 0.4, ease: "chronicle" });
        const yTo = gsap.quickTo(el, "y", { duration: 0.4, ease: "chronicle" });
        const onMove = contextSafe((e: PointerEvent) => {
          const r = el.getBoundingClientRect();
          xTo((e.clientX - (r.left + r.width / 2)) * strength);
          yTo((e.clientY - (r.top + r.height / 2)) * strength);
        });
        const onLeave = contextSafe(() => {
          xTo(0);
          yTo(0);
        });
        el.addEventListener("pointermove", onMove);
        el.addEventListener("pointerleave", onLeave);
        return () => {
          el.removeEventListener("pointermove", onMove);
          el.removeEventListener("pointerleave", onLeave);
        };
      });
    },
    { scope: ref },
  );

  return (
    <span ref={ref} className={cn("inline-block", className)}>
      {children}
    </span>
  );
}
