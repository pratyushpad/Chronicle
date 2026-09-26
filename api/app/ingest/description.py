"""Posting descriptions: raw ATS HTML → a stored, sanitized HTML subset → typed blocks.

Stored format (jobs.description_text). New rows hold a small HTML subset:

    p, ul, ol, li, h2, h3, h4, strong, em, a[href: http, https, mailto], br

`sanitize_description` emits it with an allowlisting walker that escapes every piece of
text, so nothing from the ATS reaches the page as markup. The output always starts with a
block tag, and that prefix is the format marker. Any other stored value is legacy plain
text: it is escaped and split into paragraphs, and never parsed as HTML.

The API never sends the stored HTML. `description_blocks` turns either format into typed
blocks (JSON), and the web renders those as React elements, so the page has no
`dangerouslySetInnerHTML`. `description_plain` gives the readable text of either format,
which is what the embedding and the backward-compatible `description_text` field read.

The stored form is presentation only. Every extractor (pay, tags, sponsorship) and the
content hash read `plain_text` of the RAW HTML, so reformatting descriptions never changes
a hash and never re-embeds a row.
"""
from __future__ import annotations

import html
import re
from typing import Any

from selectolax.parser import HTMLParser, Node

from .normalize import plain_text

# The stored subset's block tags. A stored value that starts with one of these is structured.
_STORED_BLOCK_PREFIXES = ("<p>", "<ul>", "<ol>", "<h2>", "<h3>", "<h4>")

# Never text (same list as normalize._DROP_TAGS, plus form controls and media).
_DROP_TAGS = frozenset({
    "script", "style", "noscript", "template", "head", "svg", "iframe", "object",
    "embed", "canvas", "math", "title", "button", "input", "select", "textarea",
    "img", "video", "audio", "picture", "source", "form", "link", "meta",
})
_HEADING_LEVEL = {"h1": 2, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}
_INLINE_WRAP = {"strong": "strong", "b": "strong", "em": "em", "i": "em"}
# Elements that start a new line in a browser: their content becomes its own paragraph.
_BREAK_TAGS = frozenset({
    "p", "div", "section", "article", "header", "footer", "main", "aside", "nav",
    "blockquote", "pre", "figure", "figcaption", "address", "details", "summary",
    "center", "fieldset", "dl", "dt", "dd", "hr", "table", "thead", "tbody", "tfoot",
    "tr", "caption", "body", "html",
})
_CELL_TAGS = frozenset({"td", "th"})
_SAFE_HREF_RE = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿]")
_TAG_RE = re.compile(r"<[^>]*>")
_BR_TRIM_RE = re.compile(r"(?:\s*<br>\s*)+")
_PSEUDO_HEADING_RE = re.compile(r"^<strong>(.*)</strong>(:?)$", re.DOTALL)
# Deeper than this, a subtree is flattened to its text (posting HTML nests arbitrarily,
# and the walker must never hit Python's recursion limit mid-ingest).
_MAX_DEPTH = 120
# Leading bullet glyphs a legacy plain-text line may carry.
_LEGACY_BULLET_RE = re.compile(r"^\s*(?:[•·▪◦‣●○■□–]|[-*])\s+")

# Fragment segments produced by the walker.
_INLINE, _BREAK, _BLOCK = 0, 1, 2


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _safe_href(node: Node) -> str | None:
    href = (node.attributes.get("href") or "").strip()
    href = _ZERO_WIDTH_RE.sub("", href)
    if not href or any(c in href for c in "\n\r\t ") or not _SAFE_HREF_RE.match(href):
        return None
    return html.escape(href, quote=True)


def _text_of(markup: str) -> str:
    return html.unescape(_TAG_RE.sub("", markup))


