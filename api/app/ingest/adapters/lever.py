from typing import Any

import httpx

from .base import RawJob

_BASE = "https://api.lever.co/v0/postings/{slug}?mode=json"


class LeverAdapter:
    source = "lever"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> list[RawJob]:
        url = _BASE.format(slug=slug)
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()

        jobs = []
        for item in data:
            cats = item.get("categories") or {}
            created_ms = item.get("createdAt")
            posted_at = str(created_ms) if created_ms is not None else None

            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=item.get("text", ""),
                    location=cats.get("location"),
                    department=cats.get("team"),
                    employment_type=cats.get("commitment"),
                    description_html=item.get("description"),
                    apply_url=item.get("hostedUrl", ""),
                    posted_at=posted_at,
                    remote=None,
                )
            )
        return jobs
