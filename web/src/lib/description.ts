/**
 * Job descriptions as typed blocks (the API's `description_blocks`, see
 * api/app/ingest/description.py). The web renders these as React elements, never as
 * HTML, so posting markup can't reach the page.
 *
 * Older APIs send only `description_text` (plain text). `descriptionBlocks` turns that
 * into the same shape with the rules the API uses for legacy rows: one paragraph per
 * line, and runs of bulleted lines become a list.
 */

export type Inline =
  | { type: "text"; text: string }
  | { type: "break" }
  | { type: "strong" | "em"; content: Inline[] }
  | { type: "link"; href: string; content: Inline[] };

export interface ListItem {
  content: Inline[];
  children: ListBlock[];
}

export interface ListBlock {
  type: "list";
  ordered: boolean;
  items: ListItem[];
}

export type DescriptionBlock =
  | { type: "paragraph"; content: Inline[] }
  | { type: "heading"; level: 2 | 3 | 4; content: Inline[] }
  | ListBlock;

const BULLET = /^\s*(?:[•·▪◦‣●○■□–]|[-*])\s+/;

export function legacyBlocks(text: string | null | undefined): DescriptionBlock[] {
  if (!text) return [];
  const blocks: DescriptionBlock[] = [];
  let bullets: ListItem[] = [];
  const flush = () => {
    if (bullets.length) blocks.push({ type: "list", ordered: false, items: bullets });
    bullets = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = BULLET.exec(line);
    const rest = m ? line.slice(m[0].length).trim() : "";
    if (m && rest) {
      bullets.push({ content: [{ type: "text", text: rest }], children: [] });
      continue;
    }
    flush();
    blocks.push({ type: "paragraph", content: [{ type: "text", text: line }] });
  }
  flush();
  return blocks;
}

/** Only these URL schemes ever become links (the API enforces the same list). */
export function isSafeHref(href: unknown): href is string {
  return typeof href === "string" && /^(https?:\/\/|mailto:)/i.test(href.trim());
}

export function descriptionBlocks(job: {
  description_blocks?: DescriptionBlock[] | null;
  description_text?: string | null;
}): DescriptionBlock[] {
  if (Array.isArray(job.description_blocks) && job.description_blocks.length > 0) {
    return job.description_blocks;
  }
  return legacyBlocks(job.description_text);
}

/** Plain text of inline content (for headings' ids and tests). */
export function inlineText(content: Inline[]): string {
  return content
    .map((n) => (n.type === "text" ? n.text : n.type === "break" ? "\n" : inlineText(n.content)))
    .join("");
}

/** A short plain-text summary for meta tags when the API doesn't send one. */
export function summarize(text: string | null | undefined, limit = 180): string | null {
  if (!text) return null;
  const flat = text.replace(/\s+/g, " ").trim();
  if (!flat) return null;
  if (flat.length <= limit) return flat;
  const cut = flat.slice(0, limit - 1);
  const space = cut.lastIndexOf(" ");
  return (space > limit / 2 ? cut.slice(0, space) : cut).replace(/[ ,.;:]+$/, "") + "…";
}
