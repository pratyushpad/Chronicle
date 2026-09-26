import type { Variants, Transition } from "motion/react";

/**
 * Chronicle's motion vocabulary — defined once, applied everywhere so the whole
 * app reads as one restrained, editorial system rather than scattered effects.
 *
 * Rules of the house (see also the LazyMotion setup in SessionWrapper):
 *  - animate only `transform` and `opacity` (plus Framer `layout`) — never layout props
 *  - every consumer branches on `useReducedMotion()` and falls back to a static/opacity-only state
 *  - use the lightweight `m` component (not `motion`) to hold the perf budget
 */

/** Standard durations, in seconds. */
export const duration = {
  fast: 0.12,
  base: 0.24,
  slow: 0.48,
} as const;

/** House easing — expressive ease-out. */
export const ease = [0.22, 1, 0.36, 1] as const;

/**
 * The same tokens for CSS. tailwind.config.ts imports these to generate `ease-house`,
 * `duration-fast|base|slow` and `animate-reveal`, so CSS-driven motion (the Sheet, the
 * server-rendered entrance reveals) moves on exactly the Framer/GSAP curve and timings.
 */
export const cssEase = `cubic-bezier(${ease.join(", ")})`;
export const cssDuration = (seconds: number) => `${Math.round(seconds * 1000)}ms`;

/** Stagger step between siblings printing onto the page. */
export const staggerStep = 0.04;

export const baseTransition: Transition = { duration: duration.base, ease };

/** Fade + 8px rise — the app's default entrance. */
export const fadeRise: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: baseTransition },
};

/** Opacity-only entrance for `prefers-reduced-motion` (no transform). */
export const fadeOnly: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: duration.base, ease } },
};

/** Container that staggers its children's entrances. */
export const staggerContainer: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: staggerStep } },
};

/** Child of `staggerContainer`. */
export const staggerItem: Variants = fadeRise;

/** Satisfying spring for toggles/press states (bookmark, selection). */
export const springPress: Transition = { type: "spring", stiffness: 500, damping: 30 };
