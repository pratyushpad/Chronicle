"use client";

import { useRef } from "react";
import { SplitText } from "gsap/SplitText";
import { gsap, useGSAP } from "@/lib/gsapConfig";

// Registered here (not in gsapConfig) so SplitText stays out of every non-landing bundle.
if (typeof window !== "undefined") gsap.registerPlugin(SplitText);

/**
 * The landing page's Largest Contentful Paint element, so LCP safety is load-bearing:
 * the full headline is server-rendered as plain, painted, visible text — LCP is captured
 * at that first paint, before any JS runs. Only after hydration does useGSAP (a layout
 * effect) split the words and set their reveal "from" state, all before the next browser
 * paint, so there is no flash of un-animated text and the early LCP timestamp stands.
 *
 * The reveal is a masked line wipe: each line clips its overflow, words rise up from
 * beneath the baseline. Reduced-motion skips the split entirely and leaves the static
 * server-rendered text in place.
 */
export function HeroHeadline() {
  const ref = useRef<HTMLHeadingElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const split = SplitText.create(ref.current!.querySelectorAll("[data-line]"), {
          type: "words",
          wordsClass: "hero-word",
        });
        const tween = gsap.from(split.words, {
          yPercent: 120,
          duration: 0.9,
          ease: "chronicle",
          stagger: 0.07,
        });
        return () => {
          tween.kill();
          split.revert();
        };
      });
      // Reduced-motion branch: nothing to do — server-rendered text stays as-is.
    },
    { scope: ref },
  );

  // Each line clips its overflow so words can rise into place from below; the bottom
  // padding + negative margin gives Playfair's descenders room so the clip never cuts them.
  const lineStyle = { overflow: "hidden", paddingBottom: "0.14em", marginBottom: "-0.14em" };

  return (
    <h1 className="mt-12 font-display text-6xl font-medium leading-[0.95] tracking-tight text-foreground sm:text-7xl md:mt-16 md:text-8xl lg:text-9xl">
      <span data-line className="block" style={lineStyle}>
        Every open
      </span>
      <span data-line className="block" style={lineStyle}>
        role. Every
      </span>
      <span data-line className="block" style={lineStyle}>
        <span className="italic">company.</span>
      </span>
    </h1>
  );
}
