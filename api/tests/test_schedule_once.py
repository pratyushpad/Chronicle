"""The one-shot refresh (GitHub Actions) must not start while another run is in flight
(the same rule POST /admin/ingest applies), passes its budget through, and stamps a crash
on the run row instead of leaving it open."""
import asyncio
from unittest.mock import MagicMock

import pytest

from app.ingest import runlock, schedule


def _wire(monkeypatch, running, calls, run_ingest=None):
    async def fake_run_ingest(session, budget_seconds=None):
        calls.append(("ingest", budget_seconds))
        return MagicMock(id=159, finished_at=None)

    monkeypatch.setattr(schedule, "get_session", lambda: MagicMock())
    monkeypatch.setattr(runlock, "open_run", lambda session: running)
    monkeypatch.setattr(runlock, "close_crashed_run", lambda exc: calls.append(("crashed", str(exc))))
    monkeypatch.setattr(schedule, "run_ingest", run_ingest or fake_run_ingest)
    monkeypatch.setattr(schedule, "_refresh_embeddings", lambda: calls.append(("embed",)))


def test_once_skips_while_another_run_is_open(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _wire(monkeypatch, MagicMock(id=158), calls)
    asyncio.run(schedule._once())
    assert calls == []
    assert "::warning::ingest run 158 is still in progress" in capsys.readouterr().out


def test_once_refreshes_with_its_budget_then_embeds(monkeypatch):
    calls = []
    _wire(monkeypatch, None, calls)
    asyncio.run(schedule._once(4200))
    assert calls == [("ingest", 4200), ("embed",)]


def test_a_crash_is_stamped_on_the_run_row(monkeypatch):
    calls = []

    async def boom(session, budget_seconds=None):
        raise RuntimeError("board fetch exploded")

    _wire(monkeypatch, None, calls, run_ingest=boom)
    with pytest.raises(RuntimeError):
        asyncio.run(schedule._once())
    assert calls == [("crashed", "board fetch exploded")]
