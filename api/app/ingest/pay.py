"""Pay extraction: structured ATS pay first, then a text parser that never guesses.

Why this exists (live bugs, 2026-09-25): the old `_parse_salary_k` multiplied anything
under 1000 by 1000, so Anduril's "US Salary Range $30 — $45 USD" (hourly) was stored
as $30k–45k and Cresta's "$45-$70 per hour" as $45k–70k. The rules here:

* Structured beats text. Ashby `compensation.summaryComponents`, Lever `salaryRange`
  and Greenhouse `pay_input_ranges` all arrive on the list call we already make.
* A period is only ever assigned from evidence: an explicit cue ("per hour", "/yr",
  an ATS interval, a range title like "US Hourly Range"), or a magnitude that can mean
  only one thing — every amount in [10, 300] is hourly, anything ≥ 20,000 is yearly.
  Anything in between with no cue ($500, $8,000 …) is left unknown. Unknown pay stays
  NULL; it is never shown as a guess.
* Every period has sanity bounds (scaled roughly per currency). A cue that contradicts
  its own amounts ("Annual base salary $40–55", "Hourly" on $85,000) is dropped and
  the unambiguous-magnitude rule gets a chance instead.
* Base pay only: OTE / total compensation / equity / bonus / stipend-for-X figures are
  skipped, judged by the label nearest to the amount.

Amounts are Decimals in the posting's own currency and unit (stored as NUMERIC(12,2)).
`annualize` exists only to derive `jobs.salary_min/max` for sorting and old clients.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PERIODS = ("hour", "day", "week", "month", "year")
_ANNUAL_FACTOR = {"hour": 2080, "day": 260, "week": 52, "month": 12, "year": 1}
_CENT = Decimal("0.01")
_MAX_AMOUNT = Decimal("9999999999.99")  # NUMERIC(12,2)


@dataclass(frozen=True)
class Pay:
    min: Decimal
    max: Decimal
    currency: str  # ISO 4217
    period: str    # hour | day | week | month | year
    source: str    # "ats" (structured ATS field) | "text" (parsed from the description)


# Rough units-per-USD, used ONLY to scale the sanity bounds below — never to convert or
# display anything. `low_cost` relaxes the lower bounds for currencies whose local pay
# sits far below US levels (a fresher's INR salary is a few thousand USD a year).
_CURRENCIES: dict[str, tuple[float, bool]] = {
    "USD": (1.0, False), "CAD": (1.4, False), "AUD": (1.5, False), "NZD": (1.7, False),
    "SGD": (1.35, False), "HKD": (7.8, False), "GBP": (0.8, False), "EUR": (0.92, False),
    "CHF": (0.9, False), "SEK": (10.5, False), "NOK": (10.8, False), "DKK": (6.9, False),
    "ILS": (3.7, False), "AED": (3.67, False), "JPY": (150.0, False), "KRW": (1350.0, False),
    "PLN": (4.0, True), "CZK": (23.0, True), "HUF": (360.0, True), "RON": (4.6, True),
    "INR": (85.0, True), "CNY": (7.2, True), "TWD": (32.0, True), "PHP": (57.0, True),
    "BDT": (120.0, True), "MXN": (18.0, True), "BRL": (5.5, True), "ZAR": (18.0, True),
}
# Plausible base pay per period, in USD-equivalents.
_BOUNDS_USD = {
    "hour": (5, 500),
    "day": (40, 4_000),
    "week": (150, 20_000),
    "month": (500, 100_000),
    "year": (10_000, 2_000_000),
}


def _valid(lo: Decimal, hi: Decimal, currency: str, period: str) -> bool:
    info = _CURRENCIES.get(currency)
    if info is None:
        # Unknown currency: only reachable from a structured ATS field with an explicit
        # interval (the text parser only recognizes the table above). Trust the ATS.
        return lo > 0 and hi >= lo
    if period not in _BOUNDS_USD:
        return False  # e.g. "per pay period": explicit, but not a period we can show
    scale, low_cost = info
    b_lo, b_hi = _BOUNDS_USD[period]
    lower = Decimal(str(b_lo * scale * (0.25 if low_cost else 1.0)))
    upper = Decimal(str(b_hi * scale))
    return lower <= lo and hi <= upper


def _magnitude_period(lo: Decimal, hi: Decimal, currency: str) -> str | None:
    """The only two magnitudes that are unambiguous on their own (raw units)."""
    if currency not in _CURRENCIES:
        return None
    if Decimal(10) <= lo and hi <= Decimal(300):
        return "hour"
    if lo >= Decimal(20_000):
        return "year"
    return None


def _dec(value) -> Decimal | None:
    """A payload number (int / Decimal from ijson / float / numeric string) → cents."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not d.is_finite():
        return None
    return d.quantize(_CENT, rounding=ROUND_HALF_UP)


