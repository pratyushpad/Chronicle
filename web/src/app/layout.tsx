import type { Metadata } from "next";
import { Playfair_Display, Source_Sans_3, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { SessionWrapper } from "@/components/SessionWrapper";

const display = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-display",
});
const body = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-body",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Chronicle — Every open role. Every company.",
  description:
    "Chronicle aggregates job listings from top tech companies into one searchable feed. Refreshed every 48 hours.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${body.variable} ${mono.variable}`}
    >
      <body className="min-h-screen antialiased">
        <SessionWrapper>
          <Nav />
          {children}
        </SessionWrapper>
      </body>
    </html>
  );
}
