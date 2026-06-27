import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from app.db import get_session  # noqa: E402 — after dotenv
from .runner import run_ingest  # noqa: E402
from .alerts import run_alerts  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def _once() -> None:
    session = get_session()
    try:
        run = await run_ingest(session)
        log.info("Run id=%d finished_at=%s", run.id, run.finished_at)
        await run_alerts(session, run.started_at)
    finally:
        session.close()


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
    scheduler.start()
    log.info("Scheduler started — will run every 48h")
    await asyncio.Event().wait()


if __name__ == "__main__":
    if "--once" in sys.argv:
        asyncio.run(_once())
    else:
        asyncio.run(_loop())
