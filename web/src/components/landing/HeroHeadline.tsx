"use client";
import { m, useReducedMotion } from "motion/react";
import { ease } from "@/lib/motion";

// The hero headline, word by word. Kept identical in wording to the original.
const LINES: { text: string; italic?: boolean }[][] = [
  [{ text: "Every" }, { text: "open" }],
  [{ text: "role." }, { text: "Every" }],
  [{ text: "company.", italic: true }],
];

/**
 * LCP-safe word reveal. This headline is the landing page's Largest Contentful
 * Paint element, so opacity stays at 1 the whole time — the text paints immediately
 * and is never held back. Only a tiny transform settles in, and the whole reveal
 * finishes well under 150ms so it can't delay LCP. Reduced-motion renders it static.
 */
export function HeroHeadline() {
  const reduce = useReducedMotion();
  let word = 0;
  return (
    <h1 className="mt-12 font-display text-6xl font-medium leading-[0.95] tracking-tight text-foreground sm:text-7xl md:mt-16 md:text-8xl lg:text-9xl">
      {LINES.map((line, li) => (
        <span key={li} className="block">
          {line.map((w, wi) => {
            const i = word++;
            return (
              <m.span
                key={wi}
                className={`inline-block ${w.italic ? "italic" : ""} ${wi > 0 ? "ml-[0.25em]" : ""}`}
                initial={reduce ? false : { y: 8 }}
                animate={{ y: 0 }}
                transition={{ duration: 0.12, ease, delay: i * 0.03 }}
              >
                {w.text}
              </m.span>
            );
          })}
        </span>
      ))}
    </h1>
  );
}
