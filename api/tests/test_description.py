"""Stored descriptions (PR 2): raw ATS HTML → sanitized subset → typed blocks.

Real posting text comes from the committed fixtures (the PR 1 board payloads and the 119
labeled intern postings), so these tests exercise the markup ATS editors actually emit.
"""
import gzip
import html
import json
import re

import pytest

from app.ingest.adapters.lever import _full_description
from app.ingest.dedupe import make_content_hash
from app.ingest.description import (
    description_blocks,
    description_plain,
    description_summary,
    is_structured,
    sanitize_description,
)
from app.ingest.normalize import plain_text
from tests.conftest import FIXTURES

CAP = 20_000
_ALLOWED_TAG_RE = re.compile(r"</?(p|ul|ol|li|h2|h3|h4|strong|em|br)>|<a href=\"[^\"]*\">|</a>")


def _real_postings() -> list[tuple[str, str]]:
    out = []
    for line in gzip.open(FIXTURES / "pay_eval" / "intern_pay_labeled.jsonl.gz", "rt"):
        row = json.loads(line)
        raw = json.loads(row["raw"]) if isinstance(row["raw"], str) else row["raw"]
        if row["ats"] == "greenhouse":
            body = html.unescape(raw.get("content") or "")
        elif row["ats"] == "lever":
            body = _full_description(raw)
        else:
            body = raw.get("descriptionHtml")
        out.append((row["id"], body))
    return out


REAL = _real_postings()


def _anduril_electrical_intern() -> str:
    jobs = json.loads((FIXTURES / "pr1_greenhouse.json").read_text())["jobs"]
    job = next(j for j in jobs if j["title"] == "2027 Electrical Engineer Intern")
    return html.unescape(job["content"])


def _squash(text: str | None) -> str:
    return re.sub(r"\s", "", text or "")


# ── sanitizer ─────────────────────────────────────────────────────────────────

def test_real_postings_keep_every_word_and_only_allowed_tags():
    assert len(REAL) >= 100
    for job_id, body in REAL:
        stored = sanitize_description(body, CAP)
        if stored is None:
            assert not plain_text(body), job_id
            continue
        assert is_structured(stored), job_id
        assert len(stored) <= CAP, job_id
        leftover = _ALLOWED_TAG_RE.sub("", stored)
        assert "<" not in leftover, (job_id, leftover[leftover.index("<"):][:80])
        # The text a reader sees is the text the extractors saw (up to the cap).
        full, kept = _squash(plain_text(body)), _squash(description_plain(stored))
        assert full.startswith(kept[:-50] if len(kept) > 50 else kept), job_id
        if len(stored) < CAP - 2_000:
            assert kept == full, job_id


def test_anduril_bullets_merge_into_one_list_and_bold_lines_become_headings():
    stored = sanitize_description(_anduril_electrical_intern(), CAP)
    # The ATS wraps every bullet in its own <ul>; the page shows one list per section.
    assert "</ul><ul>" not in stored
    assert "<h3>WHAT YOU’LL DO</h3><ul><li>Design electronics" in stored
    blocks = description_blocks(stored)
    lists = [b for b in blocks if b["type"] == "list"]
    assert lists and len(lists[0]["items"]) >= 4
    assert any(b["type"] == "heading" and b["content"][0]["text"] == "WHAT YOU’LL DO" for b in blocks)


def test_inline_markup_joins_without_spaces():
    stored = sanitize_description("<p>Base pay $150,<strong>000</strong> per year</p>", CAP)
    assert description_plain(stored) == "Base pay $150,000 per year"


@pytest.mark.parametrize("payload", [
    '<p>Hi<script>alert(1)</script></p>',
    '<p><img src=x onerror="alert(1)">Hi</p>',
    '<p><a href="javascript:alert(1)">Hi</a></p>',
    '<p><a href=" JaVaScRiPt:alert(1)">Hi</a></p>',
    '<p><a href="data:text/html,<script>alert(1)</script>">Hi</a></p>',
    '<p onclick="alert(1)" style="x">Hi</p>',
    '<p><iframe src="https://evil.example"></iframe>Hi</p>',
    '<svg><script>alert(1)</script></svg><p>Hi</p>',
    '<p>Hi<style>p{color:red}</style></p>',
])
def test_markup_never_survives(payload):
    stored = sanitize_description(payload, CAP)
    assert stored == "<p>Hi</p>"


