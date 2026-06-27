import hashlib


def make_dedup_key(company_id: int, title_normalized: str, location_normalized: str | None) -> str:
    loc = location_normalized or ""
    raw = f"{company_id}|{title_normalized}|{loc}"
    return hashlib.sha1(raw.encode()).hexdigest()
