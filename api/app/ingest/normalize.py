import re
from collections.abc import Iterable
from datetime import datetime, timezone

from selectolax.parser import HTMLParser

from .adapters.base import RawJob

_REQ_ID_RE = re.compile(
    r"[\s\-–—]+(?:req|job|jid|jreq|jr|ref)[#\s]?[\w\-]+\s*$"
    r"|[\s\-–—]+\([\w\s#\-]+\)\s*$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_REMOTE_PREFIX_RE = re.compile(r"^remote\s*[-–—:]\s*", re.IGNORECASE)
_REMOTE_WORD_RE = re.compile(r"\bremote\b", re.IGNORECASE)

_INTERN_RE = re.compile(r"\bintern(ship)?\b", re.IGNORECASE)
_NEW_GRAD_RE = re.compile(r"\b(new\s*grad|entry[\s\-]?level|university\s*grad|campus\s*hire|recent\s*grad)\b", re.IGNORECASE)
_SENIOR_RE = re.compile(r"\b(senior|sr\.?\s|lead\s|principal|staff\s|distinguished|architect)\b", re.IGNORECASE)
_MANAGER_RE = re.compile(r"\b(manager|director|vp\s|vice\s*president|head\s+of|chief)\b", re.IGNORECASE)
_MID_RE = re.compile(r"\b(mid[\s\-]?level|intermediate|associate\s)\b", re.IGNORECASE)


def normalize_title(title: str) -> str:
    title = _REQ_ID_RE.sub("", title)
    return _WHITESPACE_RE.sub(" ", title).strip().lower()


def normalize_location(location: str | None) -> str | None:
    if not location:
        return None
    loc = _REMOTE_PREFIX_RE.sub("", location)
    return _WHITESPACE_RE.sub(" ", loc).strip().lower() or None


def dedup_title(title_normalized: str, location_normalized: str | None) -> str:
    """Title used for cross-location dedup keying.

    Some ATS boards bake the city into the posting title, so the same role posted
    to N cities reads as N distinct titles (e.g.
    'manual qa engineer, simba team - skopje' vs '... - zagreb'). Strip a trailing
    location suffix that matches the row's normalized location (the full string and
    its first city segment) so cross-posts share one key. Falls back to the full
    normalized title if stripping would empty it — avoids over-stripping genuine
    title tails like 'engineer, backend'."""
    t = title_normalized
    if location_normalized:
        candidates = [location_normalized]
        city = location_normalized.split(",")[0].strip()
        if city and city != location_normalized:
            candidates.append(city)
        for loc in candidates:
            t = re.sub(
                r"\s*[-–—,(]\s*" + re.escape(loc) + r"\s*\)?\s*$",
                "",
                t,
                flags=re.IGNORECASE,
            )
    return t.strip(" -–—,") or title_normalized


# Genuine req-id tail: keyword-prefixed ("- JR12345", "req#5").
_KEYING_REQ_ID_RE = re.compile(
    r"[\s\-–—]+(?:req|job|jid|jreq|jr|ref)[#\s]?[\w\-]+\s*$", re.IGNORECASE
)
# Number/id-shaped trailing parenthetical ("(12345)", "(R-2024-1)", "(Req #7)").
_KEYING_NUM_PAREN_RE = re.compile(r"[\s\-–—]+\([^)]*\d[^)]*\)\s*$")


def keying_title(title: str) -> str:
    """Title used to BUILD the dedup key (distinct from `normalize_title`, which is
    display-facing and strips every trailing parenthetical).

    `normalize_title`'s req-id regex throws away the distinguishing team/qualifier
    parenthetical — so 'Staff Software Engineer (Data Platform)' and '(Money)' both
    reduce to 'staff software engineer' and collapse into one card (confirmed prod
    over-collapse). This variant PRESERVES an alphabetic qualifier and strips only
    genuine req-id noise (keyword- or number-shaped tails). The location suffix is
    stripped afterwards by `dedup_title`, so same role cross-posted to N cities still
    collapses (SIMBA stays one) while different qualifiers stay distinct."""
    t = _KEYING_REQ_ID_RE.sub("", title)
    t = _KEYING_NUM_PAREN_RE.sub("", t)
    return _WHITESPACE_RE.sub(" ", t).strip().lower()


def infer_remote(raw_job: RawJob) -> bool | None:
    if raw_job.remote is not None:
        return raw_job.remote
    haystack = " ".join(filter(None, [raw_job.title, raw_job.location]))
    return True if _REMOTE_WORD_RE.search(haystack) else None


def strip_html(html: str | None) -> str | None:
    if not html:
        return None
    tree = HTMLParser(html)
    text = tree.text(separator="\n", strip=True)
    return _WHITESPACE_RE.sub(" ", text).strip() or None


# ── HTML → plain text (the one text pipeline) ─────────────────────────────────

# Never rendered as text by a browser, so never text to us: CSS/JS bodies, fallback
# markup, inline SVG labels, embedded frames, and anything in <head>.
_DROP_TAGS = frozenset({
    "script", "style", "noscript", "template", "head", "svg", "iframe", "object",
    "embed", "canvas", "math", "title",
})
# Elements that start a new line in a browser. Their text is fenced with spaces so two
# blocks never fuse into one word; everything else (strong, span, a, em …) is inline
# and joins with NO inserted space — "$150,<strong>000</strong>" must stay "$150,000".
_BLOCK_TAGS = frozenset({
    "p", "div", "li", "br", "hr", "tr", "td", "th", "section", "article", "ul", "ol",
    "table", "thead", "tbody", "tfoot", "caption", "blockquote", "pre", "dl", "dd", "dt",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "footer", "main", "nav", "aside",
    "figure", "figcaption", "address", "details", "summary", "center", "form", "fieldset",
})
# Zero-width characters aren't whitespace to `\s`, but they'd split tokens invisibly.
_ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿]")
# Blocks end in ONE newline; any other whitespace run is one space. Keeping the line
# break matters to extractors: "Hourly Rate: $33.00" followed by a "Housing stipend…"
# bullet must not read as "$33.00 housing" (a benefit), and it keeps stored text readable.
_INLINE_WS_RE = re.compile(r"[^\S\n]+")
_LINE_BREAK_RE = re.compile(r"\s*\n\s*")


