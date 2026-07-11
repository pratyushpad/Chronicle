"use client";

import { m, useReducedMotion } from "motion/react";
import { duration, ease, staggerStep } from "@/lib/motion";

interface RevealProps {
  children: React.ReactNode;
  /** Position in a list — drives a small stagger delay so items print in sequence. */
  index?: number;
  /** Extra classes on the wrapper (it's a block-level div). */
  className?: string;
  /** Cap the stagger so long lists don't wait seconds to finish. */
  as?: "div" | "li";
  /** Rise distance in px. Larger = more pronounced (e.g. the jobs feed). */
  y?: number;
  /** Per-item stagger step in seconds. */
  step?: number;
  /**
   * When to fire. "inView" (default) waits for scroll-into-view — right for
   * below-the-fold landing sections. "mount" animates as soon as it renders —
   * use for content that's already on screen when it appears (e.g. a paginated
   * feed), where whileInView's IntersectionObserver can miss on soft navigation.
   */
  trigger?: "inView" | "mount";
}

const MAX_STAGGER = 0.4;

/**
 * Entrance wrapper. Works around server-rendered children (e.g. JobCards) without
 * converting them to client components — the child JSX is passed through untouched.
 * Reduced-motion renders the child immediately.
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
  const reduce = useReducedMotion();
  const Tag = as === "li" ? m.li : m.div;
  const delay = Math.min(index * step, MAX_STAGGER);

  if (reduce) {
    const Plain = as === "li" ? "li" : "div";
    return <Plain className={className}>{children}</Plain>;
  }

  const transition = { duration: duration.base, ease, delay };

  if (trigger === "mount") {
    return (
      <Tag className={className} initial={{ opacity: 0, y }} animate={{ opacity: 1, y: 0 }} transition={transition}>
        {children}
      </Tag>
    );
  }

  return (
    <Tag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-10%" }}
      transition={transition}
    >
      {children}
    </Tag>
  );
}
