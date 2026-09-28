import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from app.db import get_session  # noqa: E402 — after dotenv
from .runner import run_ingest  # noqa: E402

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


async def _once(budget_seconds: int | None = None) -> None:
    """One refresh of every board (or as many as `budget_seconds` allows), then new
    embeddings. Refuses to start while another run is in flight (runlock), the same rule
    POST /admin/ingest applies, and stamps a crash on the run row instead of leaving it
    open (an open row blocks the Render trigger for two hours)."""
    from .runlock import close_crashed_run, open_run

    session = get_session()
    try:
        running = open_run(session)
        if running is not None:
            msg = f"ingest run {running.id} is still in progress; not starting another"
            log.warning(msg)
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::warning::{msg}")  # visible on the workflow run, not just the log
            return
        try:
            run = await run_ingest(session, budget_seconds=budget_seconds)  # alerts inside
        except BaseException as exc:
            close_crashed_run(exc)
            raise
        log.info("Run id=%d finished_at=%s", run.id, run.finished_at)
    finally:
        session.close()
    _refresh_embeddings()


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
    if "--once" in sys.argv:
        budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else None
        asyncio.run(_once(budget))
    else:
        asyncio.run(_loop())