def _render(node: Node, depth: int) -> list[tuple[int, str]]:
    """Walk one node into segments: (_INLINE, html) runs of inline markup,
    (_BREAK, "") paragraph boundaries and (_BLOCK, html) finished blocks (headings, lists)."""
    tag = node.tag
    if tag == "-text":
        text = _ZERO_WIDTH_RE.sub("", node.text(deep=False) or "")
        return [(_INLINE, _esc(_WS_RE.sub(" ", text)))] if text else []
    if tag in _DROP_TAGS or tag == "_comment" or tag is None:
        return []
    if depth > _MAX_DEPTH:
        text = _WS_RE.sub(" ", _ZERO_WIDTH_RE.sub("", node.text(deep=True) or "")).strip()
        return [(_BREAK, ""), (_INLINE, _esc(text)), (_BREAK, "")] if text else []
    if tag == "br":
        return [(_INLINE, "<br>")]

    children: list[tuple[int, str]] = []
    for child in node.iter(include_text=True):
        children.extend(_render(child, depth + 1))

    if tag in _HEADING_LEVEL:
        inner = _inline_only(children)
        if not _text_of(inner).strip():
            return []
        level = _HEADING_LEVEL[tag]
        return [(_BLOCK, f"<h{level}>{inner}</h{level}>")]
    if tag in ("ul", "ol"):
        return _list(node, tag, depth)
    if tag == "li":
        # A stray <li> outside a list reads as a paragraph.
        return [(_BREAK, "")] + children + [(_BREAK, "")]
    if tag in _INLINE_WRAP or tag == "a":
        if any(kind != _INLINE for kind, _ in children):
            return children  # a wrapper around blocks can't stay inline: drop the wrapper
        inner = "".join(h for _, h in children)
        if not _text_of(inner).strip():
            return children
        if tag == "a":
            href = _safe_href(node)
            return [(_INLINE, f'<a href="{href}">{inner}</a>')] if href else children
        wrap = _INLINE_WRAP[tag]
        # <b><strong>x</strong></b> is still just bold: never nest a tag in itself.
        inner = inner.replace(f"<{wrap}>", "").replace(f"</{wrap}>", "")
        return [(_INLINE, f"<{wrap}>{inner}</{wrap}>")]
    if tag in _CELL_TAGS:
        return [(_INLINE, " ")] + children + [(_INLINE, " ")]
    if tag in _BREAK_TAGS:
        return [(_BREAK, "")] + children + [(_BREAK, "")]
    return children  # span, font, u, small, unknown tags: keep the content only


def _inline_only(segments: list[tuple[int, str]]) -> str:
    """Flatten segments into one inline run (for a heading or a list item's text):
    paragraph breaks become <br>, nested block markup is reduced to its text."""
    out: list[str] = []
    for kind, markup in segments:
        if kind == _INLINE:
            out.append(markup)
        elif kind == _BREAK:
            out.append("<br>")
        else:
            out.append("<br>" + _esc(_text_of(markup)) + "<br>")
    return _tidy_inline("".join(out))


def _tidy_inline(markup: str) -> str:
    markup = _WS_RE.sub(" ", markup)
    markup = _BR_TRIM_RE.sub("<br>", markup)
    while markup.startswith("<br>") or markup.startswith(" "):
        markup = markup[4:] if markup.startswith("<br>") else markup[1:]
    while markup.endswith("<br>") or markup.endswith(" "):
        markup = markup[:-4] if markup.endswith("<br>") else markup[:-1]
    return markup


def _list(node: Node, tag: str, depth: int) -> list[tuple[int, str]]:
    items: list[str] = []
    for child in node.iter(include_text=True):
        segs = _render(child, depth + 1) if child.tag != "li" else [
            s for c in child.iter(include_text=True) for s in _render(c, depth + 2)
        ]
        # Nested lists stay nested; everything else in the item is its inline text.
        text_segs = [s for s in segs if not (s[0] == _BLOCK and s[1][:4] in ("<ul>", "<ol>"))]
        nested = "".join(s[1] for s in segs if s[0] == _BLOCK and s[1][:4] in ("<ul>", "<ol>"))
        inner = _inline_only(text_segs)
        if not _text_of(inner).strip() and not nested:
            continue
        items.append(f"<li>{inner}{nested}</li>")
    if not items:
        return []
    return [(_BLOCK, f"<{tag}>{''.join(items)}</{tag}>")]


