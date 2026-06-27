from app.ingest.dedupe import make_dedup_key


def test_dedup_key_is_deterministic():
    k1 = make_dedup_key(1, "software engineer", "san francisco, ca")
    k2 = make_dedup_key(1, "software engineer", "san francisco, ca")
    assert k1 == k2


def test_dedup_key_differs_by_company():
    k1 = make_dedup_key(1, "engineer", "remote")
    k2 = make_dedup_key(2, "engineer", "remote")
    assert k1 != k2


def test_dedup_key_differs_by_title():
    k1 = make_dedup_key(1, "backend engineer", "remote")
    k2 = make_dedup_key(1, "frontend engineer", "remote")
    assert k1 != k2


def test_dedup_key_none_location():
    k1 = make_dedup_key(1, "engineer", None)
    k2 = make_dedup_key(1, "engineer", None)
    assert k1 == k2


def test_dedup_key_length():
    k = make_dedup_key(1, "engineer", "remote")
    assert len(k) == 40  # sha1 hex digest
