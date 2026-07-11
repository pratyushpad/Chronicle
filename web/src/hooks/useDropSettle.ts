"use client";

import { useCallback } from "react";
import { gsap } from "@/lib/gsapConfig";

/**
 * Post-drop flourish for the tracker: a subtle scale settle on the just-moved card so a
 * drop between columns lands with a deliberate beat.
 *
 * dnd-kit is the sole owner of the card *root's* transform during and right after a drag,
 * so this animates an INNER element (`[data-card-body]`) instead — the two never write the
 * same property, honouring the "never animate a node with both engines" rail. The pulse
 * runs on the next frame, after React has committed the card into its new column, and is a
 * no-op under reduced motion.
 */
export function useDropSettle() {
  return useCallback((cardId: number) => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    requestAnimationFrame(() => {
      const body = document.querySelector<HTMLElement>(
        `[data-app-card="${cardId}"] [data-card-body]`,
      );
      if (!body) return;
      gsap.fromTo(
        body,
        { scale: 0.94 },
        { scale: 1, duration: 0.35, ease: "chronicle", clearProps: "scale" },
      );
    });
  }, []);
}