def plain_text(raw_html: str | None) -> str | None:
    """Readable text of an HTML fragment: the single input for every extractor (pay,
    tech tags, sponsorship) and for the content hash.

    Block elements end in a single newline, inline text joins with no separator,
    entities are decoded, non-content elements (script/style/…) are dropped, and any
    other whitespace collapses to one space. The old `strip_html` joined every text node with a separator, which
    turned `$150,<strong>000</strong>` into "$150, 000" (unparseable) and kept the body
    of <script>/<style> tags as if it were posting text.

    Iterative walk (explicit stack): posting HTML nests arbitrarily deep and must
    never be able to hit Python's recursion limit mid-ingest.
    """
    if not raw_html or not raw_html.strip():
        return None
    root = HTMLParser(raw_html).root
    if root is None:
        return None
    parts: list[str] = []
    # Stack items: a node to expand, or a plain string (a block's closing fence).
    stack: list = [root]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            parts.append(item)
            continue
        tag = item.tag
        if tag == "-text":
            # A newline inside a text node is just whitespace in HTML — only block
            # boundaries (below) produce line breaks.
            parts.append(_WHITESPACE_RE.sub(" ", item.text(deep=False)))
            continue
        if tag in _DROP_TAGS or tag == "_comment":
            continue
        block = tag in _BLOCK_TAGS
        if block:
            parts.append("\n")
            stack.append("\n")  # closing fence, emitted after all children
        children = list(item.iter(include_text=True))
        stack.extend(reversed(children))
    text = _ZERO_WIDTH_RE.sub("", "".join(parts))
    text = _INLINE_WS_RE.sub(" ", text)
    return _LINE_BREAK_RE.sub("\n", text).strip() or None


