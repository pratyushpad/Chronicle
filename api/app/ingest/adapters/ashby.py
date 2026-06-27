from typing import Any

import httpx

from .base import RawJob

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


class AshbyAdapter:
    source = "ashby"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> list[RawJob]:
        url = _BASE.format(slug=slug)
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=item.get("title", ""),
                    location=item.get("location"),
                    department=item.get("department"),
                    employment_type=item.get("employmentType"),
                    description_html=None,
                    apply_url=item.get("jobUrl", ""),
                    posted_at=item.get("publishedAt"),
                    remote=item.get("isRemote"),
                )
            )
        return jobs
