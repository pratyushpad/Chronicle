"""runlock.open_run against real Postgres (TEST_DATABASE_URL; skips without): an unfinished
run younger than two hours is in flight; older or finished runs are not. Hermetic."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ingest.runlock import open_run
from app.models import IngestRun


def test_only_a_recent_unfinished_run_counts_as_open(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = Session(bind=conn)
            now = datetime.now(timezone.utc)
            session.add_all([
                IngestRun(started_at=now - timedelta(hours=3), failures=[]),  # dead worker
                IngestRun(started_at=now - timedelta(minutes=30), finished_at=now, failures=[]),
            ])
            session.flush()
            assert open_run(session) is None

            live = IngestRun(started_at=now - timedelta(minutes=5), failures=[])
            session.add(live)
            session.flush()
            assert open_run(session).id == live.id
        finally:
            outer.rollback()