def infer_experience_level(title: str) -> str | None:
    if _INTERN_RE.search(title):
        return "Internship"
    if _NEW_GRAD_RE.search(title):
        return "Entry Level"
    if _MANAGER_RE.search(title):
        return "Management"
    if _SENIOR_RE.search(title):
        return "Senior"
    if _MID_RE.search(title):
        return "Mid Level"
    return None


# Chronicle lists internship and early-career roles. Senior and management roles are most
# of what company boards post (about 98% of stored rows in Sept 2026) and don't fit the
# free 512 MB database, so ingest skips them. A "manager" title with an early-career
# marker ("Associate Product Manager", "Rotational Program Manager") is kept.
_EARLY_CAREER_RE = re.compile(
    r"\b(associate|junior|jr\.?|graduate|apprentice|rotational|early[\s\-]?career)\b", re.IGNORECASE
)
_SENIOR_ASSOCIATE_RE = re.compile(
    r"\bassociate\s+(director|vice\s*president|vp|partner|principal|general\s+counsel)\b", re.IGNORECASE
)


def is_out_of_scope(title: str, level: str | None) -> bool:
    """True for roles Chronicle doesn't store: senior roles, and management roles
    without an early-career marker. `level` is infer_experience_level(title)."""
    if level == "Senior":
        return True
    if level == "Management":
        return not _EARLY_CAREER_RE.search(title) or bool(_SENIOR_ASSOCIATE_RE.search(title))
    return False


# ── Department normalization (controlled vocabulary) ──────────────────────────

# Leading numeric/req code block, e.g. "20213 ", "REQ-123 - ", "#45 ".
_DEPT_CODE_RE = re.compile(r"^[\s#]*[A-Za-z]{0,4}-?\d[\w\-]*\s*[-–—:]?\s*")

# The closed vocabulary. "Engineering" is the general/software bucket; the specific
# engineering disciplines students filter on get their own category. "Other" (a
# non-empty value nothing maps) is the only value outside this tuple, and the UI never
# shows it as a chip.
DEPARTMENTS: tuple[str, ...] = (
    "Engineering", "ML & AI", "Infrastructure", "Hardware", "Robotics & Autonomy",
    "Quality", "Manufacturing", "Security", "Data", "Design", "Product", "Research",
    "Sales", "Marketing", "Finance", "People", "Legal", "Support", "IT", "Operations", "G&A",
)


def _rules(*pairs: tuple[str, str]) -> list[tuple[re.Pattern, str]]:
    return [(re.compile(p), c) for p, c in pairs]


