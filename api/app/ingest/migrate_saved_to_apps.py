"""One-off migration: fold the legacy `saved_jobs` table into `applications` so
bookmarks and the tracker share one store. A saved job becomes an
`Application(status='saved')`, preserving its original `saved_at` timestamp.

Run from the api/ directory:  python -m app.ingest.migrate_saved_to_apps
Idempotent — skips rows that already have an application, and no-ops if the
`saved_jobs` table is already gone. Self-contained (raw SQL read) so it does not
depend on the SavedJob ORM model, which has been removed.

⚠ PROD: must be run against Neon explicitly at deploy time
(DATABASE_URL='<neon_pooled_url>' python -m app.ingest.migrate_saved_to_apps),
then it drops the saved_jobs table. Snapshot Neon first.
"""
import logging

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, text  # noqa: E402 — after dotenv

from app.db import get_session  # noqa: E402 — db reads DATABASE_URL at import
from app.models import Application, ApplicationEvent, AppStatus  # noqa: E402

log = logging.getLogger(__name__)


def main(drop_table: bool = True) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = get_session()
    migrated = 0
    skipped = 0
    try:
        exists = session.execute(text("SELECT to_regclass('public.saved_jobs')")).scalar()
        if not exists:
            log.info("No saved_jobs table — nothing to migrate.")
            return

        saved_rows = session.execute(
            text("SELECT user_id, job_id, saved_at FROM saved_jobs")
        ).all()
        existing = {
            (a.user_id, a.job_id)
            for a in session.execute(select(Application.user_id, Application.job_id)).all()
        }
        for user_id, job_id, saved_at in saved_rows:
            if (user_id, job_id) in existing:
                skipped += 1
                continue
            app = Application(
                user_id=user_id,
                job_id=job_id,
                status=AppStatus.saved,
                created_at=saved_at,
                updated_at=saved_at,
            )
            session.add(app)
            session.flush()
            session.add(ApplicationEvent(
                application_id=app.id, from_status=None, to_status="saved", at=saved_at,
            ))
            existing.add((user_id, job_id))
            migrated += 1
        session.commit()
        log.info("Migrated %d saved_jobs → applications (%d already had an application).", migrated, skipped)

        if drop_table:
            session.execute(text("DROP TABLE IF EXISTS saved_jobs"))
            session.commit()
            log.info("Dropped saved_jobs table.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
