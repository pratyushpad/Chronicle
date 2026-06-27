import html
from typing import Any

import httpx

from .base import RawJob

_BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


class GreenhouseAdapter:
    source = "greenhouse"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> list[RawJob]:
        url = _BASE.format(slug=slug)
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            dept = None
            depts = item.get("departments") or []
            if depts:
                dept = depts[0].get("name")

            loc = item.get("location") or {}
            description_html = None
            raw_content = item.get("content")
            if raw_content:
                description_html = html.unescape(raw_content)

            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=item.get("title", ""),
                    location=loc.get("name"),
                    department=dept,
                    employment_type=None,
                    description_html=description_html,
                    apply_url=item.get("absolute_url", ""),
                    posted_at=item.get("updated_at"),
                    remote=None,
                )
            )
        return jobs
