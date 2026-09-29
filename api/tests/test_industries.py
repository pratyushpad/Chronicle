"""Canonical industries: every label in the registry folds into the ~20 shown names."""
import json

from app.industries import CANONICAL, canonical_industry, fold_counts, raw_labels
from tests.conftest import FIXTURES

SEED = FIXTURES.parent.parent / "companies.seed.json"


def test_every_registry_label_has_a_canonical_name():
    data = json.loads(SEED.read_text())
    companies = data if isinstance(data, list) else data["companies"]
    labels = {c["industry"] for c in companies if c.get("industry")}
    unmapped = sorted(label for label in labels if canonical_industry(label) is None)
    assert unmapped == []
    assert 18 <= len(CANONICAL) <= 22


def test_labels_fold_case_insensitively_and_names_map_to_themselves():
    assert canonical_industry("AI") == canonical_industry("ai/ml") == "AI & ML"
    assert canonical_industry("DevTools") == canonical_industry("Developer Tools") == "Developer Tools"
    assert canonical_industry("AI & ML") == "AI & ML"
    assert canonical_industry("  ") is None and canonical_industry(None) is None
    assert canonical_industry("Underwater Basket Weaving") is None


def test_raw_labels_and_fold_counts():
    assert raw_labels("ai & ml") == ["AI & ML", "AI", "AI/ML"]
    assert raw_labels("AI/ML") is None
    assert fold_counts([("AI", 5), ("AI/ML", 7), ("FinTech", 3), (None, 9), ("???", 1)]) == [
        ("AI & ML", 12), ("Fintech", 3)]