def _currency_code(value) -> str | None:
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else None


@dataclass
class _Cand:
    lo: Decimal
    hi: Decimal
    currency: str
    period: str
    strength: int   # 2 = explicit cue, 1 = weak cue / magnitude
    labeled: bool   # a pay label ("salary", "pay range", "hourly rate" …) sits right before it
    pos: int


def _resolve(lo, hi, currency, cue, weak_cue, pos, labeled=True, reinterpret=True) -> _Cand | None:
    """Validate amounts and assign a period from the strongest usable evidence.

    `reinterpret`: when an explicit cue contradicts its own amounts, may the magnitude
    rule take over? Yes for structured ATS fields — the amount is known to be pay and
    the interval/title is the typo ("Annual base salary $40–55", "per-hour-wage" on
    $60k). No for free text, where "$100/month" next to a benefit is simply not a wage
    and must not come back as "$100/hr"."""
    if lo is None or hi is None or currency is None:
        return None
    if lo <= 0 or hi <= 0 or hi > _MAX_AMOUNT or lo > _MAX_AMOUNT:
        return None
    if lo > hi:
        lo, hi = hi, lo
    if cue and _valid(lo, hi, currency, cue):
        return _Cand(lo, hi, currency, cue, 2, labeled, pos)
    if cue and not reinterpret:
        return None
    if weak_cue and _valid(lo, hi, currency, weak_cue):
        return _Cand(lo, hi, currency, weak_cue, 1, labeled, pos)
    mp = _magnitude_period(lo, hi, currency)
    if mp and _valid(lo, hi, currency, mp):
        return _Cand(lo, hi, currency, mp, 1, labeled, pos)
    return None


def _select(cands: list[_Cand], source: str) -> Pay | None:
    """Several bands can share a period + currency (per-location zones, per-degree or
    per-level tiers): report the overall min/max. Across groups prefer labelled, then
    explicitly-cued, then more numerous, then earliest."""
    if not cands:
        return None
    groups: dict[tuple[str, str], list[_Cand]] = {}
    for c in cands:
        groups.setdefault((c.period, c.currency), []).append(c)

    def rank(members: list[_Cand]):
        return (
            any(c.labeled for c in members),
            max(c.strength for c in members),
            len(members),
            -min(c.pos for c in members),
        )

    (period, currency), members = max(groups.items(), key=lambda kv: rank(kv[1]))
    return Pay(
        min=min(c.lo for c in members),
        max=max(c.hi for c in members),
        currency=currency,
        period=period,
        source=source,
    )


# ── Ashby ─────────────────────────────────────────────────────────────────────

_ASHBY_INTERVALS = {"1 HOUR": "hour", "1 DAY": "day", "1 WEEK": "week", "1 MONTH": "month", "1 YEAR": "year"}


def pay_from_ashby(compensation) -> Pay | None:
    """`compensation.summaryComponents[]` of type "Salary" (equity, bonus, commission
    components are not base pay). Same interval + currency combine by min/max."""
    if not isinstance(compensation, dict):
        return None
    comps = compensation.get("summaryComponents")
    if not isinstance(comps, list):
        return None
    cands = []
    for i, comp in enumerate(comps):
        if not isinstance(comp, dict) or comp.get("compensationType") != "Salary":
            continue
        period = _ASHBY_INTERVALS.get(str(comp.get("interval") or "").strip().upper())
        if period is None:
            continue
        cand = _resolve(
            _dec(comp.get("minValue")), _dec(comp.get("maxValue")),
            _currency_code(comp.get("currencyCode")), period, None, i,
        )
        if cand:
            cands.append(cand)
    return _select(cands, "ats")


