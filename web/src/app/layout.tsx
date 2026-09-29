import type { Metadata } from "next";
import { Playfair_Display, Source_Serif_4, Inter } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { SiteFooter } from "@/components/SiteFooter";
import { SessionWrapper } from "@/components/SessionWrapper";
import { getMeta } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

const display = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-display",
});
// Reading font for descriptions and the landing lede: never above the feed's fold, so it
// isn't preloaded (one less font on the critical path of the LCP card title).
const body = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-body",
  preload: false,
});
const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

// Static metadata makes no refresh-cadence claim: freshness is measured, not promised
// (see the /meta-backed copy on the landing page and feed).
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Chronicle — Every open role. Every company.",
    template: "%s · Chronicle",
  },
  description:
    "Chronicle aggregates job listings from top tech companies' own career pages into one searchable feed.",
  openGraph: { siteName: "Chronicle", type: "website" },
};

// Constant string (no user data): the saved theme choice, else the system setting.
const THEME_SCRIPT = `(function(){var d=document.documentElement;d.classList.add('js');var t=null;try{t=localStorage.getItem('chronicle-theme');}catch(e){}var dark=t==='dark'||(t!=='light'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(dark)d.classList.add('dark');})();`;

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Live company total for the nav badge — cached via getMeta's ISR (revalidate 300).
  // Tolerate the API being down so the layout never fails to render.
  const meta = await getMeta().catch(() => null);

  return (
    // suppressHydrationWarning: the inline script below adds `js` (and maybe `dark`) to
    // this element's class before React hydrates (one attribute, this element only).
    <html
      lang="en"
      className={`${display.variable} ${body.variable} ${sans.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Runs before first paint: adds `js` (scroll-reveal "before" states in globals.css
            apply only under `.js`, so without JavaScript every entrance renders in its final
            state) and the `dark` class from the saved choice or the system setting, so the
            page never flashes the wrong theme. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[10000] focus:bg-foreground focus:px-4 focus:py-2 focus:font-sans focus:text-xs focus:uppercase focus:tracking-[0.15em] focus:text-background"
        >
          Skip to content
        </a>
        <SessionWrapper>
          <Nav companyCount={meta?.total_companies ?? null} />
          {children}
          <SiteFooter />
        </SessionWrapper>
      </body>
    </html>
  );
}
