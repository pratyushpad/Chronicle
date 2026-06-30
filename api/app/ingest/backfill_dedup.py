"""One-off backfill: recompute every Job.dedup_key with the location-independent
key so cross-posted city duplicates collapse to one logical role.

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
from .normalize import dedup_title, normalize_title  # noqa: E402

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
            t_norm = job.title_normalized or normalize_title(job.title)
            new_key = make_dedup_key(job.company_id, dedup_title(t_norm, job.location_normalized))
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
