import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.models import Application, Interaction, Job

log = logging.getLogger(__name__)

# Roles soft-closed and unseen for this long are hard-deleted. Neon's free tier is ~0.5GB
# and 1000+ companies of history would blow past it, so only active + recently-closed
# roles stay hot. Raising this needs a paid tier (documented in the README).
STALE_AFTER_DAYS = 30


def prune_stale_jobs(session: Session, older_than_days: int = STALE_AFTER_DAYS) -> int:
    """Hard-delete long-closed roles (is_active=False AND last_seen_at older than the
    cutoff) to bound Neon storage. Active and recently-closed roles are untouched; the
    row's embedding is deleted with it.

    A role on someone's tracker is never deleted, no matter how stale — the applications
    FK has no cascade precisely so a user's history can't be vacuumed away. Interaction
    telemetry is the opposite: it must not immortalize a dead posting, so those rows are
    dropped with the job. Idempotent — re-running removes nothing new."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=older_than_days)
    stale_untracked = select(Job.id).where(
        Job.is_active == False,  # noqa: E712
        Job.last_seen_at < cutoff,
        ~exists(select(Application.id).where(Application.job_id == Job.id)),
    )
    session.execute(
        delete(Interaction).where(Interaction.job_id.in_(stale_untracked))
    )
    result = session.execute(delete(Job).where(Job.id.in_(stale_untracked)))
    session.commit()
    n = result.rowcount or 0
    if n:
        log.info("pruned %d stale inactive jobs (closed & unseen > %dd)", n, older_than_days)
    return n
