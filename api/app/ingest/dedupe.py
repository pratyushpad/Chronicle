import hashlib


def make_dedup_key(company_id: int, dedup_title: str) -> str:
    """Location-independent identity for a role: same company + same canonical title
    collapses cross-posted city duplicates into one logical role. Pass the title
    through `normalize.dedup_title()` first to strip baked-in location suffixes."""
    raw = f"{company_id}|{dedup_title}"
    return hashlib.sha1(raw.encode()).hexdigest()


def make_content_hash(
    title: str | None,
    description_text: str | None,
    location_normalized: str | None,
    department: str | None,
    tech_tags: list[str] | None,
) -> str:
    """Stable hash of the fields that feed a job's embedding. Incremental ingest stores
    this per row so it can re-embed ONLY content-changed roles (by nulling the embedding
    when the hash differs) instead of re-embedding the whole corpus every run."""
    parts = [
        title or "",
        description_text or "",
        location_normalized or "",
        department or "",
        ",".join(sorted(tech_tags or [])),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
