"""Keep maintenance tooling (alembic, backfill scripts) off production by accident.

Neon is production, and a migration or backfill run with the wrong DATABASE_URL in the
environment would hit it. These tools therefore refuse any host that isn't local unless
CHRONICLE_ALLOW_REMOTE_DB=1 is set — i.e. a production run has to be deliberate, e.g.
after taking a Neon backup branch:

    CHRONICLE_ALLOW_REMOTE_DB=1 DATABASE_URL=<neon> python -m alembic upgrade head

The running API is NOT guarded (Render must reach Neon).
"""
import os
import sys
from urllib.parse import urlparse

# "db" is the docker-compose service name.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})
ALLOW_ENV = "CHRONICLE_ALLOW_REMOTE_DB"


def db_host(url: str | None) -> str | None:
    """Hostname of a SQLAlchemy/libpq URL (driver suffix like +psycopg2 tolerated)."""
    if not url or "://" not in url:
        return None
    return urlparse("postgresql://" + url.split("://", 1)[1]).hostname


def assert_local_or_allowed(url: str | None, what: str) -> None:
    host = db_host(url)
    if host in LOCAL_HOSTS or os.environ.get(ALLOW_ENV) == "1":
        return
    sys.exit(
        f"Refusing to run {what} against non-local database host {host!r}.\n"
        f"If this is deliberate (e.g. applying a migration to Neon after taking a backup "
        f"branch), re-run with {ALLOW_ENV}=1."
    )
