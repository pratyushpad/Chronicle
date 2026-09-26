import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from app.db import get_session  # noqa: E402 — after dotenv
from .runner import RunInProgress, run_ingest  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _refresh_embeddings() -> None:
    """Nightly sweep: embed any jobs still missing vectors, then refresh
    every profile embedding (picks up new saves/applies)."""
    from app.ml.embed_jobs import embed_missing_jobs
    from app.ml.profile_embedding import refresh_all_profile_embeddings

    session = get_session()
    try:
        jobs = embed_missing_jobs(session)
        profiles = refresh_all_profile_embeddings(session)
        log.info("embedding sweep: %d jobs embedded, %d profiles refreshed", jobs, profiles)
    finally:
        session.close()
        # Same 512 MB-headroom rationale as run_ingest's release: this sweep runs in a
        # long-lived process (APScheduler nightly, or right after _once's run_ingest —
        # which would otherwise release only for this sweep to re-load and re-pin it).
        from app.ml.embedder import release_embedder

        release_embedder()


async def _once(budget_seconds: int | None = None) -> dict | None:
    """One ingest run, then the embedding sweep. Returns a small report, or None when
    another run holds the run lock (not an error: a double trigger is expected)."""
    session = get_session()
    try:
        try:
            run = await run_ingest(session, budget_seconds=budget_seconds)  # alerts fire inside
        except RunInProgress:
            log.info("another ingest run is in progress; nothing to do")
            return None
        log.info("Run id=%d finished_at=%s", run.id, run.finished_at)
        report = {
            "run_id": run.id,
            "seconds": round((run.finished_at - run.started_at).total_seconds()) if run.finished_at else None,
            "boards_total": run.companies_total, "boards_ok": run.companies_ok,
            "boards_failed": run.companies_failed, "jobs_seen": run.jobs_seen,
            "jobs_new": run.jobs_new, "jobs_closed": run.jobs_closed,
        }
    finally:
        session.close()
    _refresh_embeddings()
    return report


def _arg(flag: str) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv[:-1] else None


async def _loop() -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    async def _job():
        session = get_session()
        try:
            await run_ingest(session)
        finally:
            session.close()

    scheduler.add_job(_job, "interval", hours=48)
    scheduler.add_job(_refresh_embeddings, "cron", hour=9, minute=30)  # nightly, 09:30 UTC
    scheduler.start()
    log.info("Scheduler started — ingest every 48h, embedding sweep nightly")
    await asyncio.Event().wait()


if __name__ == "__main__":
    # --once [--budget SECONDS] [--report PATH]: one run (GitHub Actions / manual); writes a
    # JSON report for the workflow's budget summary when --report is given.
    if "--once" in sys.argv:
        budget = _arg("--budget")
        result = asyncio.run(_once(int(budget) if budget else None))
        if (path := _arg("--report")) is not None:
            import json

            with open(path, "w") as fh:
                json.dump(result or {"skipped": "another run in progress"}, fh)
    else:
        asyncio.run(_loop())
