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
from urllib.parse import parse_qs, urlparse

# "db" is the docker-compose service name.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db"})
ALLOW_ENV = "CHRONICLE_ALLOW_REMOTE_DB"


def db_host(url: str | None) -> str | None:
    """Hostname of a SQLAlchemy/libpq URL (driver suffix like +psycopg2 tolerated)."""
    if not url or "://" not in url:
        return None
    return urlparse("postgresql://" + url.split("://", 1)[1]).hostname


def db_hosts(url: str | None) -> set[str]:
    """Every host the URL would connect to: the host in the netloc plus any `host=` query
    parameter, which libpq honors (so `...@localhost/db?host=<neon>` reaches Neon)."""
    if not url or "://" not in url:
        return set()
    parsed = urlparse("postgresql://" + url.split("://", 1)[1])
    hosts = {parsed.hostname} if parsed.hostname else set()
    for value in parse_qs(parsed.query).get("host", []):
        hosts.update(h.strip().lower() for h in value.split(",") if h.strip())
    return hosts


def _is_local(host: str) -> bool:
    return host in LOCAL_HOSTS or host.startswith("/")  # "/..." is a unix-socket directory


def sqlalchemy_url(url: str) -> str:
    """Pin the installed psycopg2 driver on a driver-less URL. SQLAlchemy 2.1 maps a bare
    postgresql:// to psycopg (v3), which isn't installed, so a connection string pasted
    from the Neon console failed with ModuleNotFoundError."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def assert_local_or_allowed(url: str | None, what: str) -> None:
    hosts = db_hosts(url)
    if (hosts and all(_is_local(h) for h in hosts)) or os.environ.get(ALLOW_ENV) == "1":
        return
    remote = ", ".join(repr(h) for h in sorted(h for h in hosts if not _is_local(h))) or "None"
    sys.exit(
        f"Refusing to run {what} against non-local database host {remote}.\n"
        f"If this is deliberate (e.g. applying a migration to Neon after taking a backup "
        f"branch), re-run with {ALLOW_ENV}=1."
    )
