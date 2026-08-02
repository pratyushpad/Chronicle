import html

import httpx

from .base import RawJob, iter_board_json

_BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


class GreenhouseAdapter:
    source = "greenhouse"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> list[RawJob]:
        url = _BASE.format(slug=slug)

        jobs = []
        async for item in iter_board_json(client, url, "jobs.item", slug):
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