def _split_top_level_br(markup: str) -> list[str]:
    """Split inline markup at <br> tags that sit outside any strong/em/a element."""
    lines, depth, start = [], 0, 0
    for m in _TAG_RE.finditer(markup):
        tag = m.group(0)
        if tag == "<br>":
            if depth == 0:
                lines.append(markup[start:m.start()])
                start = m.end()
        elif tag.startswith("</"):
            depth -= 1
        else:
            depth += 1
    lines.append(markup[start:])
    return lines


def _pseudo_heading(line: str) -> str | None:
    """A line that is nothing but one short bold phrase ("<strong>What you'll do</strong>")
    is a section heading in all but name. Returns its inner markup, or None."""
    line = line.strip()
    m = _PSEUDO_HEADING_RE.match(line)
    if not m or "<strong>" in m.group(1) or "<br>" in m.group(1):
        return None
    text = _text_of(m.group(1)).strip()
    if not text or len(text) > 80 or text.endswith((".", ",", ";")):
        return None
    return m.group(1).strip() + m.group(2)


def _paragraph_blocks(inner: str) -> list[str]:
    out: list[str] = []
    lines: list[str] = []

    def flush_lines() -> None:
        body = _tidy_inline("<br>".join(lines))
        lines.clear()
        if _text_of(body).strip():
            out.append(f"<p>{body}</p>")

    for line in _split_top_level_br(inner):
        heading = _pseudo_heading(line)
        if heading is not None:
            flush_lines()
            out.append(f"<h3>{heading}</h3>")
        else:
            lines.append(line)
    flush_lines()
    return out


def _append_block(blocks: list[str], block: str) -> None:
    # ATS editors often wrap every bullet in its own list: merge adjacent lists of one kind.
    kind = block[:4]
    if kind in ("<ul>", "<ol>") and blocks and blocks[-1][:4] == kind:
        blocks[-1] = blocks[-1][:-5] + block[4:]
    else:
        blocks.append(block)


def _blocks_from_segments(segments: list[tuple[int, str]]) -> list[str]:
    blocks: list[str] = []
    run: list[str] = []

    def flush() -> None:
        inner = _tidy_inline("".join(run))
        run.clear()
        for block in _paragraph_blocks(inner):
            _append_block(blocks, block)

    for kind, markup in segments:
        if kind == _INLINE:
            run.append(markup)
        else:
            flush()
            if kind == _BLOCK:
                _append_block(blocks, markup)
    flush()
    return blocks


def sanitize_description(raw_html: str | None, max_chars: int) -> str | None:
    """Raw ATS HTML → the stored subset (None when the posting has no text).

    Whole blocks are kept until `max_chars` would be exceeded, so the output is always
    well-formed. A first block longer than the budget is kept as escaped text, cut to fit.
    """
    if not raw_html or not raw_html.strip():
        return None
    root = HTMLParser(raw_html).body or HTMLParser(raw_html).root
    if root is None:
        return None
    segments: list[tuple[int, str]] = []
    for child in root.iter(include_text=True):
        segments.extend(_render(child, 1))
    blocks = _blocks_from_segments(segments)
    out: list[str] = []
    used = 0
    for block in blocks:
        if used + len(block) > max_chars:
            room = max_chars - used - len("<p></p>")
            if not out and room > 0:
                text = _WS_RE.sub(" ", _text_of(block)).strip()
                # Cut the TEXT, then escape; trim until the escaped form fits.
                cut = text[:room]
                while cut and len(_esc(cut)) > room:
                    cut = cut[: len(cut) - (len(_esc(cut)) - room)]
                if cut.strip():
                    out.append(f"<p>{_esc(cut.rstrip())}</p>")
            break
        out.append(block)
        used += len(block)
    return "".join(out) or None


