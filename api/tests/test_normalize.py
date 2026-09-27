from datetime import datetime, timezone

import pytest

from app.ingest.normalize import (
    infer_experience_level,
    infer_remote,
    is_out_of_scope,
    normalize_department,
    normalize_location,
    normalize_title,
    parse_posted_at,
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


# ── Department normalization (controlled vocabulary) ──────────────────────────

def test_department_strips_code_and_org_to_category():
    # The internal org tail ("Square Outside") must NOT leak — resolves to "Sales".
    assert normalize_department("20213 S&M - Sales - Square Outside") == "Sales"


def test_department_engineering_subteam_uses_the_specific_category():
    # Infrastructure is its own category now; Engineering stays the general bucket.
    assert normalize_department("Engineering - Infrastructure") == "Infrastructure"
    assert normalize_department("Engineering - Backend") == "Engineering"


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


@pytest.mark.parametrize("title, expected", [
    ("Security Engineer", "Security"),
    ("Product Designer", "Design"),
    ("Product Manager", "Product"),
    ("Product Manager, AI Platform", "Product"),
    ("Data Scientist", "Data"),
    ("Machine Learning Engineer", "ML & AI"),
    ("Electrical Engineer Intern", "Hardware"),
    ("Firmware Engineer", "Hardware"),
    ("Mechanical Engineer, Autonomous Vehicles (Federal)", "Hardware"),
    ("Perception Engineer", "Robotics & Autonomy"),
    ("Staff Controls Engineer", "Robotics & Autonomy"),
    ("Site Reliability Engineer", "Infrastructure"),
    ("Software Development Engineer in Test", "Quality"),
    ("Manufacturing Engineer Intern", "Manufacturing"),
    ("Technical Recruiter", "People"),
    ("University Recruiter", "People"),
    ("Sales Engineer", "Sales"),
    ("Senior Engineering Manager, Rider Loyalty, Partnerships, and Rider Pay", "Engineering"),
    ("Technical Support Engineer", "Support"),
    ("Legal Counsel (Private Markets)", "Legal"),
    ("Crypto Controls and Compliance Lead", "Legal"),
    ("Accounting Intern", "Finance"),
    ("Software Engineer, Growth", "Engineering"),
    ("Mobile Phlebotomist (Norfolk, VA)", None),
    ("Family Medicine Physician - Ponce City Market", None),
])
def test_department_from_title_alone(title, expected):
    # No ATS department at all (Cresta sends departments: []): the title decides, and an
    # unmappable title stays None rather than inventing a facet.
    assert normalize_department(None, title) == expected


@pytest.mark.parametrize("raw, title, hints, expected", [
    # Waymo: "Pipeline (N/A)" + metadata "Job Group"
    ("Pipeline (N/A)", "2027 Summer Intern, BS/MS, Embedded, Software Engineer", ["Software Engineering"], "Engineering"),
    # Cresta: departments [] and null metadata
    (None, "Machine Learning Engineering Intern", [], "ML & AI"),
    # Lever Immuta / Hermeus: team + department both "Internships"
    ("Internships", "Full-Stack Engineering Internship - Summer 2027", ["Internships"], "Engineering"),
    ("Internships", "Platform & Site Reliability Engineering Internship - Summer 2027", ["Internships"], "Infrastructure"),
    ("Internships", "UX Designer Internship - Summer 2027", ["Internships"], "Design"),
    ("Internships", "Avionics Electrical Engineering Intern - Spring/Summer 2027", ["Internships"], "Hardware"),
    # Ashby Abridge: department "Builder", team as the hint
    ("Builder", "Software Engineering Intern, Fall", ["Product Engineering"], "Engineering"),
    ("Builder", "Machine Learning Scientist (All Levels)", ["Science"], "ML & AI"),
    # Ashby Sierra: "Early Career" / team "Intern"
    ("Early Career", "Software Engineer Intern, Agent (Summer 2027)", ["Intern"], "Engineering"),
    ("Early Career", "APX (New Grad 2027)", ["APX"], "Other"),
    # Anduril
    ("Hardware Platform : Hardware Engineering Services", "2027 Electrical Engineer Intern", ["Internships"], "Hardware"),
    ("Air Dominance & Strike", "2027 Flight Software Engineer Intern", ["Internships"], "Engineering"),
    ("Manufacturing : Manufacturing Engineering", "2027 Manufacturing Engineer Intern", ["Internships"], "Manufacturing"),
    # Recruiting orgs must not capture early-career departments…
    ("University Recruiting", "Software Engineer Intern", [], "Engineering"),
    ("6526 University Recruiting", "University Recruiter", [], "People"),
    ("Early Talent", "Data Analyst Intern (Summer 2027)", [], "Data"),
    ("Internships & Emerging Talent Positions", "Accounting Intern", [], "Finance"),
    ("5112 General University", "Software Engineering Intern", [], "Engineering"),
    ("2027 Internships", "Marketing Intern (Spring 2027)", [], "Marketing"),
    # …but real recruiting departments stay People
    ("Talent Acquisition", "Recruiting Coordinator", [], "People"),
    ("Technical Recruiting", "Coordinator, Emerging Talent Recruiting", [], "People"),
    ("People : Talent Acquisition : MFG Recruiting", "Recruiter", [], "People"),
    # Substring traps in the old rules
    ("Production Engineering", "Senior Engineer - Production Cloud and Container Services", [], "Engineering"),
    ("Commercial & Mid-Market Sales Engineering", "Commercial & Mid-Market Sales Engineer", [], "Sales"),
    ("Data Center Operations", "Data Center Technician", [], "Infrastructure"),
    ("Programs : Demand & Supply Planning : Demand & Supply Planning", "Demand & Supply Planner", [], "Operations"),
    ("56-Supply Chain", "Buyer", [], "Operations"),
    ("D41200-Sales Growth EMEA", "Account Executive", [], "Sales"),
    # Rocket Lab: multi-select metadata hint beats the unmappable business unit
    ("4015 USA Space Systems", "Avionics Automation Test Engineer II",
     ["Engineering - Electrical, Electronic Design & Test"], "Hardware"),
    # Vague departments let the title decide first
    ("Risk Solutions", "Senior AI Software Engineer, Risk - Insurance Claims Management", [], "Engineering"),
    ("Carta Law", "Lead Product Marketing Manager, Carta Law", [], "Marketing"),
    ("Tech", "Senior Platform Engineer", [], "Infrastructure"),
    # A team merely named "Platform" isn't infrastructure (live rows, Sept 2026)
    ("Platform - Elasticsearch", "Principal Software Engineer - Search Algorithms - Elasticsearch", [], "Engineering"),
    ("8813 Web Presence & Platform", "Full Stack Engineer, Web Presence and Platform", [], "Engineering"),
    ("Platform Engineering", "Software Engineer", [], "Infrastructure"),
    ("Platform Eng", "Software Engineer", [], "Infrastructure"),
    ("Technology : Infrastructure", "Senior DevOps Engineer", [], "Infrastructure"),
    # Unmappable but non-empty → "Other"; nothing at all → None
    ("Clinical", "Neurosurgeon Resident", [], "Other"),
    (None, "Neurosurgeon Resident", [], None),
])
def test_department_with_hints_and_title(raw, title, hints, expected):
    assert normalize_department(raw, title, hints) == expected


def test_department_vocabulary_is_closed():
    from app.ingest.normalize import DEPARTMENTS

    samples = [
        ("Engineering", None), ("Security", None), (None, "Data Scientist"),
        ("Clinical", "Nurse"), ("Growth", None), ("Business Operations", None),
    ]
    for raw, title in samples:
        assert normalize_department(raw, title) in set(DEPARTMENTS) | {"Other", None}


@pytest.mark.parametrize("raw, title, expected", [
    # Real intern rows that used to land in "Other" (replica, 2026-09-25)
    ("2244 Neutron - Propulsion", "Turbomachinery Intern Summer 2027", "Hardware"),
    ("4015 USA Space Systems", "Structural Analysis Intern Spring 2027", "Hardware"),
    ("Internships", "Intern, Cybersecurity", "Security"),
    ("Internships & Emerging Talent Positions", "Credit Risk Intern", "Finance"),
    ("Growth", "Growth Intern", "Marketing"),
    ("2027 Internships", "Computational Physics Intern (Spring 2027)", "Research"),
    ("Internships", "Intern, MES", "Manufacturing"),
    ("Internship", "Flight Software Internship - Spring 2027", "Engineering"),
    ("2027 Internships", "Global Supply Management Intern (Spring 2027)", "Operations"),
])
def test_department_real_intern_rows_that_were_other(raw, title, expected):
    assert normalize_department(raw, title) == expected


@pytest.mark.parametrize("title,out", [
    # Listing only (live titles, Sept 2026): senior, executive, and managers without an
    # early-career marker.
    ("Senior Data Scientist", True),
    ("Staff Engineer", True),
    ("Principal Software Engineer - Postgres", True),
    ("Senior Engineering Manager, Backend", True),
    ("Head of Engineering, Defense OS", True),
    ("Account Director - APAC", True),
    ("Revenue Operations Manager", True),
    ("Associate Director, Clinical Operations", True),
    ("Associate Creative Director", True),
    ("Director, Graduate Admissions", True),
    ("Senior Manager, Early Career Recruiting", True),
    ("Senior Associate", True),
    ("Solutions Architect", True),
    # Kept in full: early-career titles, including ones the level rules read as senior or
    # management (review of PR #9).
    ("Associate Product Manager", False),
    ("Junior Project Manager", False),
    ("Jr. Account Manager", False),
    ("Rotational Program Manager, Early Career", False),
    ("Graduate Program Manager", False),
    ("Product Manager, Early Careers", False),
    ("Technical Program Manager - Early Talent", False),
    ("Program Manager, Emerging Talent", False),
    ("Associate Partner Manager", False),
    ("Assistant Project Manager", False),
    ("Assistant Brand Manager", False),
    ("Associate Solutions Architect", False),
    ("Junior Solutions Architect", False),
    ("Associate Architect", False),
    ("Junior Staff Accountant", False),
    ("Staff Accountant", False),
    ("Staff Auditor", False),
    ("Lead Development Representative", False),
    ("Solutions Architect, New Graduate", False),
    ("Product Manager - New College Grad", False),
    ("Product Manager Intern", False),
    ("2027 Electrical Engineer Intern", False),
    ("New Grad Software Engineer", False),
    ("Software Engineer", False),
    ("Account Executive", False),
])
def test_out_of_scope_roles(title, out):
    assert is_out_of_scope(title, infer_experience_level(title)) is out


@pytest.mark.parametrize("title", [
    "Solutions Architect, New Graduate",
    "Product Manager - New College Grad",
    "University Graduate - Software Engineer",
    "Recent Graduates Program, Finance",
])
def test_graduate_variants_are_entry_level(title):
    assert infer_experience_level(title) == "Entry Level"
