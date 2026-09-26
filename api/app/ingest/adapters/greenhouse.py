import html
import re
from typing import AsyncIterator

import httpx

from ..pay import pay_from_greenhouse
from .base import RawJob, iter_board_json

# pay_transparency=true adds `pay_input_ranges` to every job on the SAME list call —
# structured pay at no extra request cost.
_BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true&pay_transparency=true"

# Custom metadata fields that name a discipline ("Job Group": "Software Engineering",
# "External Department Name for Job Board": "Internships"). Values are department hints.
_HINT_FIELD_RE = re.compile(r"department|job group|job family|function|\bteam\b", re.IGNORECASE)


def _metadata(item: dict) -> tuple[list[str], str | None]:
    """(department hints, employment type) from Greenhouse's custom metadata fields."""
    hints: list[str] = []
    employment_type = None
    for field in item.get("metadata") or []:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        value = field.get("value")
        values = [v for v in value if isinstance(v, str)] if isinstance(value, list) else (
            [value] if isinstance(value, str) else []
        )
        values = [v.strip() for v in values if v and v.strip()]
        if not values:
            continue
        if name.strip().lower() == "employment type":
            employment_type = values[0]
        elif _HINT_FIELD_RE.search(name):
            hints.extend(values)
    return hints, employment_type


class GreenhouseAdapter:
    source = "greenhouse"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> AsyncIterator[RawJob]:
        """Yield one RawJob at a time — a full board (36 MB / 2,100 jobs of
        description HTML) is never materialized as a list."""
        url = _BASE.format(slug=slug)

        async for item in iter_board_json(client, url, "jobs.item", slug):
            yield self.parse(item)

    @staticmethod
    def parse(item: dict) -> RawJob:
        """One board item → RawJob (pure; also used by the pay evaluation)."""
        dept = None
        depts = item.get("departments") or []
        if depts:
            dept = depts[0].get("name")

        loc = item.get("location") or {}
        description_html = None
        raw_content = item.get("content")
        if raw_content:
            description_html = html.unescape(raw_content)

        hints, employment_type = _metadata(item)

        return RawJob(
            source_job_id=str(item["id"]),
            title=item.get("title", ""),
            location=loc.get("name"),
            department=dept,
            employment_type=employment_type,
            description_html=description_html,
            apply_url=item.get("absolute_url", ""),
            posted_at=item.get("first_published"),
            remote=None,
            updated_at=item.get("updated_at"),
            department_hints=hints,
            pay=pay_from_greenhouse(item.get("pay_input_ranges"), description_html),
        )
