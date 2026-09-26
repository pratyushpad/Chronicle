import { describe, expect, it } from "vitest";
import { descriptionBlocks, inlineText, isSafeHref, legacyBlocks, summarize } from "./description";

describe("legacyBlocks", () => {
  it("makes one paragraph per line and a list from bulleted runs", () => {
    // Real legacy text shape (PR 1 stored plain text with a newline per block).
    const text =
      "Zipline is the world’s largest drone delivery service.\n• Design embedded firmware\n• Bring up new boards\nPay: $54/hr";
    expect(legacyBlocks(text)).toEqual([
      { type: "paragraph", content: [{ type: "text", text: "Zipline is the world’s largest drone delivery service." }] },
      {
        type: "list",
        ordered: false,
        items: [
          { content: [{ type: "text", text: "Design embedded firmware" }], children: [] },
          { content: [{ type: "text", text: "Bring up new boards" }], children: [] },
        ],
      },
      { type: "paragraph", content: [{ type: "text", text: "Pay: $54/hr" }] },
    ]);
  });

  it("keeps markup-looking text as text", () => {
    const [block] = legacyBlocks("<script>alert(1)</script>");
    expect(block).toEqual({ type: "paragraph", content: [{ type: "text", text: "<script>alert(1)</script>" }] });
  });

  it("returns nothing for empty text", () => {
    expect(legacyBlocks(null)).toEqual([]);
    expect(legacyBlocks(" \n ")).toEqual([]);
  });
});

describe("descriptionBlocks", () => {
  it("prefers the API's blocks and falls back to the plain text", () => {
    const blocks = [{ type: "paragraph" as const, content: [{ type: "text" as const, text: "From API" }] }];
    expect(descriptionBlocks({ description_blocks: blocks, description_text: "ignored" })).toBe(blocks);
    expect(descriptionBlocks({ description_text: "Old API" })[0]).toEqual({
      type: "paragraph",
      content: [{ type: "text", text: "Old API" }],
    });
    expect(descriptionBlocks({ description_blocks: [], description_text: "Empty list" })).toHaveLength(1);
  });
});

describe("isSafeHref", () => {
  it("allows only http, https and mailto", () => {
    expect(isSafeHref("https://example.com")).toBe(true);
    expect(isSafeHref("mailto:jobs@example.com")).toBe(true);
    expect(isSafeHref("javascript:alert(1)")).toBe(false);
    expect(isSafeHref(" JAVASCRIPT:alert(1)")).toBe(false);
    expect(isSafeHref("data:text/html,x")).toBe(false);
    expect(isSafeHref(null)).toBe(false);
  });
});

describe("inlineText and summarize", () => {
  it("flattens inline content", () => {
    expect(
      inlineText([
        { type: "text", text: "Pay " },
        { type: "strong", content: [{ type: "text", text: "$45" }] },
        { type: "break" },
        { type: "link", href: "https://x.test", content: [{ type: "text", text: "benefits" }] },
      ]),
    ).toBe("Pay $45\nbenefits");
  });

  it("cuts at a word boundary with an ellipsis", () => {
    const s = summarize("word ".repeat(100), 40)!;
    expect(s.length).toBeLessThanOrEqual(40);
    expect(s.endsWith("…")).toBe(true);
    expect(summarize("Short.")).toBe("Short.");
    expect(summarize("")).toBeNull();
  });
});
