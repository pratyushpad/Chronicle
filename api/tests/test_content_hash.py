"""make_content_hash underpins delta-only re-embedding: unchanged content → same hash →
keep the embedding; changed content → different hash → the upsert nulls the embedding so
only that row re-embeds. Tag order must not count as a change."""
from app.ingest.dedupe import make_content_hash


def test_stable_for_same_content_and_tag_order_insensitive():
    a = make_content_hash("Engineer", "build things", "SF", "Eng", ["go", "python"])
    b = make_content_hash("Engineer", "build things", "SF", "Eng", ["python", "go"])
    assert a == b


def test_changes_when_description_changes():
    a = make_content_hash("Engineer", "build things", "SF", "Eng", ["go"])
    b = make_content_hash("Engineer", "build other things", "SF", "Eng", ["go"])
    assert a != b


def test_changes_when_title_or_location_or_tags_change():
    base = make_content_hash("Engineer", "d", "SF", "Eng", ["go"])
    assert base != make_content_hash("Senior Engineer", "d", "SF", "Eng", ["go"])
    assert base != make_content_hash("Engineer", "d", "NYC", "Eng", ["go"])
    assert base != make_content_hash("Engineer", "d", "SF", "Eng", ["go", "rust"])


def test_handles_none_fields():
    h = make_content_hash(None, None, None, None, None)
    assert isinstance(h, str) and len(h) == 64
