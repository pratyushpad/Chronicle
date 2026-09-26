"""Student-filter extraction (PR 4) on real posting text from the labeled set
(tests/fixtures/extraction_eval), plus the gate that decides what reaches the UI."""
import gzip
import json

import pytest

from app.ingest.eligibility import country_code, extract_eligibility
from scripts.eval_extraction import MIN_PRECISION, MIN_SUPPORT, score
from tests.conftest import FIXTURES

ROWS = {json.loads(l)["id"]: json.loads(l) for l in gzip.open(FIXTURES / "extraction_eval" / "postings.jsonl.gz", "rt")}


def _extract(pid: str):
    r = ROWS[pid]
    h = r.get("ats_hints") or {}
    return extract_eligibility(r["title"], r["location"], r["text"],
                               {"workplace_type": h.get("workplaceType"), "is_remote": h.get("isRemote"),
                                "country": h.get("country")})


def test_eeo_citizenship_language_is_not_a_requirement():
    # Grow Therapy's EEO footer lists "citizenship" among protected classes.
    e = _extract(next(i for i in ROWS if i.startswith("ashby:grow-therapy:")))
    assert e.us_citizen_required is None and e.us_person_required is None


def test_itar_with_a_license_path_is_not_a_hard_us_person_rule():
    # Rocket Lab: "... U.S. citizen, lawful U.S. permanent resident ..., or be eligible to
    # obtain the required authorizations" — a license path exists, so unknown, not True.
    e = _extract("greenhouse:rocketlab:8000958003")
    assert e.us_citizen_required is None and e.us_person_required is None


def test_itar_where_the_company_may_decline_licensing_is_a_us_person_rule():
    # CoreWeave: license path offered, then "may ... decline to pursue any export licensing".
    e = _extract("greenhouse:coreweave:4692243006")
    assert e.us_person_required is True and e.us_citizen_required is None


def test_only_hire_us_persons():
    assert _extract("greenhouse:vardaspace:7824814003").us_person_required is True


def test_clearance_required_but_not_when_only_valued():
    assert _extract("lever:palantir:8bcf4f33-0a79-4248-bbfd-49ac4be9dd8e").clearance_required is True
    # Same line under a "What We Value" heading is a wish, not a requirement.
    assert _extract("lever:palantir:3ab9e715-1ea9-4c6c-ad50-7340eac14e86").clearance_required is None


def test_terms_from_titles_including_two_season_titles():
    e = _extract("lever:hermeus:d40446ee-40a9-4bb0-a3a8-a4a189b74630")  # "Spring/Summer 2027"
    assert (e.term_season, e.term_year) == ("spring", 2027)
    e = _extract("greenhouse:waymo:8214519")  # "2027 Summer Intern, MS/PhD, ..."
    assert (e.term_season, e.term_year) == ("summer", 2027)
    assert e.degree_levels == ["master", "phd"]


def test_graduation_dates_are_not_the_term():
    # "expected graduation date of Fall 2027 or Spring 2028" must not become the term.
    e = _extract(next(i for i in ROWS if i.startswith("ashby:grow-therapy:")))
    assert (e.term_season, e.term_year) == ("summer", 2027)


def test_five_office_days_is_onsite_not_hybrid():
    assert _extract("greenhouse:veeamsoftware:4955293101").workplace_type == "onsite"


def test_pay_table_degree_rows_are_not_degree_requirements():
    assert _extract("greenhouse:psiquantum:7695559003").degree_levels == ["master", "phd"]


@pytest.mark.parametrize("value, code", [
    ("Austin, TX", "US"), ("South San Francisco, California, USA", "US"), ("London", "GB"),
    ("Munich, Germany", "DE"), ("Brisbane, Queensland, Australia", "AU"), ("United States", "US"),
    ("CA", None), ("GB", "GB"), ("Remote", None), (None, None),
])
def test_country_codes(value, code):
    assert country_code(value) == code


def test_unknown_is_never_a_no():
    e = extract_eligibility("Software Engineer", None, "Build great things.", {})
    assert all(v is None for v in e.as_columns().values())


def test_shipped_fields_still_clear_the_held_out_gate():
    """The web shows term, degree levels and country (web/src/lib/eligibility.ts). A rule
    change that drops any of them below the bar must fail here, not silently in prod."""
    held = score("heldout")
    for field in ("term", "degree_levels", "country"):
        r = held[field]
        assert r["tp"] + r["fp"] >= MIN_SUPPORT, field
        assert r["precision"] >= MIN_PRECISION, (field, r["precision"])