# ── Lever ─────────────────────────────────────────────────────────────────────

_LEVER_INTERVAL_RE = re.compile(r"per-(hour|day|week|month|year)\b")


def pay_from_lever(salary_range) -> Pay | None:
    """`salaryRange {min, max, currency, interval: "per-hour-wage" | "per-year-salary" …}`
    — absent when the posting has none; "one-time" amounts are not a wage."""
    if not isinstance(salary_range, dict):
        return None
    m = _LEVER_INTERVAL_RE.match(str(salary_range.get("interval") or "").strip().lower())
    if not m:
        return None
    cand = _resolve(
        _dec(salary_range.get("min")), _dec(salary_range.get("max")),
        _currency_code(salary_range.get("currency")), m.group(1), None, 0,
    )
    return _select([cand] if cand else [], "ats")


# ── Greenhouse ────────────────────────────────────────────────────────────────

# Range titles that are not base pay (Toast "Total Targeted Cash", Rocket Lab "Total
# Compensation (base and equity)", "Annual OTE Salary", "Target Variable" …).
_GH_NOT_BASE_RE = re.compile(
    r"\bote\b|on[\s-]?target|variable|bonus|commission|equity|stock|\brsus?\b|incentive|"
    r"total\s+(?:target(?:ed)?\s+)?(?:cash|comp\w*|rewards)|sign[\s-]?on|signing",
    re.I,
)
# Range titles are short labels, so a bare period word is a cue ("US Hourly Range").
_TITLE_CUES = [
    (re.compile(r"hourly|per\s+hour|/\s*h(?:ou)?r\b|\bhour\b", re.I), "hour"),
    (re.compile(r"\bdaily\b|per\s+day|day\s+rate", re.I), "day"),
    (re.compile(r"weekly|per\s+week", re.I), "week"),
    (re.compile(r"monthly|per\s+month|\bmonth\b", re.I), "month"),
    (re.compile(r"annual|yearly|per\s+(?:year|annum)|\byear\b", re.I), "year"),
]
# Blurbs are paragraphs about benefits too ("Monthly stipend…", "annual bonus"), so only
# phrases that are about the pay itself count.
_BLURB_CUES = [
    (re.compile(r"hourly\s+(?:rate|pay|wage|range|base|salary)|(?:rate|pay|wage)\s+per\s+hour|\bper\s+hour\b", re.I), "hour"),
    (re.compile(r"daily\s+(?:rate|pay|wage)|(?:rate|pay)\s+per\s+day", re.I), "day"),
    (re.compile(r"weekly\s+(?:salary|pay|wage|rate)|(?:salary|pay)\s+per\s+week", re.I), "week"),
    (re.compile(r"monthly\s+(?:base\s+|gross\s+)?(?:salary|pay|wage|compensation|rate)|gross\s+monthly|(?:salary|pay)\s+per\s+month", re.I), "month"),
    (re.compile(r"(?:annual|yearly|annualized)\s+(?:base\s+)?(?:salary|pay|compensation|wage)|(?:salary|pay)\s+per\s+(?:year|annum)|per\s+annum", re.I), "year"),
]
# English only: Spanish "Salario bruto mensual" is a monthly figure, not a yearly cue.
_SALARY_WORD_RE = re.compile(r"\bsalar(?:y|ies)\b", re.I)


def _first_cue(text: str, cues) -> str | None:
    best = None
    for pattern, period in cues:
        m = pattern.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), period)
    return best[1] if best else None


