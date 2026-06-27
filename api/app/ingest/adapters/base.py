from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import httpx


@dataclass
class RawJob:
    source_job_id: str
    title: str
    location: str | None
    department: str | None
    employment_type: str | None
    description_html: str | None
    apply_url: str
    posted_at: str | None  # ISO string or epoch-ms string; normalizer parses
    remote: bool | None


class ATSAdapter(Protocol):
    source: str

    async def fetch(self, slug: str, client: "httpx.AsyncClient") -> list[RawJob]:
        """Fetch all open jobs for the given board slug. Raises on hard failure."""
        ...
