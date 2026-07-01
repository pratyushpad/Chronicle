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

// Umbrella finance/org buckets that prefix a real department ("S&M - Sales").
const DEPT_GROUP_PREFIXES = new Set(["s&m", "g&a", "r&d", "ga", "sm", "cogs"]);

/**
 * Cleans raw ATS department strings — CONSERVATIVELY, to avoid mangling
 * companies whose departments aren't Block-shaped.
 * - strips a leading numeric/req code block ("20213 ", "REQ-123 ")
 * - drops only a LEADING umbrella-group prefix ("S&M - Sales" → "Sales")
 * - KEEPS the parent→child chain otherwise ("Sales - EMEA" stays "Sales - EMEA",
 *   "Engineering - Infra" stays intact) — never reduces to the last segment.
 * The DB value is untouched; this is display-only.
 */
export function formatDepartment(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw.trim();
  if (!s) return "";

  // Drop a leading numeric/req code block ("20213 ", "REQ-123 ").
  s = s.replace(/^[\s#]*[A-Za-z]*-?\d[\w-]*\s+/, "");

  // Peel off leading umbrella-group prefixes only; keep the rest of the chain.
  const segs = s.split(/\s*[-/|·]\s*/).map((seg) => seg.trim()).filter(Boolean);
  while (segs.length > 1 && DEPT_GROUP_PREFIXES.has(segs[0].toLowerCase())) segs.shift();

  return segs.join(" - ").replace(/\s+/g, " ").trim() || s;
}
