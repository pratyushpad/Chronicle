import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator, Protocol

if TYPE_CHECKING:
    import httpx

# Hard cap on a single board's raw JSON. A pathological payload must fail that
# one company with a recorded error — never take down the whole process.
MAX_BOARD_BYTES = 64 * 1024 * 1024
# Response bodies spool to RAM up to this, then overflow to disk.
_SPOOL_MAX_BYTES = 4 * 1024 * 1024


class BoardTooLarge(Exception):
    """Board JSON exceeded MAX_BOARD_BYTES. Not retryable — re-fetching won't shrink it."""

    def __init__(self, slug: str, limit: int) -> None:
        super().__init__(f"board '{slug}' exceeds {limit // (1024 * 1024)} MB payload cap")


async def iter_board_json(
    client: "httpx.AsyncClient",
    url: str,
    prefix: str,
    slug: str,
    max_bytes: int | None = None,
) -> AsyncIterator[dict]:
    """Stream a board's JSON and yield the items under `prefix` one at a time.

    Peak memory stays O(one job): the body streams to a spooled temp file (disk
    past _SPOOL_MAX_BYTES) and ijson walks it incrementally. Materializing a
    mega-board in one json() call — 36 MB raw / ~175 MB peak for Anduril's
    2,100-job board — is what OOM'd the 512 MB Render instance.
    """
    import ijson

    if max_bytes is None:
        max_bytes = MAX_BOARD_BYTES
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES) as spool:
        async with client.stream("GET", url, timeout=30) as resp:
            resp.raise_for_status()
            received = 0
            async for chunk in resp.aiter_bytes():
                received += len(chunk)
                if received > max_bytes:
                    raise BoardTooLarge(slug, max_bytes)
                spool.write(chunk)
        spool.seek(0)
        for item in ijson.items(spool, prefix):
            yield item


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
