import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Reads the real token blocks from globals.css so the check can't drift from the CSS.
const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start).toBeGreaterThan(-1);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(Array.from(body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g), (m) => [m[1], m[2]]));
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [text token, background token] pairs the UI actually uses for text.
const PAIRS: [string, string][] = [
  ["foreground", "background"],
  ["foreground", "card"],
  ["foreground", "muted"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["accent-foreground", "accent"],
  ["primary-foreground", "primary"],
  ["positive", "background"],
  ["positive", "positive-bg"],
  ["warning", "background"],
  ["warning", "warning-bg"],
  ["negative", "background"],
  ["negative", "negative-bg"],
];

describe.each([":root", ".dark"])("tokens in %s", (selector) => {
  const t = block(selector);
  it.each(PAIRS)("%s on %s meets WCAG AA (4.5:1)", (fg, bg) => {
    expect(t[fg], fg).toBeDefined();
    expect(t[bg], bg).toBeDefined();
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
  });
});

describe("dark theme", () => {
  it("defines every token the light theme defines", () => {
    const light = Object.keys(block(":root"));
    const dark = block(".dark");
    expect(light.filter((k) => !(k in dark) && k !== "radius")).toEqual([]);
  });
});

describe.each([":root", ".dark"])("control borders in %s", (selector) => {
  it("are at least 3:1 against the page and cards (WCAG 1.4.11)", () => {
    const t = block(selector);
    expect(contrast(t.input, t.background)).toBeGreaterThanOrEqual(3);
    expect(contrast(t.input, t.card)).toBeGreaterThanOrEqual(3);
  });
});
