import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# app.db builds its engine from DATABASE_URL at import time; tests never
# connect, so any well-formed DSN lets router modules import in CI.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")

FIXTURES = Path(__file__).parent / "fixtures"


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
