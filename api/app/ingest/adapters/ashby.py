from typing import AsyncIterator

import httpx

from ..pay import pay_from_ashby
from .base import RawJob, iter_board_json

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


class AshbyAdapter:
    source = "ashby"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> AsyncIterator[RawJob]:
        """Yield one RawJob at a time — a full board is never materialized as a list."""
        url = _BASE.format(slug=slug)

        async for item in iter_board_json(client, url, "jobs.item", slug):
            yield self.parse(item)

    @staticmethod
    def parse(item: dict) -> RawJob:
        """One board item → RawJob (pure; also used by the pay evaluation)."""
        team = item.get("team")
        return RawJob(
            source_job_id=str(item["id"]),
            title=item.get("title", ""),
            location=item.get("location"),
            department=item.get("department"),
            employment_type=item.get("employmentType"),
            # posting-api returns the full body inline — nothing extra to fetch.
            description_html=item.get("descriptionHtml"),
            apply_url=item.get("jobUrl", ""),
            # Ashby has no updatedAt; publishedAt serves the cutoff too.
            posted_at=item.get("publishedAt"),
            remote=item.get("isRemote"),
            updated_at=item.get("publishedAt"),
            department_hints=[team] if isinstance(team, str) and team else [],
            # includeCompensation=true already puts it on every job; it was ignored.
            pay=pay_from_ashby(item.get("compensation")),
        )