def pay_from_greenhouse(pay_input_ranges, description_html: str | None = None) -> Pay | None:
    """Greenhouse `pay_input_ranges [{min_cents, max_cents, currency_type, title, blurb}]`
    (returned by the list endpoint with `&pay_transparency=true`) carry NO interval.

    Period per range: title cue, then blurb cue, then an explicit cue next to the same
    amounts in the description text, then a "salary" title (weak → year), then the
    unambiguous-magnitude rule. The description is only parsed when a range needs it.
    """
    if not isinstance(pay_input_ranges, list) or not pay_input_ranges:
        return None
    from .normalize import plain_text  # local: normalize → adapters.base → (no pay)

    text_cands: list[_TextCand] | None = None
    cands: list[_Cand] = []
    for i, rng in enumerate(pay_input_ranges):
        if not isinstance(rng, dict):
            continue
        title = str(rng.get("title") or "")
        if _GH_NOT_BASE_RE.search(title):
            continue
        lo, hi = _cents(rng.get("min_cents")), _cents(rng.get("max_cents"))
        currency = _currency_code(rng.get("currency_type"))
        if lo is None or hi is None or currency is None or lo <= 0 or hi <= 0:
            continue
        if lo > hi:
            lo, hi = hi, lo
        cue = _first_cue(title, _TITLE_CUES)
        if not (cue and _valid(lo, hi, currency, cue)):
            blurb = plain_text(rng.get("blurb")) if isinstance(rng.get("blurb"), str) else None
            cue = _first_cue(blurb, _BLURB_CUES) if blurb else None
        if not (cue and _valid(lo, hi, currency, cue)) and description_html:
            if text_cands is None:
                text_cands = _text_candidates(plain_text(description_html) or "")
            cue = next(
                (
                    t.cue for t in text_cands
                    if t.cue and t.currency == currency
                    and abs(t.lo - lo) < _CENT and abs(t.hi - hi) < _CENT
                ),
                None,
            )
        weak = "year" if _SALARY_WORD_RE.search(title) else None
        cand = _resolve(lo, hi, currency, cue, weak, i)
        if cand:
            cands.append(cand)
    return _select(cands, "ats")


def _cents(value) -> Decimal | None:
    d = _dec(value)
    return None if d is None else (d / 100).quantize(_CENT, rounding=ROUND_HALF_UP)


# ── Text parser ───────────────────────────────────────────────────────────────

_CODES = (
    r"USD|CAD|AUD|NZD|SGD|HKD|GBP|EUR|CHF|SEK|NOK|DKK|ILS|AED|JPY|KRW|PLN|CZK|HUF|RON|"
    r"INR|CNY|TWD|PHP|BDT|MXN|BRL|ZAR"
)
_SYMBOLS = {
    "US$": "USD", "CA$": "CAD", "C$": "CAD", "AU$": "AUD", "A$": "AUD", "NZ$": "NZD",
    "SG$": "SGD", "S$": "SGD", "HK$": "HKD", "MX$": "MXN", "R$": "BRL",
    "$": "USD", "£": "GBP", "€": "EUR", "₹": "INR",
}
_SYM = r"(?<![A-Za-z])(?:US|CA|AU|NZ|SG|HK|MX|C|A|S|R)\$|\$|£|€|₹"
# 150,000 · 1,234,567.89 · 45.000 / 1.234,56 (European) · 6,00,000 (Indian) · 38.47 · 45,50
_NUM = r"\d{1,3}(?:[,.]\d{3})+(?:[.,]\d{1,2})?|\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_K = r"(?P<k>[kK](?![A-Za-z]))?(?!\s?%)"
_MULT = r"(?P<mult>\+?\s?(?:million|billion|trillion|mln|bln|bn|mn|mm)\b|[mMbBtT](?![A-Za-z]))?"

