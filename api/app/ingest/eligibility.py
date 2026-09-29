"""Student filters (PR 4): what a posting says about term, degree, graduation window,
citizenship, export control (U.S. person), security clearance, workplace and country.

Rules only, read from the posting's full plain text at ingest (plus the ATS's own
workplace/country fields where it has them). Every field is None unless the posting
states it: an unknown is never a "no". Precision per field is measured on a labeled set
of real postings (docs/extraction_eval.md); only fields that clear the bar reach the UI.

The traps these rules are built around (all seen in real postings):
- EEO footers list "citizenship" among protected classes. That is the opposite of a
  requirement, so any sentence that reads like an EEO statement is ignored.
- ITAR/EAR wording ("must be a U.S. citizen, lawful permanent resident, or protected
  individual") requires U.S.-person status, NOT citizenship. Citizenship is required
  only when no non-citizen alternative is offered.
- "Graduating in Spring 2028" names a season and year that are not the internship term.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

SEASONS = ("summer", "fall", "spring", "winter")


@dataclass
class Eligibility:
    term_season: str | None = None
    term_year: int | None = None
    degree_levels: list[str] | None = None
    grad_year_min: int | None = None
    grad_year_max: int | None = None
    us_citizen_required: bool | None = None
    us_person_required: bool | None = None
    clearance_required: bool | None = None
    workplace_type: str | None = None
    country: str | None = None

    def as_columns(self) -> dict:
        return asdict(self)


# ── sentences ─────────────────────────────────────────────────────────────────

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z(\"'“])|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s and s.strip()]


# Short heading lines that switch a section to "preferences" or back to "requirements".
_SOFT_HEADING_RE = re.compile(
    r"\b(?:value|prefer|nice[- ]to[- ]have|bonus|plus|desired|ideal|stand out|extra credit)", re.I)
_HARD_HEADING_RE = re.compile(
    r"\b(?:require|qualification|must|need|you(?:['’]ll)? bring|about you|who you are|looking for|"
    r"responsibilit|what you(?:['’]ll)? do|eligib)", re.I)


def _sections(text: str) -> list[tuple[str, bool]]:
    """(sentence, in_a_preferences_section) pairs. A posting's "What We Value" or
    "Preferred qualifications" list states wishes, not requirements."""
    out: list[tuple[str, bool]] = []
    soft = False
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= 60 and not line.endswith((".", "!", "?")):
            if _SOFT_HEADING_RE.search(line):
                soft = True
            elif _HARD_HEADING_RE.search(line):
                soft = False
        out += [(s, soft) for s in _sentences(line)]
    return out


_EEO_RE = re.compile(
    r"regardless of|without regard|protected (?:class|characteristic|veteran|status)|"
    r"equal (?:employment )?opportunit|discriminat|national origin|sexual orientation|"
    r"gender identity|marital status|legally protected",
    re.I,
)

# ── citizenship / U.S. person / clearance ────────────────────────────────────

_US = r"(?:U\.?\s?S\.?(?:A\.?)?|United States|American)"
_CITIZEN_RE = re.compile(rf"\b{_US}\s+citizen(?:s|ship)?\b|\bcitizen(?:s|ship)? of the United States\b", re.I)
_REQUIRE_RE = re.compile(
    r"\b(?:must|required?|requires|requirement|mandatory|only (?:open|available|consider|hire|employ)|"
    r"need(?:s|ed)? to|eligib(?:le|ility)|necessary|exclusively|restricted to)\b",
    re.I,
)
# A non-citizen path in the same sentence makes it a U.S.-person rule, not citizenship.
_NON_CITIZEN_ALT_RE = re.compile(
    r"permanent resident|green[- ]card|protected individual|refugee|asylee|U\.?\s?S\.?\s+person|"
    r"national(?:s)?\b(?! origin)|lawfully admitted",
    re.I,
)
_NOT_REQUIRED_RE = re.compile(
    r"\b(?:not|no|isn['’]t|is not|doesn['’]t|does not)\b[^.]{0,40}\b(?:required|requirement|necessary|need)\b",
    re.I,
)
_SPONSOR_OK_RE = re.compile(r"\b(?:will|can|do|does|able to|happy to)\s+(?:provide\s+)?sponsor", re.I)

_US_PERSON_RE = re.compile(
    rf"\b{_US}\s+persons?\b|\bITAR\b|International Traffic in Arms|\bexport[- ]control(?:led)?\b|"
    r"Export Administration Regulations|\bEAR\b",
    re.I,
)

_CLEARANCE_RE = re.compile(
    r"\b(?:security|secret|top[- ]secret|TS/SCI|DoD|government|federal|public trust)\s+clearance\b|"
    r"\bclearance\b(?=[^.]{0,40}\b(?:secret|TS|SCI|DoD|security)\b)|\bTS/SCI\b|"
    r"\b(?:obtain|maintain|hold|possess|active|current)\b[^.]{0,30}\bclearance\b",
    re.I,
)
_CLEARANCE_SOFT_RE = re.compile(
    r"\b(?:prefer(?:red|ably)?|a plus|nice to have|bonus|desir(?:ed|able)|advantage|"
    r"may be required|might be required|depending on|could be required|helpful)\b",
    re.I,
)
_CLEARANCE_HARD_RE = re.compile(
    r"\b(?:must|required?|requires|requirement|ability to (?:obtain|maintain)|able to (?:obtain|maintain)|"
    r"eligib(?:le|ility) (?:to|for)|willing(?:ness)? to obtain|active|obtain and maintain)\b",
    re.I,
)


# Export-control wording that also accepts a license/authorization path is a restriction
# only when the company says it may not pursue one.
# Must be offered as an alternative ("…, or be eligible to obtain the required
# authorizations"); "U.S. persons who may access it without an export license" is not one.
_LICENSE_ALT_RE = re.compile(
    r"\bor\b[^.]{0,80}\b(?:eligib\w*|obtain\w*|likely to obtain)\b[^.]{0,80}\b(?:authori[sz]ation|licens\w*)", re.I)
_LICENSE_DECLINE_RE = re.compile(
    r"decline to (?:pursue|seek|sponsor)|(?:will|may|does|do|can) not (?:pursue|seek|sponsor|apply for)[^.]{0,60}licens|"
    r"not (?:able|willing) to (?:pursue|seek|sponsor)[^.]{0,60}licens", re.I)


def _citizenship(sections: list[tuple[str, bool]]) -> tuple[bool | None, bool | None, bool | None]:
    citizen: bool | None = None
    person: bool | None = None
    export_person = False
    license_alt = license_decline = False
    clearance: bool | None = None
    for s, soft in sections:
        if _LICENSE_ALT_RE.search(s):
            license_alt = True
        if _LICENSE_DECLINE_RE.search(s):
            license_decline = True
        if _EEO_RE.search(s):
            continue
        if _CITIZEN_RE.search(s):
            if _NOT_REQUIRED_RE.search(s) and not _NON_CITIZEN_ALT_RE.search(s):
                citizen = False if citizen is None else citizen
            elif _REQUIRE_RE.search(s) or re.search(r"\bcitizens? only\b", s, re.I):
                if _NON_CITIZEN_ALT_RE.search(s):
                    export_person = True
                else:
                    citizen = True
        if _US_PERSON_RE.search(s) and (_REQUIRE_RE.search(s) or re.search(r"\baccess to\b", s, re.I)):
            if not (_NOT_REQUIRED_RE.search(s) and not _REQUIRE_RE.search(s)):
                export_person = True
        if _CLEARANCE_RE.search(s):
            if re.search(r"\bno (?:security )?clearance\b|\bclearance (?:is )?not required\b", s, re.I):
                clearance = False if clearance is None else clearance
            elif _CLEARANCE_HARD_RE.search(s) and not _CLEARANCE_SOFT_RE.search(s) and not soft:
                clearance = True
    if export_person and not (license_alt and not license_decline):
        person = True
    if citizen:
        person = True  # a citizen is a U.S. person
    return citizen, person, clearance


# ── term ─────────────────────────────────────────────────────────────────────

_SEASON = r"(summer|fall|autumn|spring|winter)"
# A year is four digits, or two after an apostrophe ("Summer '27"): "Summer 10-Week
# Internship" is not Summer 2010.
_YEAR = r"(20\d\d|['’]\d\d)\b(?!\s*-?\s*(?:weeks?|wks?|hours?|hrs?|days?|months?)\b)"
_SEASON_YEAR_RE = re.compile(rf"\b{_SEASON}\s*{_YEAR}", re.I)
_YEAR_SEASON_RE = re.compile(rf"\b(20\d\d)\s+{_SEASON}\b", re.I)
# "Spring/Summer 2027", "Fall or Winter 2026": the first season listed, with the year.
_SEASON_PAIR_YEAR_RE = re.compile(rf"\b{_SEASON}\s*(?:/|or|and|&|,)\s*{_SEASON}\s*{_YEAR}", re.I)
_TERM_CONTEXT_RE = re.compile(r"\bintern(?:ship)?s?\b|\bco-?op\b|\bprogram\b|\bstart(?:ing|s)?\b|\bcohort\b", re.I)
_GRAD_CONTEXT_RE = re.compile(r"graduat|degree completion|class of", re.I)
_INTERN_TITLE_RE = re.compile(r"\bintern(?:ship)?s?\b|\bco-?op\b|\bapprentice", re.I)


def _norm_season(s: str) -> str:
    s = s.lower()
    return "fall" if s == "autumn" else s


def _norm_year(y: str) -> int:
    n = int(y.lstrip("'’"))
    return 2000 + n if n < 100 else n


def _first_season_year(s: str) -> tuple[str, int] | None:
    """The earliest "Summer 2027" / "2027 Summer" / "Summer '27" in s."""
    hits = [(m.start(), _norm_season(m.group(1)), _norm_year(m.group(2))) for m in _SEASON_YEAR_RE.finditer(s)]
    hits += [(m.start(), _norm_season(m.group(2)), int(m.group(1))) for m in _YEAR_SEASON_RE.finditer(s)]
    hits += [(m.start(), _norm_season(m.group(1)), _norm_year(m.group(3))) for m in _SEASON_PAIR_YEAR_RE.finditer(s)]
    if not hits:
        return None
    _, season, year = min(hits)
    return season, year


def _term(title: str, sentences: list[str]) -> tuple[str | None, int | None]:
    if not _INTERN_TITLE_RE.search(title or ""):
        return None, None
    hit = _first_season_year(title or "")
    if hit:
        return hit
    m = re.search(rf"\b{_SEASON}\b", title or "", re.I)
    if m:  # "Summer Intern" with no year: take the year from the text if one pairs up
        season = _norm_season(m.group(1))
        for s in sentences:
            h = _first_season_year(s)
            if h and h[0] == season and not _GRAD_CONTEXT_RE.search(s):
                return h
        return season, None
    for s in sentences:
        if _GRAD_CONTEXT_RE.search(s) or not _TERM_CONTEXT_RE.search(s):
            continue
        h = _first_season_year(s)
        if h:
            return h
    return None, None


# ── degree and graduation window ─────────────────────────────────────────────

_DEGREE_PATTERNS = {
    "bachelor": re.compile(
        r"\bbachelor['’]?s?\b|\bundergrad(?:uate)?s?\b|\bB\.?\s?S\.?(?:c\.?)?(?=[\s,/)]|$)|\bB\.?\s?A\.?(?=[\s,/)])|"
        r"\bBSc\b|\bBEng\b|\bsophomore|\bjunior(?:s)?\b(?= (?:or|and|year|standing))|\brising (?:junior|senior)",
        re.I,
    ),
    # Not "MS Excel", "MS Office" …: Microsoft, not a master's.
    "master": re.compile(
        r"\bmaster['’]?s?\b|\bM\.?\s?S\.?(?:c\.?)?(?=[\s,/)]|$)"
        r"(?!\s*(?:Office|Excel|Word|Teams|Project|Access|SQL|Azure|Dynamics|PowerPoint|Outlook|Visio|365)\b)|"
        r"\bMSc\b|\bMEng\b|\bM\.?Eng\b",
        re.I,
    ),
    # Not "PhD researchers/scientists": colleagues, not who may apply.
    "phd": re.compile(
        r"\b(?:Ph\.?\s?D\.?s?|doctoral|doctorate)\b(?!\s+(?:researchers?|scientists?|holders?|staff|team|engineers?)\b)",
        re.I,
    ),
}
_GRAD_STUDENT_RE = re.compile(
    r"(?<!under)\bgraduate (?:students?|degree|program|studies|concentration|level)\b|\bpost-?graduate\b", re.I)
_DEGREE_REQ_RE = re.compile(
    r"\b(?:pursuing|enrolled|currently|must|required?|requires|seeking|open to|candidates?|"
    r"students?|working towards|in (?:the|a|an) (?:final|last)|concentration|major(?:ing)?|studying|"
    r"level|year of study|degree)\b",
    re.I,
)
_DEGREE_SOFT_RE = re.compile(r"\b(?:prefer(?:red|ably)?|a plus|nice to have|bonus|ideal(?:ly)?|or equivalent experience)\b", re.I)
_YEAR_RE = re.compile(r"\b(20[2-3]\d)\b")


def _degrees(title: str, sections: list[tuple[str, bool]]) -> list[str] | None:
    # A degree in the title ("PhD Intern", "Summer Intern, MS/PhD") is the requirement.
    in_title = {lvl for lvl, rx in _DEGREE_PATTERNS.items() if rx.search(title or "")}
    if in_title:
        return [lvl for lvl in ("bachelor", "master", "phd") if lvl in in_title]
    required: set[str] = set()
    soft: set[str] = set()
    for s, soft_section in sections:
        # Pay tables list degree levels next to rates ("Master's: 1st Year $33.00"), often
        # one cell per line ("Bachelor's Degree"): neither is a requirement.
        if not _DEGREE_REQ_RE.search(s) or re.search(r"[$£€]\s?\d", s) or len(s.split()) <= 3:
            continue
        found = {lvl for lvl, rx in _DEGREE_PATTERNS.items() if rx.search(s)}
        if _GRAD_STUDENT_RE.search(s):
            found |= {"master", "phd"}
        if not found:
            continue
        (soft if soft_section or _DEGREE_SOFT_RE.search(s) else required).update(found)
    levels = required or soft
    return [lvl for lvl in ("bachelor", "master", "phd") if lvl in levels] or None


def _grad_years(sentences: list[str]) -> tuple[int | None, int | None]:
    years: list[int] = []
    for s in sentences:
        m = re.search(r"graduat\w*|class of", s, re.I)
        if not m:
            continue
        window = s[m.start(): m.start() + 120]
        years += [int(y) for y in _YEAR_RE.findall(window)]
    if not years:
        return None, None
    return min(years), max(years)


# ── workplace and country ────────────────────────────────────────────────────

_HYBRID_RE = re.compile(
    r"\bhybrid\b(?! (?:cloud|vehicle|electric|app|model|search|architecture|work(?:load)?s?\b(?! (?:schedule|model|arrangement))))|"
    # Some office days a week is hybrid; five is on-site (handled by _ONSITE_RE).
    r"\b[1-4]\s*(?:-\s*[1-4]\s*)?days? (?:a|per|each) week\b[^.]{0,40}\b(?:office|onsite|on-site|in person|in-person)|"
    r"\b(?:office|onsite|on-site|in person|in-person)\b[^.]{0,40}\b[1-4]\s*(?:-\s*[1-4]\s*)?days? (?:a|per|each) week",
    re.I,
)
_REMOTE_RE = re.compile(
    r"\b(?:fully|100%)\s+remote\b|\b(?:this|the) (?:role|position|internship|job) is (?:fully )?remote\b|"
    r"\bremote (?:role|position|internship|opportunity)\b|\bwork (?:from anywhere|remotely)\b|"
    r"\bvirtual (?:internship|role|position)\b",
    re.I,
)
_ONSITE_RE = re.compile(
    r"\b(?:on-?site|in[- ]person|in[- ]office|in the office)\b[^.]{0,60}\b(?:role|position|internship|required|"
    r"expect(?:ed|ation)?|full[- ]time|five days|5 days|every day)\b|"
    r"\b(?:5|five) days (?:a|per|each) week\b[^.]{0,40}\b(?:office|onsite|on-site|in person|in-person)|"
    r"\b(?:roles?|positions?|internships?|jobs?)\b[^.]{0,40}\b(?:on-?site|in[- ]person|in[- ]office)\b",
    re.I,
)
_ATS_WORKPLACE = {"onsite": "onsite", "on-site": "onsite", "hybrid": "hybrid", "remote": "remote"}


def _workplace(hints: dict, location: str | None, sentences: list[str]) -> str | None:
    raw = str(hints.get("workplace_type") or "").strip().lower().replace("_", "")
    ats = _ATS_WORKPLACE.get(raw)
    text: str | None = None
    for s in sentences:
        if _EEO_RE.search(s):
            continue
        if _HYBRID_RE.search(s):
            text = "hybrid"
            break
        if text is None and _REMOTE_RE.search(s) and not re.search(r"remote[- ]first|not remote", s, re.I):
            text = "remote"
        elif text is None and _ONSITE_RE.search(s):
            text = "onsite"
    if text and ats and text != ats:
        return text  # the posting's own words win over a board-level default
    if ats or text:
        return ats or text
    loc = (location or "").strip().lower()
    if hints.get("is_remote") is True or re.match(r"remote\b", loc) or re.search(r"[;,/]\s*remote$", loc):
        return "remote"
    return None


_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky",
    "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd",
    "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}
_US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri",
    "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
}
_COUNTRY_NAMES = {
    "united states": "US", "united states of america": "US", "usa": "US", "us": "US", "u.s.": "US",
    "canada": "CA", "united kingdom": "GB", "uk": "GB", "england": "GB", "scotland": "GB", "germany": "DE",
    "france": "FR", "netherlands": "NL", "ireland": "IE", "spain": "ES", "italy": "IT", "poland": "PL",
    "portugal": "PT", "switzerland": "CH", "sweden": "SE", "denmark": "DK", "norway": "NO", "finland": "FI",
    "belgium": "BE", "austria": "AT", "czech republic": "CZ", "czechia": "CZ", "romania": "RO",
    "israel": "IL", "india": "IN", "singapore": "SG", "japan": "JP", "south korea": "KR", "korea": "KR",
    "china": "CN", "hong kong": "HK", "taiwan": "TW", "australia": "AU", "new zealand": "NZ", "brazil": "BR",
    "mexico": "MX", "argentina": "AR", "colombia": "CO", "chile": "CL", "united arab emirates": "AE",
    "uae": "AE", "philippines": "PH", "vietnam": "VN", "indonesia": "ID", "malaysia": "MY", "thailand": "TH",
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE", "egypt": "EG", "turkey": "TR", "greece": "GR",
    "hungary": "HU", "ukraine": "UA", "estonia": "EE", "lithuania": "LT", "latvia": "LV", "serbia": "RS",
}
_CA_PROVINCES = {"on", "qc", "bc", "ab", "mb", "sk", "ns", "nb", "nl", "pe", "ontario", "quebec", "british columbia", "alberta"}
_CITY_COUNTRY = {
    "buenos aires": "AR", "jakarta": "ID", "medellin": "CO", "medellín": "CO", "bogota": "CO",
    "bogotá": "CO", "santiago": "CL", "lima": "PE", "cape town": "ZA", "johannesburg": "ZA",
    "lagos": "NG", "nairobi": "KE", "cairo": "EG", "istanbul": "TR", "athens": "GR", "budapest": "HU",
    "bucharest": "RO", "kyiv": "UA", "tallinn": "EE", "vilnius": "LT", "riga": "LV", "belgrade": "RS",
    "manila": "PH", "ho chi minh city": "VN", "kuala lumpur": "MY", "bangkok": "TH", "shanghai": "CN",
    "beijing": "CN", "shenzhen": "CN", "osaka": "JP", "vienna": "AT", "brussels": "BE", "helsinki": "FI",
    "haifa": "IL", "jerusalem": "IL", "chennai": "IN", "noida": "IN", "kolkata": "IN", "delhi": "IN",
    "brisbane": "AU", "perth": "AU", "wellington": "NZ", "christchurch": "NZ", "rio de janeiro": "BR",
    "guadalajara": "MX", "monterrey": "MX", "abu dhabi": "AE", "riyadh": "SA", "doha": "QA",
    "london": "GB", "manchester": "GB", "cambridge, uk": "GB", "edinburgh": "GB", "toronto": "CA",
    "vancouver": "CA", "montreal": "CA", "waterloo": "CA", "ottawa": "CA", "calgary": "CA", "berlin": "DE",
    "munich": "DE", "münchen": "DE", "hamburg": "DE", "frankfurt": "DE", "cologne": "DE", "paris": "FR",
    "amsterdam": "NL", "dublin": "IE", "madrid": "ES", "barcelona": "ES", "lisbon": "PT", "milan": "IT",
    "zurich": "CH", "zürich": "CH", "geneva": "CH", "stockholm": "SE", "copenhagen": "DK", "oslo": "NO",
    "warsaw": "PL", "krakow": "PL", "prague": "CZ", "tel aviv": "IL", "bangalore": "IN", "bengaluru": "IN",
    "hyderabad": "IN", "pune": "IN", "mumbai": "IN", "new delhi": "IN", "gurgaon": "IN", "singapore": "SG",
    "tokyo": "JP", "seoul": "KR", "sydney": "AU", "melbourne": "AU", "auckland": "NZ", "são paulo": "BR",
    "sao paulo": "BR", "mexico city": "MX", "dubai": "AE", "hong kong": "HK", "taipei": "TW",
    "san francisco": "US", "new york": "US", "nyc": "US", "seattle": "US", "boston": "US", "austin": "US",
    "chicago": "US", "los angeles": "US", "denver": "US", "atlanta": "US", "washington dc": "US",
    "washington, dc": "US", "san jose": "US", "palo alto": "US", "mountain view": "US", "menlo park": "US",
    "sunnyvale": "US", "san diego": "US", "pittsburgh": "US", "philadelphia": "US", "miami": "US",
    "dallas": "US", "houston": "US", "salt lake city": "US", "portland": "US", "costa mesa": "US",
    "el segundo": "US", "hawthorne": "US", "long beach": "US", "south san francisco": "US",
    "redwood city": "US", "arlington": "US", "reston": "US", "huntsville": "US", "columbus": "US",
}


def country_code(value: str | None) -> str | None:
    """ISO-2 for a country name or a location string ("Austin, TX" → "US"). A bare
    two-letter value is ambiguous here ("CA": Canada or California?) and gives None;
    ATS country fields, which are ISO codes, go through `_country` instead."""
    if not value:
        return None
    v = value.strip()
    if re.fullmatch(r"[A-Za-z]{2}", v):
        up = v.upper()
        return up if up == "US" or up.lower() not in _US_STATES else None
    low = v.lower()
    if low in _COUNTRY_NAMES:
        return _COUNTRY_NAMES[low]
    first = re.split(r"\s*[;|/•·]\s*|\s+or\s+", low)[0]
    parts = [p.strip(" .") for p in first.split(",") if p.strip(" .")]
    # A full country name anywhere wins.
    for p in reversed(parts):
        if p in _COUNTRY_NAMES and len(p) > 2:
            return _COUNTRY_NAMES[p]
    # "City, Region, CC": a trailing two-letter part after a region is an ISO code.
    # ("Bengaluru, KA, IN", "Montreal, QC, CA"); but "New York, New York, NY" is a state.
    if len(parts) >= 3 and re.fullmatch(r"[a-z]{2}", parts[-1]):
        region = parts[-2]
        if parts[-1] not in _US_STATES or (region not in _US_STATES and region not in _US_STATE_NAMES):
            return parts[-1].upper()
    # A known city decides before any two-letter code: "Toronto, CA" and "Berlin, DE" are
    # Canada and Germany, not California and Delaware.
    if len(parts) == 2 and parts[1] in _CA_PROVINCES:
        return "CA"  # "London, ON"
    city_code = next((code for city, code in _CITY_COUNTRY.items() if parts and parts[0] == city), None)
    if city_code:
        second = parts[1] if len(parts) > 1 else ""
        # "Paris, TX" / "London, KY" are American; "Berlin, DE" and "Toronto, CA" name the
        # city's own country with its ISO code, which happens to spell a state.
        if second in _US_STATES and second.upper() != city_code:
            return "US"
        return city_code
    for p in reversed(parts):
        if p in _COUNTRY_NAMES:
            return _COUNTRY_NAMES[p]
        if p in _US_STATE_NAMES:
            return "US"
        if p in _US_STATES:
            return "US"
    for city, code in _CITY_COUNTRY.items():
        if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", first):
            return code
    if v.upper() == "US":
        return "US"
    return None


def _country(location: str | None, hints: dict) -> str | None:
    hint = str(hints.get("country") or "").strip()
    # Lever's `country` is an ISO code ("CA" is Canada); Ashby's is a country name.
    if re.fullmatch(r"[A-Za-z]{2}", hint):
        return hint.upper()
    return country_code(hint) or country_code(location)


# ── entry point ──────────────────────────────────────────────────────────────

def extract_eligibility(
    title: str | None,
    location: str | None,
    text: str | None,
    hints: dict | None = None,
) -> Eligibility:
    """All student-filter fields for one posting. `text` is plain_text of the RAW HTML;
    `hints` holds the ATS's own fields: {"workplace_type", "is_remote", "country"}."""
    hints = hints or {}
    sections = _sections(text or "")
    sentences = [s for s, _ in sections]
    season, year = _term(title or "", sentences)
    citizen, person, clearance = _citizenship(sections)
    gmin, gmax = _grad_years(sentences)
    return Eligibility(
        term_season=season,
        term_year=year,
        degree_levels=_degrees(title or "", sections),
        grad_year_min=gmin,
        grad_year_max=gmax,
        us_citizen_required=citizen,
        us_person_required=person,
        clearance_required=clearance,
        workplace_type=_workplace(hints, location, sentences),
        country=_country(location, hints),
    )
