"""The one-shot refresh (GitHub Actions) must not start while another run is in flight,
the same rule POST /admin/ingest applies, so the two paths never overlap."""
import asyncio
from unittest.mock import MagicMock

from app.ingest import schedule


def _session(open_row):
    session = MagicMock()
    session.execute.return_value.first.return_value = open_row
    return session


def _wire(monkeypatch, open_row, calls):
    async def fake_run_ingest(session, **kwargs):
        calls.append("ingest")
        return MagicMock(id=159, finished_at=None)

    monkeypatch.setattr(schedule, "get_session", lambda: _session(open_row))
    monkeypatch.setattr(schedule, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(schedule, "_refresh_embeddings", lambda: calls.append("embed"))


def test_once_skips_while_another_run_is_open(monkeypatch):
    calls = []
    _wire(monkeypatch, (158,), calls)
    asyncio.run(schedule._once())
    assert calls == []


def test_once_refreshes_then_embeds_when_nothing_is_open(monkeypatch):
    calls = []
    _wire(monkeypatch, None, calls)
    asyncio.run(schedule._once())
    assert calls == ["ingest", "embed"]
