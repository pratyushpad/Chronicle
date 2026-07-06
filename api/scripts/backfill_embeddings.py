"""Backfill embeddings for the existing job corpus.

Resumable by construction (only touches embedding IS NULL rows) and
commits per 500-row page. Run from the api/ directory:

    python -m scripts.backfill_embeddings [--sleep 0.5] [--limit 5000]

Point DATABASE_URL at the target DB (local or Neon) explicitly.
"""
import argparse
import logging
import time

from dotenv import load_dotenv

load_dotenv()

from app.db import get_session  # noqa: E402
from app.ml.embed_jobs import embed_missing_jobs  # noqa: E402

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds to sleep between pages")
    parser.add_argument("--limit", type=int, default=None, help="stop after ~this many jobs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = get_session()
    try:
        total = 0
        while True:
            embedded = embed_missing_jobs(session, limit=500)
            total += embedded
            if embedded == 0 or (args.limit is not None and total >= args.limit):
                break
            if args.sleep:
                time.sleep(args.sleep)
        log.info("backfill complete: %d jobs embedded", total)
    finally:
        session.close()


if __name__ == "__main__":
    main()