# Department strings (and ATS hints). Ordered — FIRST match wins, so order resolves the
# overlaps: Security before Engineering ("security engineering"); People's recruiting
# orgs before Engineering ("Technical Recruiting"); Sales before Marketing and
# Engineering ("Sales Growth", "Sales Engineering"); Marketing before Product ("Product
# Marketing"); the specific disciplines before the general Engineering bucket
# ("Engineering - Infrastructure" → Infrastructure). Position-independent — never
# slices to the trailing segment (how internal org names like "Square Outside" used to
# leak through). Deliberately absent: bare "systems"/"tech"/"solutions"/"law"/"growth"
# — business-unit names like "USA Space Systems" or "Risk Solutions" say nothing about
# the discipline, so they fall through to the title.
_DEPT_RULES = _rules(
    (r"security|infosec|appsec|trust\s*&?\s*(?:and\s*)?safety", "Security"),
    (r"recruit|talent acquisition|human resources|\bhr\b|\bpeople\b|learning (?:and|&) development|\bl&d\b|compensation|benefits|workplace|diversity", "People"),
    (r"\bsales\b|account executive|account manager|account director|business development|revenue|\bgtm\b|go[\s-]?to[\s-]?market|\bs&m\b", "Sales"),
    (r"marketing|\bbrand\b|communications|\bcontent\b|demand gen|\bseo\b|public relations|social media|^growth$", "Marketing"),
    (r"hardware|electrical|electronic|mechanical|firmware|embedded|silicon|\basic\b|\bfpga\b|\brf\b|avionics|power systems|propulsion|turbomachinery|combustion|\bfluids?\b|structures|aerodynamic|thermal|payload|antenna|launch vehicle", "Hardware"),
    (r"robot|autonom|perception|controls? (?:engineering|systems)|simulation|motion planning", "Robotics & Autonomy"),
    (r"data cent(?:er|re)|site reliability|\bsre\b|devops|infrastructure|\binfra\b|cloud|platform engineering|networking|\bnetwork\b", "Infrastructure"),
    (r"machine learning|deep learning|artificial intelligence|\bml\b|\bai\b|computer vision|\bnlp\b|\bllm", "ML & AI"),
    (r"manufactur|assembly|production (?:operations|line|planning)|machining|fabrication", "Manufacturing"),
    (r"quality|\bqa\b|test engineering", "Quality"),
    (r"design|user experience|\bux\b|\bui\b|creative", "Design"),
    (r"\bdata\b|analytics|data science|business intelligence", "Data"),
    (r"\bproducts?\b", "Product"),
    (r"engineer|software|developer|\bdev\b|backend|front[\s-]?end|full[\s-]?stack|technical", "Engineering"),
    (r"finance|financial|accounting|controller|treasury|fp&a|\baudit\b|\btax\b|procurement|payroll", "Finance"),
    (r"legal|counsel|compliance|regulatory|privacy|paralegal", "Legal"),
    (r"customer success|customer experience|customer service|customer support|customer care|\bcx\b|\bsupport\b|help desk", "Support"),
    (r"research|\br&d\b|\bscience\b", "Research"),
    (r"information technology|\bit\b|helpdesk|sysadmin", "IT"),
    (r"operations|\bops\b|logistics|supply chain|supply planning|fulfillment|warehouse|facilities", "Operations"),
    (r"g&a|general (?:and|&) administrative|administrative|\badmin\b|corporate|\boffice\b", "G&A"),
)

# Job titles: keyed on the ROLE noun, so qualifiers don't steal it ("Senior AI Software
# Engineer" is Engineering, "Product Designer" is Design, "Sales Engineer" is Sales,
# "Software Development Engineer in Test" is Quality). Ordered, first match wins.
_TITLE_RULES = _rules(
    (r"(?:\b|cyber)security\b|infosec|appsec|penetration test|red team|trust\s*&?\s*safety", "Security"),
    (r"recruit|talent acquisition|sourcer|human resources|\bhrbp\b|people (?:partner|operations|ops)|workplace|employee experience", "People"),
    (r"\blegal\b|counsel|attorney|lawyer|paralegal|compliance|regulatory", "Legal"),
    (r"\bsales\b|account executive|account manager|business development|\bbdr\b|\bsdr\b", "Sales"),
    (r"marketing|\bbrand\b|\bseo\b|communications|public relations|social media|content (?:strategist|writer|marketing)", "Marketing"),
    (r"designer|\bux\b|\bui\b|user experience|product design|visual design|graphic design", "Design"),
    (r"product manag|product lead|product owner|\bapm\b|program manag", "Product"),
    (r"customer success|customer support|technical support|support engineer|customer care|help ?desk", "Support"),
    (r"machine learning|deep learning|\bml\b|computer vision|\bnlp\b|natural language|\bllms?\b|reinforcement learning|artificial intelligence|\bai (?:engineer|scientist|researcher|research)|recsys|recommender|learning-based", "ML & AI"),
    (r"site reliability|\bsre\b|devops|infrastructure|\binfra\b|platform engineer|cloud engineer|data cent(?:er|re)|network engineer|systems administrator", "Infrastructure"),
    (r"software engineer|software developer|full[\s-]?stack|back[\s-]?end|front[\s-]?end|web developer|mobile engineer|\bios\b|android", "Engineering"),
    (r"manufactur|assembly|machinist|technician, production|production technician|\bmes\b", "Manufacturing"),
    (r"hardware|electrical|electronics?|mechanical|firmware|embedded|silicon|\basic\b|\bfpga\b|\brf\b|avionics|pcb|analog|circuit|power electronics|propulsion|turbomachinery|combustion|\bfluids?\b|structural|aerodynamic|thermal|mechanisms|payload|antenna|launch vehicle|integration (?:&|and) test|\bgnc\b|\bcad\b|optics", "Hardware"),
    (r"robot|autonom|perception|controls engineer|control systems|motion planning|simulation|\bslam\b", "Robotics & Autonomy"),
    (r"\bsdet\b|engineers? in test|\bqa\b|quality|test automation", "Quality"),
    (r"data scien|data analy|data engineer|analytics|business intelligence|\bbi\b analyst", "Data"),
    (r"account(?:ing|ant)|finance|financial|\bfp&a\b|controller|treasury|\btax\b|payroll|procurement|\baudit|investment|credit|\brisk\b|m&a|valuation|value creation", "Finance"),
    (r"research|physics|scientist", "Research"),
    (r"\bit\b|information technology|helpdesk|sysadmin", "IT"),
    (r"operations|logistics|supply|buyer|warehouse|fulfillment|facilities|project manag|construction|real estate|\behs\b|environmental, health", "Operations"),
    (r"engineer|developer|programmer|software", "Engineering"),
    (r"\bgrowth\b|\bcontent\b|social|events?\b|producer", "Marketing"),
    (r"customer", "Support"),
)

