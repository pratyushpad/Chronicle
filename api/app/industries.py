"""Canonical industries: the ~20 names the site shows, folded from the free-form labels
in the company registry (72 distinct values in companies.seed.json, e.g. "AI", "AI/ML";
"DevTools", "Developer Tools").

Read-time only: companies.industry keeps its raw value, so there is no migration and a
retune here is one deploy. Every API surface returns the canonical name, and the
`industry` filters accept either a canonical name (matched against all its raw labels)
or, for older clients, any raw substring.
"""
from __future__ import annotations

from collections.abc import Iterable

CANONICAL: dict[str, tuple[str, ...]] = {
    "AI & ML": ("AI", "AI/ML"),
    "Fintech": ("FinTech",),
    "Crypto": ("Crypto",),
    "Security": ("Security",),
    "Data & Analytics": ("Data", "Analytics", "Database", "Observability", "Search"),
    "Developer Tools": (
        "Developer Tools", "DevTools", "DevOps", "CDN", "Cloud Storage", "Infrastructure", "CMS",
    ),
    "Health & Bio": ("HealthTech", "Health", "Biotech", "Life Sciences", "Neurotech", "Fitness"),
    "Robotics & Autonomy": ("Robotics", "Autonomous Vehicles"),
    "Aerospace & Defense": ("Space", "Defense", "Defense Tech", "Aerospace"),
    "Climate & Energy": ("Energy", "Climate", "Climate Tech", "Mining"),
    "Work & Productivity": ("HR Tech", "Productivity", "Collaboration", "IT Management"),
    "Sales & Marketing": ("Marketing", "Sales Tech", "CRM", "Customer Success"),
    "Enterprise Software": ("Software", "SaaS", "Enterprise SaaS", "Automation"),
    "Commerce": ("E-commerce", "Commerce", "Retail", "Marketplace", "Restaurant Tech", "Delivery"),
    "Consumer & Social": ("Consumer", "Social", "Creator Economy", "Wearables", "Travel"),
    "Media & Gaming": ("Media", "Entertainment", "Gaming"),
    "Education": ("EdTech",),
    "Mobility & Logistics": ("Logistics", "Transportation", "Mobility", "Automotive"),
    "Hardware": ("Hardware", "Manufacturing", "IoT", "Quantum", "Design Tools"),
    "Legal": ("Legal Tech",),
    "Real Estate": ("PropTech",),
}

_BY_RAW: dict[str, str] = {
    raw.lower(): name for name, raws in CANONICAL.items() for raw in raws
}
_BY_NAME: dict[str, str] = {name.lower(): name for name in CANONICAL}


def canonical_industry(raw: str | None) -> str | None:
    """The canonical name for a raw registry label; None when unknown or empty (the UI
    shows nothing rather than an unmapped label)."""
    if not raw or not raw.strip():
        return None
    key = raw.strip().lower()
    return _BY_RAW.get(key) or _BY_NAME.get(key)


def raw_labels(name: str) -> list[str] | None:
    """All raw labels behind a canonical name (case-insensitive), or None if `name`
    isn't canonical."""
    canon = _BY_NAME.get(name.strip().lower())
    if canon is None:
        return None
    return [canon, *CANONICAL[canon]]


def fold_counts(rows: Iterable[tuple[str | None, int]]) -> list[tuple[str, int]]:
    """(raw label, count) rows → (canonical name, summed count), largest first."""
    totals: dict[str, int] = {}
    for raw, count in rows:
        name = canonical_industry(raw)
        if name:
            totals[name] = totals.get(name, 0) + int(count)
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
