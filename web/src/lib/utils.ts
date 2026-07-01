import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Date unknown";
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
  }).format(new Date(iso));
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

// Words that should render fully uppercase (countries, states, common abbrevs).
const UPPER_TOKENS = new Set([
  "usa", "us", "uk", "uae", "eu", "us", "nyc", "sf", "la", "dc", "emea", "apac", "na",
  "hq", // handled separately for trailing strip, but uppercased if kept inline
]);
// US state abbreviations to keep uppercase.
const STATE_ABBR = new Set([
  "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in","ia","ks","ky",
  "la","me","md","ma","mi","mn","ms","mo","mt","ne","nv","nh","nj","nm","ny","nc","nd",
  "oh","ok","or","pa","ri","sc","sd","tn","tx","ut","vt","va","wa","wv","wi","wy",
]);

function titleCaseToken(token: string): string {
  const lower = token.toLowerCase();
  if (UPPER_TOKENS.has(lower) || STATE_ABBR.has(lower)) return lower.toUpperCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/**
 * Cleans raw, lower-cased ATS location strings into presentable form.
 * - title-cases words, uppercases countries/states (USA, NY)
 * - collapses duplicate "City, City" → "City"
 * - strips trailing "hq"
 * - normalizes "united states of america" / "united states" → "USA"
 * - passes through "Remote"
 */
export function formatLocation(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw.trim();
  if (!s) return "";

  // Normalize common country long-forms before tokenizing.
  s = s.replace(/united states of america/gi, "USA")
       .replace(/united states/gi, "USA")
       .replace(/united kingdom/gi, "UK");

  // Split on commas, format each segment, drop empties / trailing "hq".
  let parts = s
    .split(",")
    .map((seg) => seg.trim())
    .filter(Boolean)
    .map((seg) =>
      seg
        .split(/\s+/)
        .filter((w) => w.toLowerCase() !== "hq")
        .map(titleCaseToken)
        .join(" ")
        .trim()
    )
    .filter(Boolean);

  // Collapse consecutive duplicate segments ("New York, New York" → "New York").
  parts = parts.filter((seg, i) => i === 0 || seg.toLowerCase() !== parts[i - 1].toLowerCase());

  return parts.join(", ");
}

/**
 * Passthrough for the department label. Normalization now happens server-side at
 * ingest (see api/app/ingest/normalize.py `normalize_department`) — the API returns a
 * clean controlled-vocab category ("Sales", "Engineering", "G&A", "IT", "Other") or
 * null. We only trim; deliberately no re-casing (would break "G&A"/"IT") and no
 * segment peeling (the old client-side cleanup leaked internal org names).
 */
export function formatDepartment(raw: string | null | undefined): string {
  return raw?.trim() ?? "";
}
