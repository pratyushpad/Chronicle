"use client";
import { SessionProvider } from "next-auth/react";
import { LazyMotion, domAnimation } from "motion/react";

export function SessionWrapper({ children }: { children: React.ReactNode }) {
  // LazyMotion + domAnimation loads only the ~5kb DOM animation feature set (vs the
  // full ~34kb `motion` runtime). `strict` makes any stray `motion.*` throw, forcing
  // every consumer to use the lightweight `m` component and hold the Lighthouse budget.
  return (
    <SessionProvider>
      <LazyMotion features={domAnimation} strict>
        {children}
      </LazyMotion>
    </SessionProvider>
  );
}
