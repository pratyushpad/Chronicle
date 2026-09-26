import hashlib
import re

from app.ml.text import DESCRIPTION_CHARS

_WS_RE = re.compile(r"\s+")

# Hash version prefix. Legacy hashes are 64 hex chars and can never start with "v", so
# the upsert can tell versions apart and ADOPT a new version without re-embedding.
HASH_VERSION = "v2"
# Description prefix covered by the hash, counted in NON-whitespace characters. The
# embedding only reads the first DESCRIPTION_CHARS of the description; covering 3x that
# means any edit that could move the vector re-embeds, while edits deep in the
# boilerplate (and every formatting-only change) don't.
HASH_DESC_CHARS = 4000
assert HASH_DESC_CHARS >= 3 * DESCRIPTION_CHARS


def make_dedup_key(company_id: int, dedup_title: str) -> str:
    """Location-independent identity for a role: same company + same canonical title
    collapses cross-posted city duplicates into one logical role. Pass the title
    through `normalize.dedup_title()` first to strip baked-in location suffixes."""
    raw = f"{company_id}|{dedup_title}"
    return hashlib.sha1(raw.encode()).hexdigest()


def make_content_hash(
    title: str | None,
    department_raw: str | None,
    location_raw: str | None,
    description_plain: str | None,
) -> str:
    """Version-2 content hash: covers only what the SOURCE says, so a job re-embeds when
    its posting changes and never because Chronicle changed.

    Inputs are the raw title, raw ATS department and raw location (whitespace-collapsed)
    plus the first HASH_DESC_CHARS non-whitespace characters of `plain_text(raw_html)`.
    Whitespace is removed from the description entirely, so re-flowing or restructuring
    the stored text (PR 2 stores sanitized HTML) can't change the hash.

    Derived fields are deliberately excluded: the normalized department, tech tags and
    normalized location come from Chronicle's own normalizers, and retuning a normalizer
    used to null the embedding of every affected row (dropping it from semantic search
    until Render re-embedded it). Embeddings therefore lag normalizer changes by design;
    those fields are a few tokens of a 256-token input.

    Returns "v2" + 62 hex chars (64 total — fits the existing column)."""
    desc_key = _WS_RE.sub("", description_plain or "")[:HASH_DESC_CHARS]
    parts = [
        _WS_RE.sub(" ", title or "").strip(),
        _WS_RE.sub(" ", department_raw or "").strip(),
        _WS_RE.sub(" ", location_raw or "").strip(),
        desc_key,
    ]
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return HASH_VERSION + digest[: 64 - len(HASH_VERSION)]
