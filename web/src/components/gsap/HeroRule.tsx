"use client";

import { useRef } from "react";
import { gsap, useGSAP, ScrollTrigger } from "@/lib/gsapConfig";

/**
 * The hero's rule-and-square divider, assembled on scroll: the two rules draw outward
 * and the center square scales + rotates into place, scrubbed to scroll position so it
 * feels like the masthead is being ruled onto the page as you enter the feed.
 *
 * Deliberately NOT a pinned section — the hero holds the primary CTAs, so trapping it
 * under the scroll would hurt the utility of the page. Transform-only (scaleX / scale /
 * rotate). Reduced-motion renders the divider fully assembled and static.
 */
export function HeroRule() {
  const ref = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLSpanElement>(null);
  const squareRef = useRef<HTMLSpanElement>(null);
  const rightRef = useRef<HTMLSpanElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: ref.current!,
            start: "top 92%",
            end: "top 55%",
            scrub: 0.6,
          },
        });
        tl.from(leftRef.current, { scaleX: 0, transformOrigin: "left center" }, 0)
          .from(rightRef.current, { scaleX: 0, transformOrigin: "left center" }, 0)
          .from(squareRef.current, { scale: 0, rotate: -90, transformOrigin: "center" }, 0.1);
        return () => {
          tl.scrollTrigger?.kill();
          tl.kill();
        };
      });
    },
    { scope: ref },
  );

  return (
    <div ref={ref} className="mt-12 flex items-center gap-6 md:mt-16">
      <span ref={leftRef} className="h-1 w-24 bg-foreground md:w-40" />
      <span ref={squareRef} className="h-3 w-3 border-2 border-foreground" />
      <span ref={rightRef} className="h-1 flex-1 bg-foreground" />
    </div>
  );
}
