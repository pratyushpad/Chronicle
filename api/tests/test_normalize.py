from datetime import datetime, timezone

from app.ingest.normalize import (
    infer_remote,
    normalize_department,
    normalize_location,
    normalize_title,
    parse_posted_at,
    strip_html,
)
from app.ingest.adapters.base import RawJob


def _raw(**kwargs):
    defaults = dict(
        source_job_id="1", title="", location=None, department=None,
        employment_type=None, description_html=None, apply_url="", posted_at=None, remote=None,
    )
    return RawJob(**{**defaults, **kwargs})


def test_normalize_title_strips_req_id():
    assert normalize_title("Software Engineer (Req #1234)") == "software engineer"


def test_normalize_title_strips_jr_id():
    assert normalize_title("Backend Engineer - JR12345") == "backend engineer"


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  Senior  Engineer  ") == "senior engineer"


def test_normalize_location_strips_remote_prefix():
    result = normalize_location("Remote - New York")
    assert "remote" not in result
    assert "new york" in result


def test_normalize_location_none():
    assert normalize_location(None) is None


def test_infer_remote_from_adapter_flag():
    job = _raw(remote=True)
    assert infer_remote(job) is True


def test_infer_remote_from_location():
    job = _raw(location="Remote - San Francisco", remote=None)
    assert infer_remote(job) is True


def test_infer_remote_false_for_city():
    job = _raw(location="San Francisco, CA", title="Engineer", remote=None)
    assert infer_remote(job) is None


def test_parse_posted_at_iso():
    dt = parse_posted_at("2025-01-15T10:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2025


def test_parse_posted_at_epoch_ms():
    dt = parse_posted_at("1705312800000")
    assert isinstance(dt, datetime)
    assert dt.year == 2024


def test_parse_posted_at_none():
    assert parse_posted_at(None) is None


def test_parse_posted_at_invalid():
    assert parse_posted_at("not-a-date") is None


def test_strip_html():
    result = strip_html("<p>Hello <strong>world</strong></p>")
    assert "<" not in result
    assert "Hello" in result
    assert "world" in result


def test_strip_html_none():
    assert strip_html(None) is None


# ── Department normalization (controlled vocabulary) ──────────────────────────

def test_department_strips_code_and_org_to_category():
    # The internal org tail ("Square Outside") must NOT leak — resolves to "Sales".
    assert normalize_department("20213 S&M - Sales - Square Outside") == "Sales"


def test_department_engineering_subteam():
    assert normalize_department("Engineering - Infrastructure") == "Engineering"


def test_department_region_is_not_the_department():
    assert normalize_department("Sales - EMEA") == "Sales"


def test_department_plain_category():
    assert normalize_department("Marketing") == "Marketing"


def test_department_unknown_collapses_to_other_not_org_name():
    result = normalize_department("Skunkworks - Zephyr Internal Team")
    assert result == "Other"
    assert "Zephyr" not in result and "Skunkworks" not in result


def test_department_security_beats_engineering():
    assert normalize_department("Security Engineering") == "Security"


def test_department_product_marketing_is_marketing():
    assert normalize_department("Product Marketing") == "Marketing"


def test_department_empty_is_none():
    assert normalize_department(None) is None
    assert normalize_department("") is None
    assert normalize_department("   ") is None
