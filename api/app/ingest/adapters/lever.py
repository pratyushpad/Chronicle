import httpx

from .base import RawJob, iter_board_json

_BASE = "https://api.lever.co/v0/postings/{slug}?mode=json"


class LeverAdapter:
    source = "lever"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> list[RawJob]:
        url = _BASE.format(slug=slug)

        jobs = []
        # Lever returns a top-level JSON array, hence the bare "item" prefix.
        async for item in iter_board_json(client, url, "item", slug):
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
