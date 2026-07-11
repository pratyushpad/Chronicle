import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Job

log = logging.getLogger(__name__)

# Roles soft-closed and unseen for this long are hard-deleted. Neon's free tier is ~0.5GB
# and 1000+ companies of history would blow past it, so only active + recently-closed
# roles stay hot. Raising this needs a paid tier (documented in the README).
STALE_AFTER_DAYS = 30


def prune_stale_jobs(session: Session, older_than_days: int = STALE_AFTER_DAYS) -> int:
    """Hard-delete long-closed roles (is_active=False AND last_seen_at older than the
    cutoff) to bound Neon storage. Active and recently-closed roles are untouched; the
    row's embedding is deleted with it. Idempotent — re-running removes nothing new."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=older_than_days)
    result = session.execute(
        delete(Job).where(Job.is_active == False, Job.last_seen_at < cutoff)  # noqa: E712
    )
    session.commit()
    n = result.rowcount or 0
    if n:
        log.info("pruned %d stale inactive jobs (closed & unseen > %dd)", n, older_than_days)
    return n
