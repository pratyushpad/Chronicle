"""make_content_hash (v2) underpins delta-only re-embedding: the posting's SOURCE content
unchanged → same hash → keep the embedding; source changed → different hash → the upsert
nulls the embedding so only that row re-embeds. Formatting-only changes and Chronicle's
own normalizer retunes must never change it."""
from app.ingest.dedupe import HASH_DESC_CHARS, HASH_VERSION, make_content_hash
from app.ml.text import DESCRIPTION_CHARS


def test_versioned_and_fits_the_column():
    h = make_content_hash("Engineer", "Eng", "SF", "build things")
    assert h.startswith(HASH_VERSION) and len(h) == 64
    # Legacy hashes were pure hex, so no legacy value can ever look like a v2 one.
    assert not any(c in "0123456789abcdef" for c in HASH_VERSION[0])


def test_stable_for_same_content():
    assert make_content_hash("Engineer", "Eng", "SF", "build things") == make_content_hash(
        "Engineer", "Eng", "SF", "build things"
    )


def test_formatting_only_changes_do_not_change_it():
    base = make_content_hash("Software Engineer", "Engineering", "San Francisco, CA",
                             "About us We build things. Requirements Python")
    # Re-flowed whitespace / line breaks (what PR 2's structured storage produces).
    assert base == make_content_hash("Software  Engineer ", " Engineering", "San Francisco,  CA",
                                     "About us\n\nWe build things.\n Requirements\n  Python")


def test_changes_when_source_fields_change():
    base = make_content_hash("Engineer", "Eng", "SF", "d")
    assert base != make_content_hash("Senior Engineer", "Eng", "SF", "d")
    assert base != make_content_hash("Engineer", "Platform", "SF", "d")
    assert base != make_content_hash("Engineer", "Eng", "NYC", "d")
    assert base != make_content_hash("Engineer", "Eng", "SF", "e")


def test_description_beyond_the_hashed_prefix_does_not_churn_it():
    head = "x" * HASH_DESC_CHARS
    assert make_content_hash("t", None, None, head + " tail A") == make_content_hash(
        "t", None, None, head + " tail B"
    )
    # …and the prefix comfortably covers everything the embedding can see.
    assert HASH_DESC_CHARS >= 3 * DESCRIPTION_CHARS


def test_handles_none_fields():
    h = make_content_hash(None, None, None, None)
    assert isinstance(h, str) and len(h) == 64
