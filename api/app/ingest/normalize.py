import re
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
