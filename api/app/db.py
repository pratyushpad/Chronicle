import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.dbguard import db_host, sqlalchemy_url


def _connect_args() -> dict:
    """Bound how long a request can wait on Postgres.

    Without these, a frozen or slow database hung every request for as long as it was down,
    and once the threadpool filled even /health stopped answering (local drill, Oct 2026).
    connect_timeout is plain libpq and works everywhere. statement_timeout is sent as a
    startup option, which Neon's PgBouncer pooler ("-pooler" hosts) rejects, so it is only
    added on direct connections; set it on the role in Neon for pooled URLs
    (ALTER ROLE ... SET statement_timeout).
    """
    args: dict = {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_S", "5"))}
    stmt_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "15000"))
    host = db_host(os.environ.get("DATABASE_URL")) or ""
    if stmt_ms > 0 and "-pooler" not in host:
        args["options"] = f"-c statement_timeout={stmt_ms}"
    return args

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
