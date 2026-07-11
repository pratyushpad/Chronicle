"use client";

/**
 * Single registration point for GSAP and its plugins. Every client component that
 * animates imports `gsap` (and any plugins) from here — never from "gsap" directly —
 * so plugins are registered exactly once and the house ease/durations stay consistent.
 *
 * GSAP 3.13+ ships SplitText / ScrollSmoother / etc. in the free package, so these
 * imports need no membership. Registration is guarded to the client: client components
 * still render once on the server, and GSAP must not touch the DOM there.
 */
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Flip } from "gsap/Flip";
import { Observer } from "gsap/Observer";
import { CustomEase } from "gsap/CustomEase";

// NOTE: the heavy, landing-only plugins (ScrollSmoother, SplitText) are deliberately NOT
// registered here. They are imported and registered directly by their sole consumers
// (SmoothScrollStage, HeroHeadline) so they stay out of every other route's bundle —
// Nav/Magnetic pull this module app-wide, and /jobs must stay lean for its Lighthouse budget.

if (typeof window !== "undefined") {
  gsap.registerPlugin(useGSAP, ScrollTrigger, Flip, Observer, CustomEase);

  // The app's editorial ease, mirroring lib/motion.ts `ease = [0.22, 1, 0.36, 1]`
  // (a cubic-bezier). Registering it by name lets GSAP tweens read `ease: "chronicle"`
  // so the GSAP and Framer surfaces move with the same signature curve.
  if (!gsap.parseEase("chronicle")) {
    CustomEase.create("chronicle", "M0,0 C0.22,1 0.36,1 1,1");
  }

  // Match Framer's press spring feel for snappy micro-interactions.
  gsap.defaults({ ease: "chronicle" });
}

/** House motion tokens (seconds), mirroring lib/motion.ts so both engines agree. */
export const DUR = {
  fast: 0.12,
  base: 0.24,
  slow: 0.48,
  cinematic: 0.9,
} as const;

/** Named ease string usable in any GSAP tween once this module has loaded. */
export const EASE = "chronicle";

export { gsap, useGSAP, ScrollTrigger, Flip, Observer, CustomEase };
