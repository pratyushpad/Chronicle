"""One-off backfill: populate Job.department_raw and normalize Job.department.

Before this pass, `department` held the raw ATS string verbatim (the fragile cleanup
lived in the frontend, which leaked internal org names like "Square Outside"). This
copies the original into `department_raw` (preserved untouched for retuning) and
overwrites `department` with the controlled-vocab category from normalize_department().

Idempotent: uses department_raw as the source of truth once populated, so re-running
after a normalize_department() tweak re-derives cleanly without losing the original.

Run from the api/ directory:  python -m app.ingest.backfill_departments
Requires the department_raw column (alembic upgrade head first).
"""
import logging

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402 — after dotenv

from app.db import get_session  # noqa: E402 — after dotenv (db reads DATABASE_URL at import)
from app.models import Job  # noqa: E402
from .normalize import normalize_department  # noqa: E402

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
            # Preserve the original once; department_raw is the source of truth thereafter.
            if job.department_raw is None:
                job.department_raw = job.department
            new_dept = normalize_department(job.department_raw)
            if new_dept != job.department:
                job.department = new_dept
                updated += 1
            if i % _BATCH == 0:
                session.commit()
                log.info("  ...processed %d/%d (%d updated)", i, total, updated)
        session.commit()
        log.info("Backfill complete: %d/%d rows re-normalized.", updated, total)
    finally:
        session.close()


if __name__ == "__main__":
    main()
