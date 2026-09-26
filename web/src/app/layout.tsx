import type { Metadata } from "next";
import { Playfair_Display, Source_Serif_4, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { SessionWrapper } from "@/components/SessionWrapper";
import { RouteCurtain } from "@/components/gsap/RouteCurtain";
import { getMeta } from "@/lib/api";

const display = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-display",
});
const body = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-body",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500"],
  variable: "--font-mono",
});

// Static metadata makes no refresh-cadence claim: freshness is measured, not promised
// (see the /meta-backed copy on the landing page and feed).
export const metadata: Metadata = {
  title: "Chronicle — Every open role. Every company.",
  description:
    "Chronicle aggregates job listings from top tech companies' own career pages into one searchable feed.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Live company total for the nav badge — cached via getMeta's ISR (revalidate 300).
  // Tolerate the API being down so the layout never fails to render.
  const meta = await getMeta().catch(() => null);

  return (
    // suppressHydrationWarning: the inline script below adds `js` to this element's class
    // before React hydrates (one attribute, this element only).
    <html
      lang="en"
      className={`${display.variable} ${body.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Runs before first paint. Scroll-reveal "before" states in globals.css apply only
            under `.js`, so without JavaScript every entrance renders in its final state. */}
        <script
          dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.add('js')" }}
        />
      </head>
      <body className="min-h-screen antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[10000] focus:bg-foreground focus:px-4 focus:py-2 focus:font-mono focus:text-xs focus:uppercase focus:tracking-[0.15em] focus:text-background"
        >
          Skip to content
        </a>
        <SessionWrapper>
          <RouteCurtain />
          <Nav companyCount={meta?.total_companies ?? null} />
          {children}
        </SessionWrapper>
      </body>
    </html>
  );
}