# Values that name a hiring PROGRAM or cohort, not a discipline — every intern at a
# company can share one ("Internships", "Early Career", "University Recruiting"). They
# must never decide the department (and must never land interns in People via
# "recruiting"/"talent"), so the title decides instead.
_GENERIC_DEPT_RE = re.compile(
    r"^(?:\d{4}\s+)?(?:intern(?:ship)?s?|co-?ops?|early[\s-]?(?:career|talent)s?|emerging talent|"
    r"university(?: recruiting| relations| programs?)?|general university|campus(?: recruiting)?|"
    r"college|students?|graduates?|new grads?|grad(?:uate)? programs?|"
    r"n/?a|\(n/?a\)|none|other|general|all|various|multiple|tbd|misc(?:ellaneous)?)$"
    r"|intern(?:ship)?s?\b.*\b(?:talent|positions?|program)|\(n/?a\)",
    re.IGNORECASE,
)


def _clean_dept(value: str | None) -> str | None:
    if not value:
        return None
    s = _DEPT_CODE_RE.sub("", value)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s or None


def _match(rules: list[tuple[re.Pattern, str]], text: str) -> str | None:
    low = text.lower()
    for pattern, canonical in rules:
        if pattern.search(low):
            return canonical
    return None


def normalize_department(
    raw: str | None,
    title: str | None = None,
    hints: Iterable[str] = (),
) -> str | None:
    """Map a posting to one controlled-vocabulary department.

    Precedence: a specific raw ATS department → the job title → ATS hints (Greenhouse
    metadata such as "Job Group", Ashby `team`, Lever `categories.department`). Program
    or cohort names ("Internships", "Early Career", "University Recruiting", "Pipeline
    (N/A)") never decide — half of all intern roles used to land in "Other" or "People"
    that way. The title outranks hints because hints are often the same program label
    or a coarse org ("Science" for an ML scientist).

    Returns None when there is nothing at all to go on, and "Other" when there was a
    non-empty department that maps to nothing. The untouched original stays in
    Job.department_raw so this can be retuned without re-ingesting."""
    dept = _clean_dept(raw)
    if dept and not _GENERIC_DEPT_RE.search(dept):
        found = _match(_DEPT_RULES, dept)
        if found:
            return found
    if title:
        found = _match(_TITLE_RULES, title)
        if found:
            return found
    for hint in hints:
        h = _clean_dept(hint)
        if h and not _GENERIC_DEPT_RE.search(h):
            found = _match(_DEPT_RULES, h)
            if found:
                return found
    return "Other" if dept else None


# ── Heuristic enrichment ──────────────────────────────────────────────────────

