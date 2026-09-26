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
    from app.ingest.runner import RunInProgress, run_ingest

    session = get_session()
    try:
        await run_ingest(session, budget_seconds=budget_seconds)
    except RunInProgress:
        # Lost the race for the run slot (ux_ingest_runs_one_open): another run is open.
        log.info("ingest not started: another run holds the run lock")
    except Exception:
        # run_ingest has already closed its own run row (by id) before re-raising.
        log.exception("background ingest run failed")
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


# ── Production search benchmark ──────────────────────────────────────────────
# Runs on the Render box against Neon: the number that matters for users (the local
# docs/bench_results.md figures are from faster hardware). Protected by the ingest secret
# and capped, so it can't be used to load the database.
_BENCH_QUERIES = (
    "software engineer intern", "machine learning", "data science internship",
    "product manager new grad", "hardware engineer", "backend distributed systems",
    "frontend react", "security", "robotics", "quantitative research",
)


@router.post("/bench")
def bench_search(
    n: int = Query(20, ge=5, le=100),
    modes: str = Query("keyword,semantic,hybrid", pattern=r"^(keyword|semantic|hybrid)(,(keyword|semantic|hybrid))*$"),
    _: None = Depends(require_ingest_secret),
    session: Session = Depends(_db),
):
    """Time the real /jobs handler in-process (handler + database; no network) for each
    search mode, n queries each, and return p50/p95/max in milliseconds."""
    import inspect
    import statistics
    import time

    from app.routers.jobs import list_jobs

    # Call the handler as FastAPI would: every parameter at its declared default.
    defaults = {
        name: (p.default.default if hasattr(p.default, "default") else p.default)
        for name, p in inspect.signature(list_jobs).parameters.items()
        if name != "session"
    }
    out = {}
    try:
        for mode in modes.split(","):
            # Warm-up: the first semantic call loads the model (~2 s); keep it out of timing.
            list_jobs(**{**defaults, "q": _BENCH_QUERIES[0], "mode": mode}, session=session)
            session.rollback()
            times = []
            for i in range(n):
                q = _BENCH_QUERIES[i % len(_BENCH_QUERIES)]
                t0 = time.perf_counter()
                list_jobs(**{**defaults, "q": q, "mode": mode, "level": "intern"}, session=session)
                times.append((time.perf_counter() - t0) * 1000)
                session.rollback()  # never hold one read transaction open across the run
            times.sort()
            out[mode] = {
                "n": n,
                "p50_ms": round(statistics.median(times)),
                "p95_ms": round(times[max(0, int(len(times) * 0.95) - 1)]),
                "max_ms": round(times[-1]),
            }
    finally:
        # Hand the embedding model back: the 512 MB box can't keep it resident.
        from app.ml.embedder import release_embedder

        release_embedder()
    return {"measured_at": datetime.now(tz=timezone.utc).isoformat(), "results": out,
            "note": "In-process /jobs handler time (database + app), excluding network."}
