import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncIterator, Protocol

if TYPE_CHECKING:
    import httpx

    from ..pay import Pay

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
    # When the role was FIRST published (ISO or epoch-ms string); None when the ATS doesn't
    # say. Never a last-modified time: Greenhouse's updated_at moves on any edit (Anduril
    # bulk-touched 2,244 of 2,374 jobs in one day), which floated old roles to the top.
    posted_at: str | None
    remote: bool | None
    # Last-modified time. Drives ONLY the pre-2026 staleness cutoff, so switching
    # posted_at to first-published doesn't silently drop still-open evergreen roles.
    updated_at: str | None = None
    # Secondary department signals (Greenhouse metadata "Job Group"…, Ashby team, Lever
    # categories.department) — consulted only when the primary department is a program
    # label like "Internships" or maps to nothing.
    department_hints: list[str] = field(default_factory=list)
    # Structured pay from the ATS itself (beats anything parsed from the text).
    pay: "Pay | None" = None


class ATSAdapter(Protocol):
    source: str

    def fetch(self, slug: str, client: "httpx.AsyncClient") -> AsyncIterator[RawJob]:
        """Stream the open jobs for a board slug, one at a time. Raises on hard failure.

        Implementations are async generators, so nothing is raised (and no request is
        made) until the caller starts consuming. Because iter_board_json finishes the
        whole network download before its first yield, a consumer that holds a DB
        transaction open across this iteration never blocks on the network mid-txn.
        """
        ...
