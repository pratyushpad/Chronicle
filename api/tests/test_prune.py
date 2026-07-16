"""prune_stale_jobs must bound storage without ever deleting a job a user has on their
tracker (applications FK has no cascade — a tracked job blocking the old bulk DELETE
crashed the whole prune, so nothing was ever pruned again). Interaction telemetry is
disposable and must be dropped with the job, not immortalize it.

Postgres only; skips where no reachable Postgres. Hermetic: runs inside one outer
transaction that is rolled back — prune's internal commit is neutered to a flush.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.ingest.prune import prune_stale_jobs
from app.models import (
    Application, AppStatus, ATSSource, Company, Interaction,
    InteractionEvent, InteractionSurface, Job, User,
)


def _pg_engine():
    url = os.environ.get("DATABASE_URL", "")
    if "postgres" not in url:
        return None
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception:
        return None


def _mk_job(company_id: int, sid: str, active: bool, last_seen: datetime) -> Job:
    return Job(
        company_id=company_id, source=ATSSource.greenhouse, source_job_id=sid,
        title=f"Role {sid}", title_normalized=f"role {sid}", apply_url="https://x",
        dedup_key=f"dk-{sid}", first_seen_at=last_seen, last_seen_at=last_seen,
        is_active=active,
    )


@pytest.mark.skipif(_pg_engine() is None, reason="no reachable Postgres for prune test")
def test_prune_spares_tracked_jobs_and_drops_stale_telemetry():
    eng = _pg_engine()
    with eng.connect() as conn:
        outer = conn.begin()
        try:
            session = Session(bind=conn)
            session.commit = session.flush  # hermetic: everything rolls back below

            old = datetime.now(timezone.utc) - timedelta(days=45)
            fresh = datetime.now(timezone.utc) - timedelta(days=2)
            co = Company(name="PruneCo", ats=ATSSource.greenhouse, slug="prune-co-test", active=False)
            user = User(auth_provider="google", auth_provider_id="prune-test", email="prune@test.local")
            session.add_all([co, user])
            session.flush()

            stale_free = _mk_job(co.id, "stale-free", False, old)      # prunable
            stale_tracked = _mk_job(co.id, "stale-tracked", False, old)  # on a tracker → kept
            stale_recent = _mk_job(co.id, "stale-recent", False, fresh)  # too recent → kept
            live = _mk_job(co.id, "live", True, old)                     # active → kept
            session.add_all([stale_free, stale_tracked, stale_recent, live])
            session.flush()

            session.add(Application(user_id=user.id, job_id=stale_tracked.id, status=AppStatus.saved))
            session.add_all([
                Interaction(user_id=user.id, job_id=stale_free.id,
                            event=InteractionEvent.impression, surface=InteractionSurface.feed),
                Interaction(user_id=user.id, job_id=live.id,
                            event=InteractionEvent.click, surface=InteractionSurface.search),
            ])
            session.flush()

            pruned = prune_stale_jobs(session)
            assert pruned == 1

            remaining = set(session.execute(
                select(Job.source_job_id).where(Job.company_id == co.id)
            ).scalars())
            assert remaining == {"stale-tracked", "stale-recent", "live"}

            events = set(session.execute(
                select(Interaction.job_id).where(Interaction.user_id == user.id)
            ).scalars())
            assert events == {live.id}  # telemetry for the pruned job went with it
        finally:
            outer.rollback()
