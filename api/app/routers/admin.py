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


def _close_crashed_run(exc: BaseException) -> None:
    """Stamp finished_at on a run whose worker died, recording why.

    A run row left with finished_at NULL is indistinguishable from one still in flight,
    so four consecutive crashed runs looked identical to a healthy backlog and the real
    cause stayed invisible for days. Uses a fresh session on purpose: the run's own is
    typically dead by the time we get here (that is usually what killed it).
    """
    session = get_session()
    try:
        run = session.execute(
            select(IngestRun)
            .where(IngestRun.finished_at.is_(None))
            .order_by(IngestRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if run is None:
            return
        run.finished_at = datetime.now(tz=timezone.utc)
        run.failures = list(run.failures or []) + [
            {"company": None, "ats": None, "slug": None,
             "error": f"run crashed: {type(exc).__name__}: {exc}"[:500]}
        ]
        session.commit()
    except Exception:
        log.exception("could not stamp crashed ingest run")
    finally:
        try:
            session.close()
        except Exception:
            pass


async def _run_ingest_bg(budget_seconds: int | None) -> None:
    """Background worker: its own session (the request session is long gone by now)."""
    from app.ingest.runner import run_ingest

    session = get_session()
    try:
        await run_ingest(session, budget_seconds=budget_seconds)
    except Exception as exc:
        log.exception("background ingest run failed")
        _close_crashed_run(exc)
    finally:
        # close() rolls back, which itself raises if the connection is already gone —
        # that escaped this task and surfaced as an unhandled ASGI error.
        try:
            session.close()
        except Exception:
            log.warning("ingest session close failed; connection already dropped", exc_info=True)


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
