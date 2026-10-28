import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

from app.dbguard import sqlalchemy_url


def _connect_args() -> dict:
    """Bound how long a request can wait to CONNECT to Postgres.

    Without this, a frozen or slow database hung every request for as long as it was down,
    and once the threadpool filled even /health stopped answering (local drill, Oct 2026).
    connect_timeout is plain libpq and works everywhere, including Neon's "-pooler" hosts.

    There is deliberately no global statement_timeout: ingest, admin and backfill jobs run
    long statements on purpose. The per-request cap is applied by get_request_session().
    """
    return {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_S", "5"))}


def _statement_timeout_ms() -> int:
    return int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "15000"))

engine = create_engine(
    sqlalchemy_url(os.environ["DATABASE_URL"]),
    pool_pre_ping=True,      # drop dead Neon connections before use
    pool_size=10,            # base connections kept open on this (long-running) Render process
    max_overflow=20,         # burst headroom under prefetch fan-out
    pool_recycle=1800,       # recycle every 30 min, under Neon's idle limit
    pool_timeout=10,         # fail fast (then 503) instead of queueing 30 s when the pool is stuck
    connect_args=_connect_args(),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    return SessionLocal()


def get_request_session() -> Session:
    """Session for public request handlers: every transaction starts with
    SET LOCAL statement_timeout, so a runaway query is cut off at 15 s.

    SET LOCAL is a plain statement, so it works through Neon's PgBouncer pooler (a startup
    option would not), and it is scoped to the transaction, so the pooled connection goes
    back to the pool clean. The hook re-applies it after a commit starts a new transaction.
    Jobs and scripts keep using get_session(), which has no statement timeout.
    """
    session = SessionLocal()
    ms = _statement_timeout_ms()
    if ms > 0:
        @event.listens_for(session, "after_begin")
        def _set_timeout(_session, _transaction, connection):
            connection.execute(text(f"SET LOCAL statement_timeout = '{ms}ms'"))
    return session