# One amount WITH a currency marker: [CODE] [SYMBOL] number [k] [M/B] [CODE|€|£]
_TOKEN_RE = re.compile(
    rf"(?<![\w$£€₹.,])"
    rf"(?:(?:(?P<code>\b(?:{_CODES}))\s?(?P<sym1>{_SYM})?|(?P<sym2>{_SYM}))\s?(?P<num>{_NUM})(?![\d]){_K}{_MULT}"
    rf"(?:\s?(?:\(?(?P<post>(?:{_CODES}))\b\)?|(?P<postsym>[€£])))?"
    rf"|(?P<num2>{_NUM})(?![\d])(?P<k2>[kK](?![A-Za-z]))?\s?(?:\(?(?P<post2>(?:{_CODES}))\b\)?|(?P<postsym2>[€£])))",
    re.I,
)
# Gap between two amounts that makes them one range.
_SEP_RE = re.compile(r"\s*(?:[-–—‒―~]|to|through|thru|and)\s*", re.I)
# A range whose second amount carries no marker: "USD $30.00-40.00", "$120-150k".
_BARE_SECOND_RE = re.compile(
    rf"\s*(?:[-–—‒―~]|to|through|thru)\s*(?P<num>{_NUM})(?![\d])(?P<k>[kK](?![A-Za-z]))?"
    rf"(?:\s?\(?(?P<post>(?:{_CODES}))\b\)?)?(?![\d%])",
    re.I,
)
_BETWEEN_RE = re.compile(r"between\s*$", re.I)
# A range whose FIRST amount carries no marker: "30,000-120,000 USD/Year".
_BARE_FIRST_RE = re.compile(
    rf"(?<![\w$£€₹.,])(?P<num>{_NUM})(?![\d])(?P<k>[kK](?![A-Za-z]))?\s*(?:[-–—‒―~]|to)\s*$",
    re.I,
)

# Explicit period right after an amount: "/hr", "/ HR", "per hour", "an hour", "USD Hourly",
# "/per year", "annually", "a month", "p.a." …
_AFTER_CUE_RE = re.compile(
    r"^\s*\)?\s*(?:(?:net|gross)\s+)?(?:(?:/\s*per|/|per|an?|each)\s*(?P<unit>hour|hr|h|day|week|wk|month|mo|year|yr|annum|pay\s?period)\b"
    r"|(?P<adv>hourly|daily|weekly|monthly|annually|yearly|annual|p\.\s?a\.|p/h))",
    re.I,
)
_UNIT_PERIOD = {
    "hour": "hour", "hr": "hour", "h": "hour", "day": "day", "week": "week", "wk": "week",
    "month": "month", "mo": "month", "year": "year", "yr": "year", "annum": "year",
    "hourly": "hour", "daily": "day", "weekly": "week", "monthly": "month", "annually": "year",
    "yearly": "year", "annual": "year", "p.a.": "year", "p. a.": "year", "p/h": "hour",
    # "$20/pay period cell phone reimbursement": an explicit unit that is none of ours —
    # the amount is dropped rather than read as $20/hr by magnitude.
    "pay period": "pay_period", "payperiod": "pay_period",
}
# Explicit period somewhere in the lead-in: "The expected hourly range for this role is …"
_BEFORE_CUE_RE = re.compile(
    r"\b(?:hourly|per\s+hour|an\s+hour|daily|per\s+day|weekly|per\s+week|monthly|per\s+month|"
    r"annual(?:ly|ized)?|yearly|per\s+year|per\s+annum)\b",
    re.I,
)
# The label nearest an amount decides whether it is base pay. Exclusions: variable pay,
# equity, benefits budgets, company money (funding, revenue).
_LABEL_RE = re.compile(
    r"(?P<ex>(?:incentive|variable|bonus|commission|on[\s-]?target)\s+(?:pay|compensation|comp|earnings)|"
    r"total\s+(?:target(?:ed)?\s+)?(?:cash|comp\w*|rewards)(?:\s+(?:range|package|target))?|"
    r"quotas?|\bacv\b|deal\s+sizes?|book\s+of\s+business|"
    r"\bote\b|on[\s-]?target|variable|bonus(?:es)?|commissions?|equity|\bstock\b|\brsus?\b|"
    r"incentive|allowance|budget|reimburs\w*|"
    r"relocation|sign[\s-]?on|signing|401\s*\(?k\)?|\bmatch\b|credits?\b|raised|funding|valuation|"
    r"revenue|\barr\b|\bspend\b|saved|traded|invest\w*|donat\w*|\bgrants?\b|prizes?|awards?|"
    r"\bfees?\b|\bcosts?\b|\bprice|tuition|per\s+diem|discount|referral|learning|wellness|"
    r"transport\w*|commut\w*|\bphone\b|internet|home[\s-]office|equipment|\blunch|\bmeals?\b|"
    r"\bgym\b|fitness|childcare|housing|\btravel\b)"
    r"|(?P<inc>\bbase\b|salar(?:y|ies)|\bpay\b|\bwages?\b|\brates?\b|hourly|compensation|"
    r"\branges?\b|\bearn\w*|\bpaid\b)",
    re.I,
)
# What an amount is FOR, when that follows it: "$1.5K monthly stipend for meals",
# "$100/month education budget", "$5,000 signing bonus". Only the short noun phrase right
# after the amount (and any period cue) counts, up to the first separator — so the
# "Lunch" bullet after "$45-$70 per hour subject to taxes" never voids the wage, and
# neither does "+ housing stipend" after "$40/hr". A bare "stipend" is neutral: an
# intern's "$8,000 monthly stipend" is their pay.
_AFTER_PERIOD_PREFIX_RE = re.compile(
    r"^\s*\)?\s*(?:(?:net|gross)\s+)?(?:(?:/\s*per|/|per|an?|each)\s*(?:hour|hr|h|day|week|wk|month|mo|year|yr|annum)\b"
    r"|hourly|daily|weekly|monthly|annually|yearly|annual)",
    re.I,
)
_AFTER_PHRASE_STOP_RE = re.compile(r"[+,;.:()|/\n–—]")
_NOT_WAGE_NOUNS_RE = re.compile(
    r"\b(?:budgets?|allowances?|bonus(?:es)?|credits?|reimburse\w*|relocation|equity|stock|rsus?|"
    r"funding|raised|revenue|arr|valuation|signing|sign-on|referral|education|learning|wellness|"
    r"home|equipment|phone|internet|gym|fitness|commut\w*|transport\w*|meals?|lunch|food|"
    r"childcare|travel|housing|towards?|ote|quotas?)\b",
    re.I,
)
# An amount restated in another currency right after the first ("$75/£75", "$100 (£80)")
# is the same figure: it inherits the first one's label and exclusion.
_ALT_GAP_RE = re.compile(r"\s*(?:/|or|\(|\|)\s*", re.I)
_CLAUSE_BREAK_RE = re.compile(r"[.!?;](?=\s)|\n")


