"""Standalone prune of long-closed roles (see app/ingest/prune.py).

    python -m scripts.prune_jobs               # dry run (default): counts and estimates only
    python -m scripts.prune_jobs --apply       # clear payloads and hard-delete, in batches
    python -m scripts.prune_jobs --days 30 --batch-size 200

PRUNE_INACTIVE_DAYS (default 14) sets the age. Refuses a non-local database unless
CHRONICLE_ALLOW_REMOTE_DB=1 (app.dbguard), like the other maintenance scripts.
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (the default)")
    mode.add_argument("--apply", action="store_true", help="actually delete")
    ap.add_argument("--days", type=int, default=None, help="override PRUNE_INACTIVE_DAYS")
    ap.add_argument("--batch-size", type=int, default=500)
    args = ap.parse_args(argv)

    from app.dbguard import assert_local_or_allowed

    assert_local_or_allowed(os.environ.get("DATABASE_URL"), "the job prune")
    from app.db import get_session
    from app.ingest.prune import prune_closed_jobs

    session = get_session()
    try:
        result = prune_closed_jobs(
            session, days=args.days, dry_run=not args.apply, batch_size=args.batch_size
        )
    finally:
        session.close()
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