def is_structured(stored: str | None) -> bool:
    return bool(stored) and stored.startswith(_STORED_BLOCK_PREFIXES)


def description_plain(stored: str | None) -> str | None:
    """Readable text of a stored description in either format."""
    if not stored:
        return None
    if is_structured(stored):
        return plain_text(stored)
    return stored


# ── Stored form → typed blocks (the API's shape) ─────────────────────────────

def _inlines(node: Node, depth: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            text = child.text(deep=False) or ""
            if text:
                if out and out[-1]["type"] == "text":
                    out[-1]["text"] += text
                else:
                    out.append({"type": "text", "text": text})
        elif tag == "br":
            out.append({"type": "break"})
        elif depth > _MAX_DEPTH:
            text = child.text(deep=True) or ""
            if text:
                out.append({"type": "text", "text": text})
        elif tag in ("strong", "em"):
            content = _inlines(child, depth + 1)
            if content:
                out.append({"type": tag, "content": content})
        elif tag == "a":
            content = _inlines(child, depth + 1)
            href = (child.attributes.get("href") or "").strip()
            if content and _SAFE_HREF_RE.match(href):
                out.append({"type": "link", "href": href, "content": content})
            else:
                out.extend(content)
        elif tag in ("ul", "ol"):
            continue  # nested lists are handled by the list item
        else:
            out.extend(_inlines(child, depth + 1))  # never trust markup: unknown → its text
    return out


def _list_block(node: Node, depth: int) -> dict[str, Any] | None:
    items = []
    for li in node.iter(include_text=False):
        if li.tag != "li":
            continue
        children = [
            b for c in li.iter(include_text=False) if c.tag in ("ul", "ol") and depth < _MAX_DEPTH
            for b in [_list_block(c, depth + 1)] if b
        ]
        content = _inlines(li, depth + 1)
        if content or children:
            items.append({"content": content, "children": children})
    if not items:
        return None
    return {"type": "list", "ordered": node.tag == "ol", "items": items}


def _structured_blocks(stored: str) -> list[dict[str, Any]]:
    tree = HTMLParser(stored)
    root = tree.body or tree.root
    blocks: list[dict[str, Any]] = []
    if root is None:
        return blocks
    for node in root.iter(include_text=True):
        tag = node.tag
        if tag in ("h2", "h3", "h4"):
            content = _inlines(node)
            if content:
                blocks.append({"type": "heading", "level": int(tag[1]), "content": content})
        elif tag in ("ul", "ol"):
            block = _list_block(node, 1)
            if block:
                blocks.append(block)
        elif tag == "-text":
            text = (node.text(deep=False) or "").strip()
            if text:
                blocks.append({"type": "paragraph", "content": [{"type": "text", "text": text}]})
        else:
            content = _inlines(node)
            if content:
                blocks.append({"type": "paragraph", "content": content})
    return blocks


def _legacy_blocks(stored: str) -> list[dict[str, Any]]:
    """Legacy plain text: one paragraph per line; runs of bulleted lines become a list."""
    blocks: list[dict[str, Any]] = []
    bullets: list[dict[str, Any]] = []

    def flush_list() -> None:
        if bullets:
            blocks.append({"type": "list", "ordered": False, "items": list(bullets)})
            bullets.clear()

    for line in stored.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _LEGACY_BULLET_RE.match(line)
        if m and line[m.end():].strip():
            bullets.append({"content": [{"type": "text", "text": line[m.end():].strip()}], "children": []})
            continue
        flush_list()
        blocks.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
    flush_list()
    return blocks


def description_blocks(stored: str | None) -> list[dict[str, Any]]:
    if not stored:
        return []
    if is_structured(stored):
        return _structured_blocks(stored)
    return _legacy_blocks(stored)


def description_summary(stored: str | None, limit: int = 180) -> str | None:
    """First sentence-ish of the description, for meta descriptions and social cards."""
    text = description_plain(stored)
    if not text:
        return None
    text = _WS_RE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,.;:") + "…"
