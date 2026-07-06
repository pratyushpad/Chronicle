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
}

const MAX_STAGGER = 0.3;

/**
 * Scroll-into-view entrance wrapper. Works around server-rendered children
 * (e.g. JobCards) without converting them to client components — the child JSX
 * is passed through untouched. Reduced-motion renders the child immediately.
 */
export function Reveal({ children, index = 0, className, as = "div" }: RevealProps) {
  const reduce = useReducedMotion();
  const Tag = as === "li" ? m.li : m.div;
  const delay = Math.min(index * staggerStep, MAX_STAGGER);

  if (reduce) {
    const Plain = as === "li" ? "li" : "div";
    return <Plain className={className}>{children}</Plain>;
  }

  return (
    <Tag
      className={className}
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-10%" }}
      transition={{ duration: duration.base, ease, delay }}
    >
      {children}
    </Tag>
  );
}
