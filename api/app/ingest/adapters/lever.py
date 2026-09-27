import html
from typing import AsyncIterator

import httpx

from ..pay import pay_from_lever
from .base import RawJob, iter_board_json

_BASE = "https://api.lever.co/v0/postings/{slug}?mode=json"


def _full_description(item: dict) -> str | None:
    """Lever splits a posting across `description` (the intro), `lists` (each a heading
    plus `<li>` items — usually the requirements) and `additional` (the closing section,
    where pay and sponsorship language often sit). Only `description` used to be kept."""
    parts: list[str] = []
    if item.get("description"):
        parts.append(item["description"])
    for block in item.get("lists") or []:
        if not isinstance(block, dict):
            continue
        heading = html.escape(str(block.get("text") or "").strip())
        content = block.get("content") or ""
        if heading:
            parts.append(f"<h3>{heading}</h3>")
        if content:
            parts.append(f"<ul>{content}</ul>")
    if item.get("additional"):
        parts.append(item["additional"])
    return "".join(parts) or None


class LeverAdapter:
    source = "lever"

    async def fetch(self, slug: str, client: httpx.AsyncClient) -> AsyncIterator[RawJob]:
        """Yield one RawJob at a time — a full board is never materialized as a list."""
        url = _BASE.format(slug=slug)

        # Lever returns a top-level JSON array, hence the bare "item" prefix.
        async for item in iter_board_json(client, url, "item", slug):
            yield self.parse(item)

    @staticmethod
    def parse(item: dict) -> RawJob:
        """One board item → RawJob (pure; also used by the pay evaluation)."""
        cats = item.get("categories") or {}
        created_ms = item.get("createdAt")
        # Lever exposes no separate publish or edit time; createdAt is both.
        created = str(created_ms) if created_ms is not None else None
        dept_hint = cats.get("department")
        return RawJob(
            source_job_id=str(item["id"]),
            title=item.get("text", ""),
            location=cats.get("location"),
            department=cats.get("team"),
            employment_type=cats.get("commitment"),
            description_html=_full_description(item),
            apply_url=item.get("hostedUrl", ""),
            posted_at=created,
            remote=None,
            updated_at=created,
            department_hints=[dept_hint] if isinstance(dept_hint, str) and dept_hint else [],
            pay=pay_from_lever(item.get("salaryRange")),
        )
