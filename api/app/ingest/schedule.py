import asyncio
import logging
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


async def _once() -> None:
    session = get_session()
    try:
        run = await run_ingest(session)  # alerts fire inside run_ingest
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
        asyncio.run(_once())
    else:
        asyncio.run(_loop())
