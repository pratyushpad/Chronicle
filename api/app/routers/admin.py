import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import IngestRun

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# A run whose row is still open after this long is treated as crashed, so a new run may
# start. Normal runs finish well inside this window.
_LOCK_STALE_AFTER = timedelta(hours=2)


def require_ingest_secret(x_ingest_secret: str | None = Header(None)) -> None:
    """Guard the ingest trigger with a dedicated shared secret (the caller is a machine —
    GitHub Actions / cron — not a user identity). 500 if the secret is unset (never run
    unauthenticated), 401 if the header is missing or wrong. Constant-time compare."""
    secret = os.environ.get("INGEST_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="INGEST_SECRET not configured")
    if not x_ingest_secret or not hmac.compare_digest(x_ingest_secret, secret):
        raise HTTPException(status_code=401, detail="Not authorized")


def _db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


async def _run_ingest_bg(budget_seconds: int | None) -> None:
    """Background worker: its own session (the request session is long gone by now)."""
    from app.ingest.runner import run_ingest

    session = get_session()
    try:
        await run_ingest(session, budget_seconds=budget_seconds)
    except Exception:
        log.exception("background ingest run failed")
    finally:
        session.close()


@router.post("/ingest", status_code=202)
def trigger_ingest(
    background_tasks: BackgroundTasks,
    # Default budget so a caller that omits the param (e.g. the cron-job.org backup
    # trigger) can never start an unbounded run — unbudgeted runs OOM the 512 MB box.
    budget_seconds: int = Query(240, ge=30, le=3600),
    _: None = Depends(require_ingest_secret),
    session: Session = Depends(_db),
):
    """Kick off an incremental ingest in the background and return immediately (202) so the
    caller never blocks on a long run or hits a request timeout. A DB run-lock refuses to
    start if a run is already in progress; combined with the upsert's idempotency, an
    accidental double-fire (e.g. GitHub + cron-job.org both firing) is harmless.

    Optional budget_seconds bounds wall-clock time so a full 1000+ board run fits a Render
    free-tier window and continues (stalest-first) on the next invocation.
    """
    cutoff = datetime.now(tz=timezone.utc) - _LOCK_STALE_AFTER
    open_run = session.execute(
        select(IngestRun)
        .where(IngestRun.finished_at.is_(None), IngestRun.started_at >= cutoff)
        .order_by(IngestRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if open_run is not None:
        raise HTTPException(
            status_code=409, detail=f"ingest run {open_run.id} already in progress"
        )

    background_tasks.add_task(_run_ingest_bg, budget_seconds)
    return {"status": "started", "budget_seconds": budget_seconds}
