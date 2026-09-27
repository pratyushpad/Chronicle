import type { Config } from "tailwindcss";
import { cssDuration, cssEase, duration } from "./src/lib/motion";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          secondary: "var(--accent-secondary)",
          foreground: "var(--accent-foreground)",
        },
        border: "var(--border)",
        "border-light": "var(--border-light)",
        input: "var(--input)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        ring: "var(--ring)",
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "monospace"],
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
