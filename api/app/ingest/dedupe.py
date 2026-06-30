import hashlib


def make_dedup_key(company_id: int, dedup_title: str) -> str:
    """Location-independent identity for a role: same company + same canonical title
    collapses cross-posted city duplicates into one logical role. Pass the title
    through `normalize.dedup_title()` first to strip baked-in location suffixes."""
    raw = f"{company_id}|{dedup_title}"
    return hashlib.sha1(raw.encode()).hexdigest()