def _after_excluded(after: str) -> bool:
    """Is the word right after the amount (past any period cue) a not-a-wage noun?
    "stipend"/"for" look one or two words further ("stipend for meals"). Only the first
    word otherwise: "$140,000 Competitive Equity Package" is still a salary."""
    m = _AFTER_PERIOD_PREFIX_RE.match(after)
    rest = after[m.end():] if m else after
    phrase = _AFTER_PHRASE_STOP_RE.split(rest, maxsplit=1)[0]
    words = [w.lower() for w in phrase.split()]
    if words and words[0] == "in":
        words = words[1:]
    if not words:
        return False
    if words[0] in ("for", "stipend", "stipends"):
        return bool(_NOT_WAGE_NOUNS_RE.search(" ".join(words[1:3])))
    return bool(_NOT_WAGE_NOUNS_RE.fullmatch(words[0]))


@dataclass
class _TextCand:
    lo: Decimal
    hi: Decimal
    currency: str
    cue: str | None      # explicit period next to the amounts (not yet validated)
    weak: str | None     # "year" when the lead-in says "salary"
    labeled: bool
    excluded: bool
    start: int
    end: int


def _num(s: str) -> Decimal | None:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", s):  # 45.000 / 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", s):  # 45,50
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _token_parts(m: re.Match) -> tuple[Decimal | None, bool, str | None, bool]:
    """(value, has_k, currency, is_company_money) for one _TOKEN_RE match."""
    if m.group("num") is not None:
        value, k = _num(m.group("num")), bool(m.group("k"))
        code = m.group("code") or m.group("post")
        sym = m.group("sym1") or m.group("sym2") or m.group("postsym")
        mult = bool(m.group("mult"))
    else:
        value, k = _num(m.group("num2")), bool(m.group("k2"))
        code, sym, mult = m.group("post2"), m.group("postsym2"), False
    if code:
        currency = code.upper()
    elif sym:
        currency = _SYMBOLS.get(sym.upper() if sym[0].isalpha() else sym)
    else:
        currency = None
    return value, k, currency, mult