def test_text_that_looks_like_markup_is_escaped():
    stored = sanitize_description("<p>Use &lt;script&gt; tags &amp; C++ templates like vector&lt;int&gt;</p>", CAP)
    assert stored == "<p>Use &lt;script&gt; tags &amp; C++ templates like vector&lt;int&gt;</p>"
    [block] = description_blocks(stored)
    assert block["content"] == [{"type": "text", "text": "Use <script> tags & C++ templates like vector<int>"}]


def test_safe_links_are_kept_with_escaped_href():
    stored = sanitize_description(
        '<p>See <a href="https://example.com/a?b=1&amp;c=&quot;2&quot;" target="_blank">benefits</a> '
        'or <a href="mailto:jobs@example.com">email us</a></p>', CAP)
    assert '<a href="https://example.com/a?b=1&amp;c=&quot;2&quot;">benefits</a>' in stored
    links = [i for i in description_blocks(stored)[0]["content"] if i["type"] == "link"]
    assert [link["href"] for link in links] == ['https://example.com/a?b=1&c="2"', "mailto:jobs@example.com"]


def test_blocks_inside_inline_wrappers_drop_the_wrapper():
    stored = sanitize_description("<strong><p>One</p><p>Two</p></strong>", CAP)
    assert stored == "<p>One</p><p>Two</p>"


def test_headings_map_to_h2_through_h4():
    stored = sanitize_description("<h1>A</h1><h3>B</h3><h6>C</h6>", CAP)
    assert stored == "<h2>A</h2><h3>B</h3><h4>C</h4>"


def test_nested_lists_stay_nested():
    stored = sanitize_description("<ul><li>Top<ul><li>Inner</li></ul></li><li>Next</li></ul>", CAP)
    assert stored == "<ul><li>Top<ul><li>Inner</li></ul></li><li>Next</li></ul>"
    [block] = description_blocks(stored)
    assert block["items"][0]["children"][0]["items"][0]["content"] == [{"type": "text", "text": "Inner"}]


def test_cap_cuts_at_a_whole_block():
    body = "".join(f"<p>Paragraph number {i} of the posting.</p>" for i in range(2000))
    stored = sanitize_description(body, 1_000)
    assert len(stored) <= 1_000 and stored.endswith("</p>")
    assert stored.count("<p>") == stored.count("</p>")


def test_one_giant_block_is_cut_as_escaped_text():
    stored = sanitize_description("<p>" + "a &amp; b " * 5_000 + "</p>", 1_000)
    assert len(stored) <= 1_000
    assert stored.startswith("<p>a &amp; b") and stored.endswith("</p>")


def test_pathologically_deep_markup_does_not_recurse_out():
    body = "<div>" * 5_000 + "deep text" + "</div>" * 5_000
    stored = sanitize_description(body, CAP)
    assert description_plain(stored) == "deep text"


def test_empty_descriptions_are_none():
    assert sanitize_description(None, CAP) is None
    assert sanitize_description("   ", CAP) is None
    assert sanitize_description("<p> </p><script>x</script>", CAP) is None


def test_hash_reads_raw_text_so_the_stored_format_cannot_change_it():
    body = _anduril_electrical_intern()
    stored = sanitize_description(body, CAP)
    raw_hash = make_content_hash("T", "D", "L", plain_text(body))
    # The runner hashes plain_text(raw); plain_text of the stored form differs in line
    # breaks only, which the hash ignores — so either input gives one hash.
    assert raw_hash == make_content_hash("T", "D", "L", plain_text(stored))


# ── legacy rows and the API shape ─────────────────────────────────────────────

def test_legacy_plain_text_is_never_parsed():
    legacy = "Intro line\n<script>alert(1)</script> is how XSS looks\n• Python\n• SQL\nClosing"
    assert not is_structured(legacy)
    blocks = description_blocks(legacy)
    assert blocks[0] == {"type": "paragraph", "content": [{"type": "text", "text": "Intro line"}]}
    assert blocks[1]["content"][0]["text"] == "<script>alert(1)</script> is how XSS looks"
    assert blocks[2] == {"type": "list", "ordered": False, "items": [
        {"content": [{"type": "text", "text": "Python"}], "children": []},
        {"content": [{"type": "text", "text": "SQL"}], "children": []},
    ]}
    assert blocks[3]["content"][0]["text"] == "Closing"
    assert description_plain(legacy) == legacy


def test_summary_is_short_plain_text():
    stored = sanitize_description(_anduril_electrical_intern(), CAP)
    summary = description_summary(stored)
    assert summary.startswith("Anduril Industries is a defense technology company")
    assert len(summary) <= 180 and summary.endswith("…") and "<" not in summary
    assert description_summary("Short.") == "Short."
    assert description_summary(None) is None
