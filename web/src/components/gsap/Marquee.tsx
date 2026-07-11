"use client";

import Link from "next/link";
import { useRef } from "react";
import { gsap, useGSAP } from "@/lib/gsapConfig";

export interface MarqueeItem {
  id: number;
  name: string;
}

/**
 * A seamless, infinitely-looping editorial ticker of company wordmarks — the black
 * square glyph from the masthead separates each name. The track holds the list twice
 * and translates by exactly -50%, so the second copy lands where the first began and
 * the loop never seams.
 *
 * Reduced-motion (CSS, prefers-reduced-motion): the viewport stops clipping, the track
 * wraps to multiple readable lines, and the duplicated copy is hidden — a static,
 * legible wall instead of frozen scrolling text.
 */
export function Marquee({ items }: { items: MarqueeItem[] }) {
  const trackRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        // Duration scales with item count so speed stays constant regardless of list size.
        const tween = gsap.to(trackRef.current, {
          xPercent: -50,
          ease: "none",
          repeat: -1,
          duration: Math.max(20, items.length * 1.6),
        });
        return () => tween.kill();
      });
    },
    { scope: trackRef },
  );

  const row = (dup: boolean) =>
    items.map((c) => (
      <Link
        key={`${dup ? "b" : "a"}-${c.id}`}
        href={`/jobs?company_id=${c.id}`}
        aria-hidden={dup || undefined}
        tabIndex={dup ? -1 : undefined}
        className="marquee-item group flex shrink-0 items-center gap-6 px-6 font-display text-4xl font-medium text-foreground transition-opacity duration-100 hover:opacity-50 md:text-6xl"
      >
        {c.name}
        <span className="h-2 w-2 shrink-0 bg-foreground md:h-2.5 md:w-2.5" aria-hidden />
      </Link>
    ));

  return (
    <div className="marquee-viewport relative mt-12 overflow-hidden">
      <div ref={trackRef} className="marquee-track flex w-max flex-nowrap items-center">
        {row(false)}
        <div className="marquee-dup flex flex-nowrap items-center" aria-hidden>
          {row(true)}
        </div>
      </div>
    </div>
  );
}
