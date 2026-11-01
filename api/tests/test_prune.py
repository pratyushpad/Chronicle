"""prune_stale_jobs must bound storage without ever deleting a job a user has on their
tracker (applications FK has no cascade — a tracked job blocking the old bulk DELETE
crashed the whole prune, so nothing was ever pruned again). Interaction telemetry is
disposable and must be dropped with the job, not immortalize it.

Postgres only (TEST_DATABASE_URL); skips without one. Hermetic: runs inside one outer
transaction that is rolled back — prune's internal commit is neutered to a flush.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.prune import prune_stale_jobs
from app.models import (
    Application, AppStatus, ATSSource, Company, Interaction,
    InteractionEvent, InteractionSurface, Job, User,
)



def _mk_job(company_id: int, sid: str, active: bool, last_seen: datetime) -> Job:
    return Job(
        company_id=company_id, source=ATSSource.greenhouse, source_job_id=sid,
        title=f"Role {sid}", title_normalized=f"role {sid}", apply_url="https://x",
        dedup_key=f"dk-{sid}", first_seen_at=last_seen, last_seen_at=last_seen,
        is_active=active,
    )


def test_prune_spares_tracked_jobs_and_drops_stale_telemetry(pg_engine):
    eng = pg_engine
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


# ── closed-role prune (PRUNE_INACTIVE_DAYS, closed_at clock, any-FK protection) ──────────

from contextlib import contextmanager  # noqa: E402

from sqlalchemy import text  # noqa: E402

from app.ingest.prune import prune_closed_jobs  # noqa: E402


@contextmanager
def _hermetic(eng):
    with eng.connect() as conn:
        outer = conn.begin()
        try:
            session = Session(bind=conn)
            session.commit = session.flush
            yield session
        finally:
            outer.rollback()


def _closed(co_id, sid, days_ago, **kw):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    job = _mk_job(co_id, sid, False, when)
    job.closed_at = when
    job.description_text = "x" * 4000
    for k, v in kw.items():
        setattr(job, k, v)
    return job


def _seed(session):
    co = Company(name="PruneCo2", ats=ATSSource.greenhouse, slug="prune-co-2", active=False)
    user = User(auth_provider="google", auth_provider_id="prune-2", email="prune2@test.local")
    session.add_all([co, user])
    session.flush()
    jobs = {
        "old_free": _closed(co.id, "old-free", 20),
        "old_applied": _closed(co.id, "old-applied", 20),
        "old_clicked": _closed(co.id, "old-clicked", 20),
        "old_impressed": _closed(co.id, "old-impressed", 20),
        "old_pinned": _closed(co.id, "old-pinned", 20),     # FK from a table found at run time
        "recent_closed": _closed(co.id, "recent-closed", 3),
        "live": _mk_job(co.id, "live", True, datetime.now(timezone.utc)),
        # closed before closed_at existed: falls back to last_seen_at
        "legacy_old": _mk_job(co.id, "legacy-old", False, datetime.now(timezone.utc) - timedelta(days=40)),
    }
    session.add_all(jobs.values())
    session.flush()
    session.add(Application(user_id=user.id, job_id=jobs["old_applied"].id, status=AppStatus.saved))
    session.add_all([
        Interaction(user_id=user.id, job_id=jobs["old_clicked"].id,
                    event=InteractionEvent.click, surface=InteractionSurface.feed),
        Interaction(user_id=user.id, job_id=jobs["old_impressed"].id,
                    event=InteractionEvent.impression, surface=InteractionSurface.feed),
    ])
    session.execute(text("CREATE TABLE zz_pins (job_id integer REFERENCES jobs(id))"))
    session.execute(text("INSERT INTO zz_pins VALUES (:j)"), {"j": jobs["old_pinned"].id})
    session.flush()
    return co, jobs


def _remaining(session, co):
    return set(session.execute(select(Job.source_job_id).where(Job.company_id == co.id)).scalars())


def test_dry_run_changes_nothing_and_reports(pg_engine):
    with _hermetic(pg_engine) as session:
        co, jobs = _seed(session)
        before = _remaining(session, co)
        res = prune_closed_jobs(session, days=14, dry_run=True)
        assert _remaining(session, co) == before
        desc = session.execute(select(Job.description_text).where(Job.id == jobs["old_free"].id)).scalar_one()
        assert desc is not None  # dry run must not clear payloads either
        assert res.dry_run and res.deleted_rows >= 2 and res.deleted_bytes > 0
        assert "DRY RUN" in res.summary()


def test_apply_deletes_only_unreferenced_closed_roles(pg_engine):
    with _hermetic(pg_engine) as session:
        co, jobs = _seed(session)
        res = prune_closed_jobs(session, days=14, dry_run=False, batch_size=1)  # batches of one
        assert _remaining(session, co) == {
            "old-applied", "old-clicked", "old-pinned", "recent-closed", "live",
        }
        assert res.deleted_rows >= 3 and res.deleted_bytes > 0 and res.freed_bytes >= res.deleted_bytes
        # impression telemetry went with its job; the click row protects its job
        kinds = set(session.execute(text("SELECT event::text FROM interactions")).scalars())
        assert "impression" not in kinds and "click" in kinds
        again = prune_closed_jobs(session, days=14, dry_run=False)
        assert again.deleted_rows == 0  # idempotent


def test_days_threshold_is_honoured(pg_engine):
    with _hermetic(pg_engine) as session:
        co, _ = _seed(session)
        prune_closed_jobs(session, days=2, dry_run=False)
        assert "recent-closed" not in _remaining(session, co)  # closed 3 days ago > 2
        assert "live" in _remaining(session, co)


def test_closed_roles_lose_description_and_embedding_but_keep_the_row(pg_engine):
    with _hermetic(pg_engine) as session:
        co, jobs = _seed(session)
        jobs["old_applied"].embedding = [0.1] * 384
        session.flush()
        res = prune_closed_jobs(session, days=14, dry_run=False)
        row = session.execute(
            select(Job.description_text, Job.embedding).where(Job.id == jobs["old_applied"].id)
        ).one()
        assert row.description_text is None and row.embedding is None
        assert res.cleared_rows >= 1 and res.cleared_bytes >= 1536  # the 384-float vector alone