_SALARY_RANGE_RE = re.compile(
    r"\$\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*\$?\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*[kK]?",
    re.IGNORECASE,
)
_SALARY_SINGLE_RE = re.compile(r"\$\s*(\d{2,3}(?:,\d{3})?)\s*[kK]", re.IGNORECASE)

_NO_SPONSOR_RE = re.compile(
    r"\b(no\s+(?:visa\s+)?sponsorship|must\s+be\s+(?:authorized|a\s+us\s+citizen)|us\s+citizens?\s+only|"
    r"citizenship\s+required|security\s+clearance\s+required|cannot\s+(?:provide|offer)\s+sponsorship|"
    r"not\s+(?:able|eligible)\s+to\s+sponsor|authorization\s+to\s+work\s+in\s+the\s+us\s+(?:is\s+)?required)\b",
    re.IGNORECASE,
)
_YES_SPONSOR_RE = re.compile(
    r"\b(visa\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered|considered)|will\s+sponsor|"
    r"sponsorship\s+available|h.?1b\s+(?:sponsor|transfer|support)|open\s+to\s+sponsoring)\b",
    re.IGNORECASE,
)

_TECH_SKILLS: list[str] = [
    # Languages
    "python", "javascript", "typescript", "java", "golang", "go ", "rust", "c\\+\\+", "c#", "ruby",
    "swift", "kotlin", "scala", "r ", "matlab", "bash", "shell", "sql",
    # Web / API
    "react", "next.js", "nextjs", "vue", "angular", "svelte", "fastapi", "django", "flask",
    "express", "node.js", "nodejs", "rails", "spring", "graphql", "grpc", "rest api",
    # Data / ML
    "pytorch", "tensorflow", "scikit-learn", "sklearn", "pandas", "numpy", "spark", "kafka",
    "airflow", "dbt", "ray", "cuda", "triton", "jax", "transformers", "hugging face",
    "reinforcement learning", "computer vision", "nlp", "llm",
    # Infra / Cloud
    "aws", "gcp", "azure", "kubernetes", "k8s", "docker", "terraform", "linux",
    "postgresql", "postgres", "mysql", "redis", "mongodb", "elasticsearch", "snowflake",
    "databricks", "bigquery", "s3", "lambda", "ci/cd", "github actions",
    # Robotics / Embedded
    "ros", "ros2", "embedded", "firmware", "fpga", "vhdl", "verilog",
]
_SKILL_RES = [(s, re.compile(r"\b" + s.replace(".", r"\.").replace("+", r"\+") + r"\b", re.IGNORECASE)) for s in _TECH_SKILLS]


def _parse_salary_k(raw: str) -> int:
    raw = raw.replace(",", "")
    val = float(raw)
    return int(val * 1000) if val < 1000 else int(val)


def extract_tech_tags(text: str | None) -> list[str] | None:
    if not text:
        return None
    found = []
    seen: set[str] = set()
    for skill, pattern in _SKILL_RES:
        canonical = skill.strip().rstrip("\\")
        if canonical not in seen and pattern.search(text):
            found.append(canonical)
            seen.add(canonical)
    return found or None


def extract_salary(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    m = _SALARY_RANGE_RE.search(text)
    if m:
        lo = _parse_salary_k(m.group(1))
        hi = _parse_salary_k(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        if 30_000 <= lo <= 1_000_000 and 30_000 <= hi <= 1_000_000:
            return lo, hi
    m = _SALARY_SINGLE_RE.search(text)
    if m:
        val = _parse_salary_k(m.group(1))
        if 30_000 <= val <= 1_000_000:
            return val, None
    return None, None


def infer_sponsorship(text: str | None) -> str:
    if not text:
        return "unknown"
    if _NO_SPONSOR_RE.search(text):
        return "likely_no"
    if _YES_SPONSOR_RE.search(text):
        return "likely_yes"
    return "unknown"


def parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    # Lever sends epoch milliseconds as an integer-like string
    if value.isdigit():
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    # ISO 8601
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None
