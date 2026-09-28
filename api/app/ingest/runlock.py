"""One ingest run at a time, shared by POST /admin/ingest (Render) and
`python -m app.ingest.schedule --once` (GitHub Actions), so the two never overlap."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import IngestRun

log = logging.getLogger(__name__)

# An unfinished run younger than this is in flight; an older one is a dead worker's.
LOCK_STALE_AFTER = timedelta(hours=2)


def open_run(session: Session) -> IngestRun | None:
    """The run still in flight, if any."""
    cutoff = datetime.now(tz=timezone.utc) - LOCK_STALE_AFTER
    return session.execute(
        select(IngestRun)
        .where(IngestRun.finished_at.is_(None), IngestRun.started_at >= cutoff)
        .order_by(IngestRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def close_crashed_run(exc: BaseException) -> None:
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
