"""One-off backfill: recompute every Job.dedup_key.

Location-independent key so cross-posted city duplicates collapse to one logical role,
AND (as of the over-collapse fix) keyed off `keying_title`, which preserves the
distinguishing team qualifier — e.g. 'Staff Software Engineer (Data Platform)' vs
'(Money)' — so genuinely distinct reqs at one company no longer merge into one card.
Must key off raw `job.title` (not `job.title_normalized`, which already stripped the
qualifier).

Run from the api/ directory:  python -m app.ingest.backfill_dedup
Idempotent — safe to re-run. No schema change (dedup_key column already exists).
"""
import logging

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402 — after dotenv

from app.db import get_session  # noqa: E402 — after dotenv (db reads DATABASE_URL at import)
from app.models import Job  # noqa: E402
from .dedupe import make_dedup_key  # noqa: E402
from .normalize import dedup_title, keying_title  # noqa: E402

log = logging.getLogger(__name__)

_BATCH = 1000


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = get_session()
    updated = 0
    try:
        jobs = session.execute(select(Job)).scalars().all()
        total = len(jobs)
        for i, job in enumerate(jobs, 1):
            k_title = keying_title(job.title)
            new_key = make_dedup_key(job.company_id, dedup_title(k_title, job.location_normalized))
            if new_key != job.dedup_key:
                job.dedup_key = new_key
                updated += 1
            if i % _BATCH == 0:
                session.commit()
                log.info("  ...processed %d/%d (%d updated)", i, total, updated)
        session.commit()
        log.info("Backfill complete: %d/%d rows re-keyed.", updated, total)
    finally:
        session.close()


if __name__ == "__main__":
    main()
