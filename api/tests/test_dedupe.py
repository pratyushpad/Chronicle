from app.ingest.dedupe import make_dedup_key
from app.ingest.normalize import dedup_title


def test_dedup_key_is_deterministic():
    k1 = make_dedup_key(1, "software engineer")
    k2 = make_dedup_key(1, "software engineer")
    assert k1 == k2


def test_dedup_key_differs_by_company():
    k1 = make_dedup_key(1, "engineer")
    k2 = make_dedup_key(2, "engineer")
    assert k1 != k2


def test_dedup_key_differs_by_title():
    k1 = make_dedup_key(1, "backend engineer")
    k2 = make_dedup_key(1, "frontend engineer")
    assert k1 != k2


def test_dedup_key_length():
    k = make_dedup_key(1, "engineer")
    assert len(k) == 40  # sha1 hex digest


# ── Cross-location collapse (the P0 fix) ──────────────────────────────────────

def test_cross_posted_cities_collapse_to_one_key():
    """Same role posted to many cities with the city baked into the title must
    collapse to a single dedup_key."""
    t = "manual quality assurance engineer, simba team - skopje"
    skopje = make_dedup_key(1, dedup_title(t, "skopje, north macedonia"))
    t2 = "manual quality assurance engineer, simba team - zagreb"
    zagreb = make_dedup_key(1, dedup_title(t2, "zagreb, croatia"))
    assert skopje == zagreb


def test_dedup_title_strips_matching_location_suffix():
    assert dedup_title("ml systems engineer - amsterdam", "amsterdam") == "ml systems engineer"
    assert dedup_title("ml systems engineer, london", "london, uk") == "ml systems engineer"


def test_dedup_title_does_not_overstrip_real_title_tail():
    # The location is San Francisco, so a ", backend" tail must survive.
    assert dedup_title("software engineer, backend", "san francisco, ca") == "software engineer, backend"


def test_different_titles_stay_distinct():
    k1 = make_dedup_key(1, dedup_title("backend engineer - berlin", "berlin"))
    k2 = make_dedup_key(1, dedup_title("frontend engineer - berlin", "berlin"))
    assert k1 != k2


def test_dedup_title_none_location_passthrough():
    assert dedup_title("staff engineer", None) == "staff engineer"
