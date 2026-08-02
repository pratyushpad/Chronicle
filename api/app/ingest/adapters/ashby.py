import httpx

from .base import RawJob, iter_board_json

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


class AshbyAdapter:
    source = "ashby"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> list[RawJob]:
        url = _BASE.format(slug=slug)

        jobs = []
        async for item in iter_board_json(client, url, "jobs.item", slug):
            jobs.append(
                RawJob(
                    source_job_id=str(item["id"]),
                    title=item.get("title", ""),
                    location=item.get("location"),
                    department=item.get("department"),
                    employment_type=item.get("employmentType"),
                    # posting-api returns the full body inline — nothing extra to fetch.
                    # Flows through strip_html → description_text/tags/salary, and a
                    # changed content_hash re-embeds these rows with real signal.
                    description_html=item.get("descriptionHtml"),
                    apply_url=item.get("jobUrl", ""),
                    posted_at=item.get("publishedAt"),
                    remote=item.get("isRemote"),
                )
            )
        return jobs
