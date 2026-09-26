"""Pay extraction: structured ATS pay first, then a text parser that never guesses.

Every text case below is lifted from a real posting in the Sept 25 recorded payloads
(company noted). The two live bugs this replaces: Anduril "US Salary Range $30 — $45
USD" stored as $30k–45k, and Cresta "$45-$70 per hour" stored as $45k–70k.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.ingest.pay import (
    Pay,
    annual_usd,
    annualize,
    format_pay,
    parse_pay_text,
    pay_from_ashby,
    pay_from_greenhouse,
    pay_from_lever,
)

FIXTURES = Path(__file__).parent / "fixtures"
D = Decimal


def _fixture(name):
    return json.loads((FIXTURES / name).read_text())


def _gh(job_id):
    return next(j for j in _fixture("pr1_greenhouse.json")["jobs"] if j["id"] == job_id)


def _lever(job_id):
    return next(j for j in _fixture("pr1_lever.json") if j["id"] == job_id)


def _ashby(job_id):
    return next(j for j in _fixture("pr1_ashby.json")["jobs"] if j["id"] == job_id)


def _p(lo, hi, cur, period, source="text"):
    return Pay(D(str(lo)), D(str(hi)), cur, period, source)


# ── Ashby: compensation.summaryComponents ─────────────────────────────────────

def test_ashby_hourly_intern():
    job = _ashby("3f07a457-dc14-4238-bf4e-5c33b5c1f883")  # Abridge SWE intern, "$40 per hour"
    assert pay_from_ashby(job["compensation"]) == _p(40, 40, "USD", "hour", "ats")


def test_ashby_salary_ignores_equity_components():
    job = _ashby("097490e8-48c6-46e3-a0ce-882151fb4fa2")  # Abridge ML Scientist + EquityCashValue
    assert pay_from_ashby(job["compensation"]) == _p(205000, 300000, "USD", "year", "ats")


def test_ashby_no_components_is_no_pay():
    job = _ashby("34b31b67-268c-4270-b48f-72e59064c96e")  # Sierra intern, nothing disclosed
    assert pay_from_ashby(job["compensation"]) is None
    assert pay_from_ashby(None) is None


def test_ashby_same_interval_components_combine_by_min_max():
    comp = {"summaryComponents": [
        {"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "USD", "minValue": 150000, "maxValue": 180000},
        {"compensationType": "EquityPercentage", "interval": "NONE", "currencyCode": None, "minValue": None, "maxValue": None},
        {"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "USD", "minValue": 140000, "maxValue": 170000},
    ]}
    assert pay_from_ashby(comp) == _p(140000, 180000, "USD", "year", "ats")


def test_ashby_non_usd_currency_kept():
    comp = {"summaryComponents": [
        {"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "SGD", "minValue": 200000, "maxValue": 240000},
    ]}
    assert pay_from_ashby(comp) == _p(200000, 240000, "SGD", "year", "ats")


# ── Lever: salaryRange ────────────────────────────────────────────────────────

def test_lever_hourly_intern():
    job = _lever("b9b21075-74a4-4b64-8f1b-f0be1fb0b24d")  # Immuta intern 25–30/hr
    assert pay_from_lever(job["salaryRange"]) == _p(25, 30, "USD", "hour", "ats")


def test_lever_hermeus_intern_and_salaried():
    assert pay_from_lever(_lever("b7babdb5-64ee-49ad-a193-918d6a31c462")["salaryRange"]) == _p(25, 33, "USD", "hour", "ats")
    assert pay_from_lever(_lever("1602c0e0-10fe-4fc9-ac0f-22ce2a2c0d18")["salaryRange"]) == _p(159750, 225500, "USD", "year", "ats")


def test_lever_missing_or_unusable_ranges():
    assert pay_from_lever(None) is None
    assert pay_from_lever({"min": 500, "max": 500, "currency": "MXN", "interval": "one-time"}) is None
    # Lyra's MXN "0–450 per hour": a zero floor is a placeholder, not a wage.
    assert pay_from_lever({"min": 0, "max": 450, "currency": "MXN", "interval": "per-hour-wage"}) is None


def test_lever_interval_contradicted_by_magnitude_falls_back():
    # Real Sila shape: "per-hour-wage" on a $60k–100k band — no hourly wage is $60,000.
    sr = {"min": 60000, "max": 100000, "currency": "USD", "interval": "per-hour-wage"}
    assert pay_from_lever(sr) == _p(60000, 100000, "USD", "year", "ats")


# ── Greenhouse: pay_input_ranges (cents, no interval) ─────────────────────────

def test_greenhouse_anduril_intern_is_hourly_not_thousands():
    job = _gh(5148101007)  # "US Salary Range" 3000–4500 cents
    assert pay_from_greenhouse(job["pay_input_ranges"], job["content"]) == _p(30, 45, "USD", "hour", "ats")


def test_greenhouse_hourly_title_cue():
    job = _gh(5239083007)  # "US Hourly Range " 4200–6000
    assert pay_from_greenhouse(job["pay_input_ranges"]) == _p(42, 60, "USD", "hour", "ats")


def test_greenhouse_degree_tiers_combine():
    job = _gh(8221198)  # Waymo: Hourly Bachelors 60, Hourly Masters 70
    assert pay_from_greenhouse(job["pay_input_ranges"]) == _p(60, 70, "USD", "hour", "ats")


def test_greenhouse_total_comp_range_is_not_base_pay():
    job = _gh(7980750003)  # Rocket Lab: "Total Compensation (base and equity)" + "Base Salary"
    assert pay_from_greenhouse(job["pay_input_ranges"]) == _p(83200, 114400, "USD", "year", "ats")


def test_greenhouse_placeholder_amounts_are_dropped():
    # Real Anthropic placeholder: "Annual Salary:" $1–$2.
    ranges = [{"min_cents": 100, "max_cents": 200, "currency_type": "USD", "title": "Annual Salary:", "blurb": ""}]
    assert pay_from_greenhouse(ranges) is None


def test_greenhouse_monthly_cue_in_local_currency():
    ranges = [{"min_cents": 4350000, "max_cents": 4833300, "currency_type": "MXN",
               "title": "Mexico Monthly Pay Range", "blurb": ""}]
    assert pay_from_greenhouse(ranges) == _p(43500, 48333, "MXN", "month", "ats")


def test_greenhouse_contradicted_cue_falls_back_to_magnitude():
    # Real Verkada: "Estimated Hourly Pay Range" on $85,000–$145,000.
    ranges = [{"min_cents": 8500000, "max_cents": 14500000, "currency_type": "USD",
               "title": "Estimated Hourly Pay Range", "blurb": ""}]
    assert pay_from_greenhouse(ranges) == _p(85000, 145000, "USD", "year", "ats")


def test_greenhouse_ambiguous_amount_uses_description_cue():
    ranges = [{"min_cents": 800000, "max_cents": 900000, "currency_type": "USD", "title": "Pay Range", "blurb": ""}]
    html = "<p>Interns are paid $8,000 - $9,000 per month.</p>"
    assert pay_from_greenhouse(ranges, html) == _p(8000, 9000, "USD", "month", "ats")
    # Without any cue, $8,000 could be a month or a term stipend: never guess.
    assert pay_from_greenhouse(ranges, "<p>Great team.</p>") is None


def test_greenhouse_blurb_benefit_words_are_not_period_cues():
    # Real Smartsheet shape: blurb mentions a "Monthly stipend" benefit; the band is hourly.
    ranges = [{"min_cents": 2300, "max_cents": 2900, "currency_type": "USD", "title": "US Base Salary Pay Range",
               "blurb": "<p>Monthly stipend to support your work and productivity</p>"}]
    assert pay_from_greenhouse(ranges) == _p(23, 29, "USD", "hour", "ats")


def test_greenhouse_no_ranges():
    assert pay_from_greenhouse([]) is None
    assert pay_from_greenhouse(None) is None


# ── Text parser ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    # Anduril: em dash, "USD" suffix, no period anywhere → magnitude says hourly.
    ("US Salary Range $30—$45 USD", _p(30, 45, "USD", "hour")),
    ("US Salary Range $30 — $45 USD", _p(30, 45, "USD", "hour")),
    # Cresta
    ("Perks & Benefits: $45-$70 per hour subject to taxes", _p(45, 70, "USD", "hour")),
    # Crusoe
    ("Compensation will be paid in the range of $29.00 - $33.00 / HR + Bonus.", _p(29, 33, "USD", "hour")),
    # Lucid: code before symbol, bare second amount, "/ Hour"
    ("USD $30.00-40.00 / Hour Compensation & Benefits", _p(30, 40, "USD", "hour")),
    # Rocket Lab: cue after the currency code
    ("Pay Range CA: $28.00 USD Hourly You may be eligible", _p(28, 28, "USD", "hour")),
    # Everlaw: cue before the amount
    ("The expected hourly range for this role is $38.47 - $48.56, actual salary", _p(D("38.47"), D("48.56"), "USD", "hour")),
    # Sweetgreen
    ("Starting salary range based on experience $65,000 — $75,000 USD Sweetgreen", _p(65000, 75000, "USD", "year")),
    # Life360: "to"
    ("The US-based salary range for this position is $137,000 to $252,000. We take", _p(137000, 252000, "USD", "year")),
    # Braze: "between … and", "/year"
    ("expected to be between $208,000 and $349,655/year with an expected", _p(208000, 349655, "USD", "year")),
    # Wayve: space after the symbol
    ("ranges from $ 407,330 to $ 460,020 plus a competitive equity package", _p(407330, 460020, "USD", "year")),
    # Justworks: decimals on annual amounts
    ("targeted at $144,615.00 - $159,077.00 in the state of California", _p(144615, 159077, "USD", "year")),
    # Via: trailing ISO code overrides "$"
    ("Salary Range: $160,000-$200,000 CAD Comprehensive health", _p(160000, 200000, "CAD", "year")),
    # Asana (after plain_text rejoins the <span>)
    ("between $207,000 – $261,000. The actual base salary", _p(207000, 261000, "USD", "year")),
    # Dragos: a single annual figure
    ("Compensation : Salary: $140,000 Competitive Equity Package", _p(140000, 140000, "USD", "year")),
])
def test_text_real_postings(text, expected):
    assert parse_pay_text(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Base pay: $120K - $150K", _p(120000, 150000, "USD", "year")),
    ("Base pay: $120-150k", _p(120000, 150000, "USD", "year")),
    ("Salary £30k-£35k plus benefits", _p(30000, 35000, "GBP", "year")),
    ("Salary: $212.5k", _p(212500, 212500, "USD", "year")),
    ("SGD 200K – SGD 240K • Offers Equity", _p(200000, 240000, "SGD", "year")),
    ("£30 to £35 per hour", _p(30, 35, "GBP", "hour")),
    ("€45.000 - €55.000 per year", _p(45000, 55000, "EUR", "year")),
    ("CA$85,000–CA$95,000 annually", _p(85000, 95000, "CAD", "year")),
    ("A$120,000 base", _p(120000, 120000, "AUD", "year")),
    ("CAD 90,000 - 110,000", _p(90000, 110000, "CAD", "year")),
    ("₹6,00,000 - ₹8,00,000 per annum", _p(600000, 800000, "INR", "year")),
    ("Interns earn $8,000/mo", _p(8000, 8000, "USD", "month")),
    ("a stipend of $8,000 per month", _p(8000, 8000, "USD", "month")),
    ("$1,200 per week", _p(1200, 1200, "USD", "week")),
    ("$400 per day", _p(400, 400, "USD", "day")),
])
def test_text_formats(text, expected):
    assert parse_pay_text(text) == expected


@pytest.mark.parametrize("text", [
    None,
    "",
    "No compensation information here.",
    "$500 - $900",                      # 300 < x < 20,000 with no cue: month? stipend? never guess
    "A one-time $5,000 payment",
    "$250 - $400",                      # straddles the hourly window
    "We've raised $116M from some of the world's best investors",
    "Valued at $1.9B and backed by industry-leading investors",
    "over $1.57 Billion in ARR",
    "a market expected to reach $28.5 billion by 2028",
    "401(k) with a 4% match",
    "Compensation OTE $336,000 - $420,000k + Offers Equity",            # Decagon: OTE is not base
    "Total Targeted Cash $115,000 — $185,000 USD How Toast Uses AI",     # Toast
    "Personal learning and development budget of USD 2,000 per year",   # Canonical
    "Housing stipend of $2,000 per month for relocating interns",
    "Apoyo de transporte de $1000 MXN",                                  # Platacard
    "Annual Salary: $1 — $2 USD",                                        # Anthropic placeholder
    # Found by running the parser over all 48k recorded postings:
    "Perks: A weekly lunch stipend of $75/£75 or equivalent in your local currency for lunch.",  # Cohere
    "Get what you need to be happy and productive! $100/month education budget with more",      # Ashby
    "backed by Andreessen Horowitz, NEA, and Addition with $250+ million raised to date.",      # Anyscale
    "Work on real, high-impact projects. $1.5K monthly stipend for meals Free Equinox membership",  # Mercor
    "ofrecemos: Salario bruto mensual entre $10,300 Salario mensual bruto dado de alta",        # Lyra (MXN, Spanish)
    "Technology stipend – Equivalent to US$100 net per month to help support your work.",       # Docker
    "SaaS or infrastructure technology company in Series D/E/F stages with over $200mln in ARR",  # Teleport
    "Salary: $10% commission on all jobs! What You'll Do",                                      # Sila
    "Experience owning an annual quota of at least $500K, with the discipline to hit it",      # quota, not pay
    "Compensation: $100,000 OTE About Us We live and breathe",                                  # OTE after the amount
    "on target earnings (including base salary and on target incentive pay) for this role is "
    "$216,000 - $276,000 per year. By clicking",
    "The estimated total compensation range for this position is $152,000 - $195,000 (base plus bonus).",
])
def test_text_no_pay(text):
    assert parse_pay_text(text) is None


def test_text_unmarked_first_amount_takes_the_second_amounts_currency():
    text = "The Netherlands Based Salary range for this role is: 30,000-120,000 USD/Year + Bonus"
    assert parse_pay_text(text) == _p(30000, 120000, "USD", "year")


def test_text_parenthesised_codes_split_currencies():
    text = ("competitive salary range for this role - which is $170,000-$185,000 (USD) or "
            "$165,000-$180,000 (CAD) base salary")
    assert parse_pay_text(text) == _p(170000, 185000, "USD", "year")


def test_text_benefit_after_a_separator_does_not_void_the_wage():
    assert parse_pay_text("$45-$70 per hour subject to taxes Lunch provided daily") == _p(45, 70, "USD", "hour")
    assert parse_pay_text("$40/hr + housing stipend") == _p(40, 40, "USD", "hour")


def test_text_explicit_cue_that_fails_its_bounds_is_not_reinterpreted():
    # "$100/month" is a monthly amount that is too small to be a wage — it must not be
    # re-read as $100/hr by the magnitude rule.
    assert parse_pay_text("Remote setup: $100/month") is None
    assert parse_pay_text("A $200 per week commuter benefit") is None


def test_text_total_comp_is_skipped_but_base_salary_kept():
    # Rocket Lab's pay block as plain text.
    text = ("Total Compensation (base and equity) $135,475 — $194,075 USD "
            "Base Salary $115,000 — $158,400 USD")
    assert parse_pay_text(text) == _p(115000, 158400, "USD", "year")


def test_text_exclusion_only_applies_to_the_nearest_label():
    # Zscaler: "equity" earlier in the sentence, but the band is labelled "Base Pay Range".
    text = ("base salary + commission/ bonus/ equity (if applicable) + benefits. "
            "Base Pay Range $175,875 — $251,250 USD At Zscaler")
    assert parse_pay_text(text) == _p(175875, 251250, "USD", "year")


def test_text_location_tiers_take_the_overall_band():
    text = ("Zone 1 Pay Range $182,000 — $250,208 USD Zone 2 Pay Range $163,800 — $225,187 USD "
            "Zone 3 Pay Range $154,700 — $212,677 USD")
    assert parse_pay_text(text) == _p(154700, 250208, "USD", "year")


def test_text_level_tiers_with_per_year_cue():
    text = "Engineer I: $105,000 -$139,466/per year Engineer II: $119,543-$152,749/per year"
    assert parse_pay_text(text) == _p(105000, 152749, "USD", "year")


def test_text_hourly_by_location():
    # Gopuff: several cities, one hourly band each.
    text = ("based on a cost of labor index for that geographic area. Encino, CA: $23- $31.65 "
            "The salary range above reflects … Turlock, CA: USD $17.65 The salary range above")
    assert parse_pay_text(text) == _p(D("17.65"), D("31.65"), "USD", "hour")


# ── annualize / annual_usd / format_pay ───────────────────────────────────────

def test_annualize_each_period():
    assert annualize(_p(30, 45, "USD", "hour")) == (62400, 93600)
    assert annualize(_p(400, 400, "USD", "day")) == (104000, 104000)
    assert annualize(_p(1200, 1500, "USD", "week")) == (62400, 78000)
    assert annualize(_p(8000, 9000, "USD", "month")) == (96000, 108000)
    assert annualize(_p(150000, 190000, "USD", "year")) == (150000, 190000)
    assert annualize(_p(D("38.47"), D("48.56"), "USD", "hour")) == (80018, 101005)


def test_annual_usd_only_for_dollars():
    # salary_min/max keep their "$ per year" meaning for old clients, so a GBP or INR
    # band never lands there (the old web renders them as "$Xk").
    assert annual_usd(_p(30, 45, "USD", "hour")) == (62400, 93600)
    assert annual_usd(_p(30000, 35000, "GBP", "year")) == (None, None)
    assert annual_usd(None) == (None, None)


@pytest.mark.parametrize("args, expected", [
    ((45, 55, "USD", "hour"), "$45 to 55/hr"),
    ((205000, 300000, "USD", "year"), "$205k to 300k/yr"),
    ((30, 35, "GBP", "hour"), "£30 to 35/hr"),
    ((8000, 8000, "USD", "month"), "$8,000/mo"),
    ((D("24.04"), D("24.04"), "USD", "hour"), "$24.04/hr"),
    ((D("17.65"), D("31.65"), "USD", "hour"), "$17.65 to 31.65/hr"),
    ((212500, 212500, "USD", "year"), "$212.5k/yr"),
    ((43500, 48333, "MXN", "month"), "MX$43,500 to 48,333/mo"),
    ((95, 345, "PLN", "hour"), "PLN 95 to 345/hr"),
    ((1200, 1500, "EUR", "week"), "€1,200 to 1,500/wk"),
    ((400, 400, "USD", "day"), "$400/day"),
    ((None, None, "USD", "hour"), None),
    ((45, 55, None, "hour"), None),
    ((45, 55, "USD", None), None),
])
def test_format_pay(args, expected):
    assert format_pay(*args) == expected


def test_per_pay_period_amount_is_not_read_as_an_hourly_wage():
    # Varda Space: the wage line, then benefits that include "$20/pay period cell phone
    # reimbursement". The benefit must not become part of the pay band.
    from app.ingest.pay import parse_pay_text

    text = ("Compensation\nHourly Rate: $33.00\nHousing stipend for interns relocating to the area\n"
            "Benefits\nFinancial $20/pay period cell phone reimbursement.")
    pay = parse_pay_text(text)
    assert (float(pay.min), float(pay.max), pay.currency, pay.period) == (33.0, 33.0, "USD", "hour")


import pytest as _pytest


@_pytest.mark.parametrize("text, expected", [
    # Real rows the first backfill wrongly cleared (replica, 2026-09-26).
    ("Annual base salary range (excluding equity and bonus): $218,025 — $256,500 USD Application Limit",
     (218025.0, 256500.0, "USD", "year")),
    ("COMPENSATION Base Salary: $140,000 to $250,000 Equity + Benefits including Health",
     (140000.0, 250000.0, "USD", "year")),
    ("For Bay Area based hires: Estimated annual salary of $194,000-266,000 Equity This role is eligible",
     (194000.0, 266000.0, "USD", "year")),
    ("Allowance In-Office Lunch (5 days per week) Compensation and benefits $128K -$168K Suno is proud",
     (128000.0, 168000.0, "USD", "year")),
    ("The salary range for this role is $158,000-$223,000K, plus a competitive equity grant",
     (158000.0, 223000.0, "USD", "year")),
])
def test_salaries_the_legacy_text_backfill_must_keep(text, expected):
    from app.ingest.pay import parse_pay_text

    pay = parse_pay_text(text)
    assert pay is not None
    assert (float(pay.min), float(pay.max), pay.currency, pay.period) == expected
