"use client";

import { useRef } from "react";
import { ScrollSmoother } from "gsap/ScrollSmoother";
import { gsap, useGSAP } from "@/lib/gsapConfig";

// Registered here (not in gsapConfig) so ScrollSmoother stays out of every non-landing bundle.
if (typeof window !== "undefined") gsap.registerPlugin(ScrollSmoother);

/**
 * Wraps the landing page in ScrollSmoother's required `#smooth-wrapper > #smooth-content`
 * structure and drives inertial smooth-scroll + `data-speed` parallax there.
 *
 * Scoped deliberately to the landing ONLY (this component is rendered by app/page.tsx,
 * nowhere else) so the long, utility-first /jobs feed keeps native, snappy scrolling —
 * ScrollSmoother can lag long lists (motion brief, rail #2).
 *
 * Reduced-motion: no smoother is created, so scrolling stays fully native and the
 * `data-speed` layers simply render at rest. useGSAP reverts on unmount, killing the
 * smoother on navigation away so no proxy scroll or ScrollTrigger leaks across routes.
 */
export function SmoothScrollStage({ children }: { children: React.ReactNode }) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const smoother = ScrollSmoother.create({
          wrapper: wrapperRef.current!,
          content: contentRef.current!,
          smooth: 1,
          effects: true,
          // Leave touch scrolling native — smoothing touch feels laggy and fights momentum.
          smoothTouch: false,
        });
        return () => smoother.kill();
      });
    },
    { scope: wrapperRef },
  );

  return (
    <div id="smooth-wrapper" ref={wrapperRef}>
      <div id="smooth-content" ref={contentRef}>
        {children}
      </div>
    </div>
  );
}
