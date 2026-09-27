"use client";

import { useRef, type CSSProperties, type ReactNode } from "react";
import { useInView } from "motion/react";
import { staggerStep } from "@/lib/motion";
import { cn } from "@/lib/utils";

interface RevealProps {
  children: ReactNode;
  /** Position in a list — drives a small stagger delay so items print in sequence. */
  index?: number;
  /** Extra classes on the wrapper (it's a block-level div). */
  className?: string;
  as?: "div" | "li";
  /** Rise distance in px. Larger = more pronounced (e.g. the jobs feed). */
  y?: number;
  /** Per-item stagger step in seconds. */
  step?: number;
  /**
   * When to fire. "inView" (default) waits for scroll-into-view — right for
   * below-the-fold landing sections. "mount" plays as soon as it renders — use for
   * content that's already on screen when it appears (e.g. a paginated feed).
   */
  trigger?: "inView" | "mount";
}

/** Cap the stagger so long lists don't wait seconds to finish. */
const MAX_STAGGER = 0.4;

/**
 * Entrance wrapper. Works around server-rendered children (e.g. JobCards) without
 * converting them to client components — the child JSX is passed through untouched.
 *
 * The markup never depends on the reader's motion preference, so server HTML and
 * hydration always agree, and the hidden "before" frame exists only in CSS that is
 * gated on `prefers-reduced-motion: no-preference`:
 *  - "mount": a CSS keyframe (`motion-safe:animate-reveal`) that plays on insertion and
 *    needs no JS; reduced-motion readers get the final state with no animation.
 *  - "inView": the element is marked `data-reveal="rise"`; globals.css hides it only for
 *    motion-OK readers with JS, and `data-revealed` (set when it scrolls into view)
 *    transitions it in.
 * Duration and curve come from lib/motion.ts via the Tailwind theme.
 */
export function Reveal({
  children,
  index = 0,
  className,
  as = "div",
  y = 8,
  step = staggerStep,
  trigger = "inView",
}: RevealProps) {
  const delay = Math.min(index * step, MAX_STAGGER);
  const style = { "--reveal-y": `${y}px`, "--reveal-delay": `${delay}s` } as CSSProperties;

  if (trigger === "mount") {
    const Tag = as;
    return (
      <Tag className={cn("motion-safe:animate-reveal", className)} style={style}>
        {children}
      </Tag>
    );
  }

  return (
    <InViewReveal as={as} className={className} style={style}>
      {children}
    </InViewReveal>
  );
}

function InViewReveal({
  as,
  className,
  style,
  children,
}: {
  as: "div" | "li";
  className?: string;
  style: CSSProperties;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement & HTMLLIElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10%" });
  const Tag = as;
  return (
    <Tag
      ref={ref}
      data-reveal="rise"
      data-revealed={inView ? "" : undefined}
      className={className}
      style={style}
    >
      {children}
    </Tag>
  );
}
