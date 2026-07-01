from app.ingest.dedupe import make_dedup_key
from app.ingest.normalize import dedup_title, keying_title


def _key(company_id: int, title: str, location: str | None) -> str:
    """Mirror the runner's dedup path: keying_title preserves the team qualifier,
    dedup_title strips the location suffix."""
    return make_dedup_key(company_id, dedup_title(keying_title(title), location))


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


# ── Over-collapse guard: preserve the distinguishing team qualifier ────────────
# Confirmed prod bug: four distinct Databricks reqs sharing the base title
# "Staff Software Engineer" merged into one card because normalize_title stripped
# the "(Data Platform)" / "(Money)" parenthetical before keying.

def test_databricks_distinct_reqs_stay_separate():
    teams = [
        "Staff Software Engineer (Data Platform)",
        "Staff Software Engineer (Money)",
        "Staff Software Engineer (Compute)",
        "Staff Software Engineer (Growth)",
    ]
    keys = {_key(42, t, "san francisco, ca") for t in teams}
    assert len(keys) == 4  # four cards, not one


def test_same_qualified_role_cross_posted_still_collapses():
    # Same distinguished role posted to two cities → one key (SIMBA-style collapse
    # must survive the qualifier-preserving change).
    ny = _key(42, "Staff Software Engineer (Data Platform) - New York", "new york, ny")
    sf = _key(42, "Staff Software Engineer (Data Platform), San Francisco", "san francisco, ca")
    assert ny == sf


def test_numeric_req_id_parenthetical_still_stripped():
    # A number-shaped parenthetical is req-id noise, not a team qualifier — must still
    # collapse so the same role with different req ids stays one card.
    a = _key(42, "Staff Software Engineer (R-20481)", "austin, tx")
    b = _key(42, "Staff Software Engineer (R-73920)", "austin, tx")
    assert a == b


def test_keying_title_preserves_alpha_qualifier():
    assert keying_title("Staff Software Engineer (Data Platform)") == "staff software engineer (data platform)"
    assert keying_title("Staff Software Engineer (12345)") == "staff software engineer"