def _apply_k(value: Decimal | None, k: bool) -> Decimal | None:
    return None if value is None else (value * 1000 if k else value)


def _text_candidates(text: str) -> list[_TextCand]:
    """Every money amount/range in `text`, with its currency, nearby cues and whether its
    nearest label marks it as not-base-pay. Company money ($116M raised) is dropped."""
    if not text:
        return []
    tokens = list(_TOKEN_RE.finditer(text))
    out: list[_TextCand] = []
    prev_end = 0
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.start() < prev_end:  # swallowed by a bare-second range
            i += 1
            continue
        a_val, a_k, a_cur, a_mult = _token_parts(t)
        start, end = t.start(), t.end()
        b_val, b_k, b_cur, b_mult = None, False, None, False
        consumed = 1
        bare_first = None
        if t.group("num") is None:  # marker only AFTER the number: "30,000-120,000 USD"
            bare_first = _BARE_FIRST_RE.search(text, max(prev_end, start - 30), start)
        if bare_first:
            b_val, b_k, b_cur, b_mult = a_val, a_k, a_cur, a_mult
            a_val, a_k, a_cur = _num(bare_first.group("num")), bool(bare_first.group("k")), None
            start = bare_first.start()
        elif i + 1 < len(tokens):
            u = tokens[i + 1]
            gap = text[end:u.start()]
            sep = _SEP_RE.fullmatch(gap)
            if sep and (gap.strip().lower() != "and" or _BETWEEN_RE.search(text[max(0, start - 12):start])):
                b_val, b_k, b_cur, b_mult = _token_parts(u)
                end = u.end()
                consumed = 2
        if consumed == 1 and not a_mult and not bare_first:
            bare = _BARE_SECOND_RE.match(text, end)
            if bare:
                b_val, b_k = _num(bare.group("num")), bool(bare.group("k"))
                b_cur = bare.group("post").upper() if bare.group("post") else None
                end = bare.end()
        i += consumed
        if a_mult or b_mult:
            prev_end = end
            continue
        if b_val is not None:
            # "$120-150k": the k written once applies to both ends (and vice versa).
            if b_k and not a_k and a_val is not None and a_val < 1000:
                a_k = True
            if a_k and not b_k and b_val < 1000:
                b_k = True
        lo, hi = _apply_k(a_val, a_k), _apply_k(b_val, b_k) if b_val is not None else None
        if hi is None:
            hi = lo
        # A trailing ISO code beats the "$" default ("$160,000-$200,000 CAD").
        currency = b_cur if (b_cur and (b_cur != "USD" or a_cur is None)) else a_cur
        if currency is None or lo is None or hi is None:
            prev_end = end
            continue
        lo, hi = lo.quantize(_CENT, rounding=ROUND_HALF_UP), hi.quantize(_CENT, rounding=ROUND_HALF_UP)
        lead = text[max(prev_end, start - 70):start]
        # A heading on its own line ("Monthly Stipend" / "$8,000") still labels the amount
        # under it, so line breaks don't end the lead-in; sentence ends do. (The phrase
        # AFTER an amount does stop at a line break — see _after_excluded.)
        lead = _CLAUSE_BREAK_RE.split(lead.replace("\n", " "))[-1]
        after = text[end:end + 40]
        cue = None
        am = _AFTER_CUE_RE.match(after)
        if am:
            cue = _UNIT_PERIOD.get((am.group("unit") or am.group("adv") or "").lower())
        if cue is None:
            bm = list(_BEFORE_CUE_RE.finditer(lead))
            if bm:
                word = re.sub(r"\s+", " ", bm[-1].group(0).lower())
                cue = _BEFORE_WORD_PERIOD.get(word)
        labels = list(_LABEL_RE.finditer(lead))
        last = labels[-1] if labels else None
        cand = _TextCand(
            lo=min(lo, hi), hi=max(lo, hi), currency=currency, cue=cue,
            weak="year" if _SALARY_WORD_RE.search(lead) else None,
            labeled=bool(last and last.group("inc")),
            excluded=bool(last and last.group("ex")) or _after_excluded(after),
            start=start, end=end,
        )
        prev = out[-1] if out else None
        if prev is not None and _ALT_GAP_RE.fullmatch(text[prev.end:start]):
            cand.excluded = cand.excluded or prev.excluded
            cand.labeled = prev.labeled
            cand.cue = cand.cue or prev.cue
            cand.weak = cand.weak or prev.weak
        out.append(cand)
        prev_end = end
    return out


