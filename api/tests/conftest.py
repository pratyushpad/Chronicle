import asyncio
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock

import pytest

# app.db builds its engine from DATABASE_URL at import time; tests never
# connect, so any well-formed DSN lets router modules import in CI.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")

FIXTURES = Path(__file__).parent / "fixtures"


def _test_pg_engine():
    """Engine for database-backed tests: TEST_DATABASE_URL (a migrated, local, disposable
    Postgres — CI provides one), or None when unset/unreachable so those tests skip.
    Never DATABASE_URL: that is the app's database, and tests must not touch it."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    if "postgres" not in url:
        return None
    from app.dbguard import LOCAL_HOSTS, db_hosts

    hosts = db_hosts(url)
    if not hosts or not hosts <= LOCAL_HOSTS:
        raise RuntimeError(f"TEST_DATABASE_URL must point at a local database, got hosts {sorted(hosts)!r}")
    from sqlalchemy import create_engine, text

    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception:
        return None


@pytest.fixture(scope="session")
def pg_engine():
    eng = _test_pg_engine()
    if eng is None:
        pytest.skip("no TEST_DATABASE_URL Postgres reachable")
    return eng


class ResultSet(NamedTuple):
    """What one statement sent back over the wire: its SQL (and bind parameters, so a test
    can EXPLAIN exactly what ran), the column names of its result, and how many rows it
    carried."""

    sql: str
    columns: tuple[str, ...]
    rows: int
    params: object = None


# The ORM de-duplicates repeated labels in one SELECT (id, id_1, ...); strip that so a
# column is matched by the name the model gives it.
_LABEL_SUFFIX = re.compile(r"_\d+$")


class SelectLog(list):
    """The result sets the database returned while a request ran (see record_selects)."""

    def with_column(self, *names: str) -> list[ResultSet]:
        """The result sets that returned a column called one of `names`."""
        return [
            rs for rs in self
            if any(_LABEL_SUFFIX.sub("", col) in names for col in rs.columns)
        ]

    def assert_never_returned(self, *names: str) -> None:
        hits = self.with_column(*names)
        assert not hits, (
            f"{', '.join(names)} came back over the wire from:\n"
            + "\n".join(f"  [{rs.rows} rows] {' '.join(rs.sql.split())[:240]}" for rs in hits)
        )


@pytest.fixture
def record_selects(pg_engine):
    """Context manager that records, for every statement that returns rows while it is
    open, the column names and row count of the result set (cursor.description and
    cursor.rowcount, via the engine's after_cursor_execute). That is what Neon bills as
    egress, so a test can assert that one API request never pulls a column or a row
    volume it does not use.

        with record_selects() as log:
            client.get("/jobs")
        log.assert_never_returned("description_text", "embedding")
    """
    from sqlalchemy import event

    @contextmanager
    def _record():
        log = SelectLog()

        def _after(conn, cursor, statement, parameters, context, executemany):
            if cursor.description is not None:
                log.append(ResultSet(statement, tuple(d[0] for d in cursor.description), cursor.rowcount, parameters))

        event.listen(pg_engine, "after_cursor_execute", _after)
        try:
            yield log
        finally:
            event.remove(pg_engine, "after_cursor_execute", _after)

    return _record


@pytest.fixture
def greenhouse_response():
    return json.loads((FIXTURES / "greenhouse_stripe.json").read_text())


@pytest.fixture
def lever_response():
    return json.loads((FIXTURES / "lever_sample.json").read_text())


@pytest.fixture
def ashby_response():
    return json.loads((FIXTURES / "ashby_sample.json").read_text())


@pytest.fixture
def mock_client():
    """Fake httpx.AsyncClient. Tests set response.json.return_value; both the
    legacy client.get path and the streaming client.stream path (adapters read
    aiter_bytes) serve that same payload."""
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    async def _aiter_bytes():
        yield json.dumps(response.json.return_value).encode()

    response.aiter_bytes = _aiter_bytes
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)
    client.stream = MagicMock(return_value=stream_cm)
    return client, response


class _IngestRunStub:
    """Stand-in for the IngestRun ORM row.

    The real model's counter defaults are applied at flush time, so an un-flushed
    instance has None where run_ingest does `+= 1`. Tests never touch a DB, hence
    a stub that starts at the post-flush state.
    """

    def __init__(self, **kwargs):
        self.companies_total = 0
        self.companies_ok = 0
        self.companies_failed = 0
        self.jobs_seen = 0
        self.jobs_new = 0
        self.jobs_closed = 0
        self.failures = []
        self.finished_at = None
        self.__dict__.update(kwargs)


@pytest.fixture
def drive_run_ingest(monkeypatch):
    """Run runner.run_ingest() end-to-end against stubbed boards, no DB or network.

    Post-run side effects (prune, alerts, meta-cache invalidation) are neutralized by
    default; pass `alerts=` to override that one — e.g. with a raiser, to prove the
    steps after it still happen. Returns (run, session).
    """
    from app.ingest import alerts as alerts_mod
    from app.ingest import prune as prune_mod
    from app.ingest import runner
    from app.routers import jobs as jobs_router

    def drive(companies, adapters, alerts=None, budget_seconds=None):
        async def _noop_alerts(session, run_start):
            return None

        # Collapse the runner's 2s retry backoff so failure-path tests stay fast.
        # Keep asyncio.sleep's full signature (result= kwarg) — code under test may
        # use it, and a stub that drops it would fail in a way the runner never does.
        real_sleep = asyncio.sleep
        monkeypatch.setattr(asyncio, "sleep", lambda _s, result=None: real_sleep(0, result))

        monkeypatch.setattr(runner, "IngestRun", _IngestRunStub)
        monkeypatch.setattr(
            runner, "load_active_companies", lambda s, stale_first=False: list(companies)
        )
        monkeypatch.setattr(runner, "_ADAPTERS", adapters)
        monkeypatch.setattr(prune_mod, "prune_stale_jobs", lambda session: None)
        monkeypatch.setattr(alerts_mod, "run_alerts", alerts or _noop_alerts)
        monkeypatch.setattr(jobs_router, "invalidate_meta_cache", lambda: None)

        session = MagicMock()
        session.execute.return_value.scalar_one.return_value = True
        run = asyncio.run(runner.run_ingest(session, budget_seconds=budget_seconds))
        return run, session

    return drive


@pytest.fixture
def fake_company():
    """Minimal stand-in for a Company row as the runner reads it."""
    from app.models import ATSSource

    def _make(slug="acme", name="Acme", company_id=7, ats=ATSSource.greenhouse):
        return SimpleNamespace(id=company_id, name=name, slug=slug, ats=ats)

    return _make
