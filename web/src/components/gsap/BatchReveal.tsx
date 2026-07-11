"use client";

import { useRef } from "react";
import { gsap, useGSAP, ScrollTrigger } from "@/lib/gsapConfig";

/**
 * Reveals a group of sibling elements in staggered batches as they enter the viewport,
 * using ScrollTrigger.batch — cheaper and more cohesive than one trigger per card, and
 * `once: true` so it never re-fires or costs anything after the first pass. Any descendant
 * carrying `data-batch` participates.
 *
 * Reduced-motion: elements are set to their resting state and no triggers are created.
 * Server-renders children visible, so no-JS is unaffected.
 */
export function BatchReveal({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const items = gsap.utils.toArray<HTMLElement>(
        ref.current!.querySelectorAll("[data-batch]"),
      );
      if (!items.length) return;

      const mm = gsap.matchMedia();
      mm.add(
        {
          reduce: "(prefers-reduced-motion: reduce)",
          ok: "(prefers-reduced-motion: no-preference)",
        },
        (ctx) => {
          if (ctx.conditions!.reduce) {
            gsap.set(items, { opacity: 1, y: 0 });
            return;
          }
          gsap.set(items, { opacity: 0, y: 24 });
          ScrollTrigger.batch(items, {
            once: true,
            start: "top 88%",
            onEnter: (batch) =>
              gsap.to(batch, {
                opacity: 1,
                y: 0,
                duration: 0.6,
                ease: "chronicle",
                stagger: 0.09,
                overwrite: true,
              }),
          });
        },
      );
    },
    { scope: ref },
  );

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