_BEFORE_WORD_PERIOD = {
    "hourly": "hour", "per hour": "hour", "an hour": "hour", "daily": "day", "per day": "day",
    "weekly": "week", "per week": "week", "monthly": "month", "per month": "month",
    "annual": "year", "annually": "year", "annualized": "year", "yearly": "year",
    "per year": "year", "per annum": "year",
}


def parse_pay_text(text: str | None) -> Pay | None:
    """Pay from free text (a posting's plain_text). Ranges and singles; `$ £ € ₹`, ISO
    codes and CA$/C$/A$…; K suffixes; `-`, en/em dash, "to", "between … and"."""
    if not text:
        return None
    cands = []
    for t in _text_candidates(text):
        if t.excluded:
            continue
        c = _resolve(t.lo, t.hi, t.currency, t.cue, t.weak, t.start, labeled=t.labeled, reinterpret=False)
        if c:
            cands.append(c)
    return _select(cands, "text")


def resolve_pay(structured: Pay | None, description_plain: str | None) -> Pay | None:
    """The one rule ingest (and the pay evaluation) uses: the ATS's own structured pay
    when it has one, else what the posting's plain text states, else nothing."""
    return structured or parse_pay_text(description_plain)


# ── Derived values ────────────────────────────────────────────────────────────

def annualize(pay: Pay) -> tuple[int, int]:
    """Yearly equivalents (hour×2080, day×260, week×52, month×12) — for sorting only."""
    f = _ANNUAL_FACTOR[pay.period]
    return (
        int((pay.min * f).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
        int((pay.max * f).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
    )


def annual_usd(pay: Pay | None) -> tuple[int | None, int | None]:
    """Values for the legacy `salary_min/max` columns: annualized USD only. Old clients
    render those as "$Xk", and a sort across currencies would be meaningless, so a GBP
    or INR band never lands there."""
    if pay is None or pay.currency != "USD":
        return None, None
    return annualize(pay)


_DISPLAY_SYMBOL = {
    "USD": "$", "GBP": "£", "EUR": "€", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$",
    "SGD": "S$", "HKD": "HK$", "INR": "₹", "MXN": "MX$", "BRL": "R$",
}
_PERIOD_SUFFIX = {"hour": "/hr", "day": "/day", "week": "/wk", "month": "/mo", "year": "/yr"}


def _fmt_amount(value: Decimal, in_thousands: bool) -> str:
    if in_thousands:
        text = f"{value / 1000:,.1f}"
        return text.rstrip("0").rstrip(".") + "k"
    if value == value.to_integral_value():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def format_pay(pay_min, pay_max, currency: str | None, period: str | None) -> str | None:
    """"$45 to 55/hr", "$205k to 300k/yr", "£30 to 35/hr", "$8,000/mo" (alert emails; the
    web has its own formatter). None when anything needed is missing."""
    if pay_min is None or not currency or period not in _PERIOD_SUFFIX:
        return None
    lo = Decimal(str(pay_min))
    hi = Decimal(str(pay_max)) if pay_max is not None else lo
    in_thousands = period == "year" and lo >= 1000
    symbol = _DISPLAY_SYMBOL.get(currency)
    prefix = symbol if symbol else f"{currency} "
    a, b = _fmt_amount(lo, in_thousands), _fmt_amount(hi, in_thousands)
    body = a if lo == hi else f"{a} to {b}"
    return f"{prefix}{body}{_PERIOD_SUFFIX[period]}"
