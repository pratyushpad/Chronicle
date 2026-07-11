"use client";

import { usePathname } from "next/navigation";
import { useRef } from "react";
import { gsap, useGSAP } from "@/lib/gsapConfig";

/**
 * A full-bleed monochrome wipe that plays on navigation so route changes read as
 * deliberate cuts rather than flashes. App Router unmounts the old page before any exit
 * could run, so this is an arrival wipe: on a pathname change the curtain covers instantly
 * (set in the layout effect, before the browser paints the new route — no flash of new
 * content) then wipes away downward to reveal it, all within ~450ms so it never feels slow.
 *
 * The initial page load is deliberately skipped — a curtain over the first paint would
 * delay the landing LCP. Reduced-motion never creates the animation, so the curtain stays
 * hidden.
 */
export function RouteCurtain() {
  const pathname = usePathname();
  const ref = useRef<HTMLDivElement>(null);
  const firstRun = useRef(true);

  useGSAP(
    () => {
      if (firstRun.current) {
        firstRun.current = false;
        return; // never wipe over the initial paint (protects landing LCP)
      }
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const el = ref.current!;
        gsap.set(el, { scaleY: 1, transformOrigin: "top center", autoAlpha: 1 });
        const tween = gsap.to(el, {
          scaleY: 0,
          transformOrigin: "bottom center",
          duration: 0.45,
          ease: "chronicle",
          onComplete: () => gsap.set(el, { autoAlpha: 0 }),
        });
        return () => tween.kill();
      });
    },
    { dependencies: [pathname], scope: ref },
  );

  return (
    <div
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[9998] bg-foreground"
      style={{ transform: "scaleY(0)", visibility: "hidden" }}
    />
  );
}
