import type { Config } from "tailwindcss";
import { cssDuration, cssEase, duration } from "./src/lib/motion";

// Theme colors are CSS variables (hex, switched by .dark), so Tailwind can't apply an
// opacity modifier to them directly: `bg-background/95` generated nothing. <alpha-value>
// inside color-mix makes modifiers work; without one it is 1, i.e. the plain color.
const tok = (name: string) =>
  `color-mix(in srgb, var(--${name}) calc(<alpha-value> * 100%), transparent)`;

const config: Config = {
  // Dark mode follows the system unless the reader picks one (ThemeToggle); an inline
  // script in app/layout.tsx sets the class before first paint, so there's no flash.
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: tok("background"),
        foreground: tok("foreground"),
        muted: {
          DEFAULT: tok("muted"),
          foreground: tok("muted-foreground"),
        },
        accent: {
          DEFAULT: tok("accent"),
          secondary: tok("accent-secondary"),
          foreground: tok("accent-foreground"),
        },
        border: tok("border"),
        "border-light": tok("border-light"),
        input: tok("input"),
        card: {
          DEFAULT: tok("card"),
          foreground: tok("card-foreground"),
        },
        ring: tok("ring"),
        popover: {
          DEFAULT: tok("popover"),
          foreground: tok("popover-foreground"),
        },
        primary: {
          DEFAULT: tok("primary"),
          foreground: tok("primary-foreground"),
        },
        secondary: {
          DEFAULT: tok("secondary"),
          foreground: tok("secondary-foreground"),
        },
        positive: { DEFAULT: tok("positive"), bg: tok("positive-bg") },
        warning: { DEFAULT: tok("warning"), bg: tok("warning-bg") },
        negative: { DEFAULT: tok("negative"), bg: tok("negative-bg") },
      },
      fontFamily: {
        // Playfair: display headings and job titles only. Inter: all UI chrome and copy.
        // Source Serif: long-form reading (job descriptions, the landing lede).
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        body: ["var(--font-body)", "Georgia", "serif"],
      },
      fontSize: {
        // Dramatic editorial scale — words become graphic elements
        "7xl": ["6rem", { lineHeight: "1" }],
        "8xl": ["8rem", { lineHeight: "1" }],
        "9xl": ["10rem", { lineHeight: "1" }],
      },
      // Motion vocabulary, generated from src/lib/motion.ts (the single source of truth).
      transitionTimingFunction: {
        house: cssEase,
      },
      transitionDuration: {
        fast: cssDuration(duration.fast),
        base: cssDuration(duration.base),
        slow: cssDuration(duration.slow),
      },
      keyframes: {
        // Entrance "print": fade + rise from --reveal-y into the element's resting state.
        "reveal-rise": {
          from: { opacity: "0", transform: "translate3d(0, var(--reveal-y, 8px), 0)" },
        },
      },
      animation: {
        // `backwards` holds the hidden frame only during the stagger delay and never pins
        // the end state, so hover/press transforms keep working after the entrance.
        reveal: `reveal-rise ${cssDuration(duration.base)} ${cssEase} var(--reveal-delay, 0s) backwards`,
      },
      // Minimalist Monochrome: no depth from shadows, no rounded corners.
      boxShadow: {
        sm: "none",
        md: "none",
        lg: "none",
      },
      borderRadius: {
        none: "0px",
        sm: "0px",
        md: "0px",
        lg: "0px",
        xl: "0px",
        "2xl": "0px",
        "3xl": "0px",
        full: "0px",
        DEFAULT: "0px",
      },
    },
  },
  plugins: [],
};

export default config;
