"""Daily refresh budget: a board whose downloaded payload is byte-identical to the last full
ingest is skipped (no normalization, no per-job upserts, no soft-close), and a changed or
never-hashed board is processed in full and stores its new hash."""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ingest import runner
from app.ingest.adapters.base import BoardDigest, RawJob, board_digest, iter_board_json
from app.models import ATSSource


def _raw(i: int) -> RawJob:
    return RawJob(
        source_job_id=str(i), title=f"Software Engineer {i}", location="Austin, TX",
        department="Engineering", employment_type=None, description_html="<p>x</p>",
        apply_url=f"https://example.com/{i}", posted_at="2026-06-01T00:00:00Z", remote=None,
    )


class _BodyAdapter:
    """Stands in for an adapter: 'downloads' `body` through the digest, then yields jobs."""

    source = "greenhouse"

    def __init__(self, body: bytes, jobs: list[RawJob]):
        self.body, self.jobs, self.closed_early = body, jobs, False

    async def fetch(self, slug, client):
        digest = board_digest.get()
        if digest is not None:
            digest.update(self.body)
        for j in self.jobs:
            yield j


def _drive(adapter, board_hash, monkeypatch, force=None):
    import app.ml.embed_jobs as embed_jobs

    monkeypatch.setattr(runner, "_ADAPTERS", {ATSSource.greenhouse: adapter})
    monkeypatch.setattr(embed_jobs, "embed_missing_jobs", lambda *a, **kw: 0)
    if force is None:
        monkeypatch.delenv("INGEST_FORCE_FULL", raising=False)
    else:
        monkeypatch.setenv("INGEST_FORCE_FULL", force)
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = True
    company = SimpleNamespace(id=7, ats=ATSSource.greenhouse, slug="acme", board_hash=board_hash)
    result = asyncio.run(runner._ingest_company(
        company, client=None, sem=asyncio.Semaphore(1),
        run_start=datetime.now(tz=timezone.utc), session=session,
    ))
    return result, session


def _expected_hash(body: bytes) -> str:
    d = BoardDigest()
    d.update(body)
    return d.hexdigest(runner.BOARD_HASH_VERSION)


def _statements(session) -> list[str]:
    return [str(c.args[0]).split()[0].upper() for c in session.execute.call_args_list]


def test_changed_board_is_processed_and_hash_stored(monkeypatch):
    body = b'{"jobs":[1,2,3]}'
    result, session = _drive(_BodyAdapter(body, [_raw(1), _raw(2)]), "stale-hash", monkeypatch)
    assert result["unchanged"] is False and result["jobs_seen"] == 2
    assert _statements(session).count("INSERT") == 2
    update = session.execute.call_args_list[-1].args[0]
    assert update.compile().params["board_hash"] == _expected_hash(body)


def test_unchanged_board_skips_every_job_upsert(monkeypatch):
    body = b'{"jobs":[1,2,3]}'
    result, session = _drive(_BodyAdapter(body, [_raw(1), _raw(2)]), _expected_hash(body), monkeypatch)
    assert result["unchanged"] is True and result["jobs_seen"] == 0
    # Only the one company bookkeeping UPDATE ran: zero job statements.
    assert _statements(session) == ["UPDATE"]
    session.commit.assert_called_once()


def test_unchanged_board_with_no_jobs_is_also_skipped(monkeypatch):
    body = b'{"jobs":[]}'
    result, session = _drive(_BodyAdapter(body, []), _expected_hash(body), monkeypatch)
    assert result["unchanged"] is True
    assert _statements(session) == ["UPDATE"]


def test_force_full_overrides_the_skip(monkeypatch):
    body = b'{"jobs":[1]}'
    result, session = _drive(_BodyAdapter(body, [_raw(1)]), _expected_hash(body), monkeypatch, force="1")
    assert result["unchanged"] is False
    assert _statements(session).count("INSERT") == 1


def test_adapter_that_never_feeds_the_digest_is_never_skipped(monkeypatch):
    class _Silent(_BodyAdapter):
        async def fetch(self, slug, client):
            for j in self.jobs:
                yield j

    result, session = _drive(_Silent(b"", [_raw(1)]), "anything", monkeypatch)
    assert result["unchanged"] is False and result["jobs_seen"] == 1


def test_hash_version_salt_changes_the_digest():
    d = BoardDigest()
    d.update(b"payload")
    assert d.hexdigest("v1") != d.hexdigest("v2")
    assert BoardDigest().hexdigest("v1") is None  # nothing fed: no hash


def test_iter_board_json_feeds_the_digest_with_the_exact_body():
    body = json.dumps({"jobs": [{"id": 1}, {"id": 2}]}).encode()

    class _Resp:
        def raise_for_status(self): ...
        async def aiter_bytes(self):
            yield body[:10]
            yield body[10:]
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    client = MagicMock()
    client.stream = MagicMock(return_value=_Resp())

    async def go():
        digest = BoardDigest()
        token = board_digest.set(digest)
        try:
            items = [i async for i in iter_board_json(client, "http://x", "jobs.item", "acme")]
        finally:
            board_digest.reset(token)
        return items, digest

    items, digest = asyncio.run(go())
    assert [i["id"] for i in items] == [1, 2]
    ref = BoardDigest(); ref.update(body)
    assert digest.hexdigest("v1") == ref.hexdigest("v1")


def test_run_ingest_keeps_unchanged_boards_out_of_soft_close(drive_run_ingest, fake_company, monkeypatch):
    import app.ml.embed_jobs as embed_jobs

    monkeypatch.setattr(embed_jobs, "embed_missing_jobs", lambda *a, **kw: 0)
    body = b'{"jobs":[1]}'
    same = fake_company(slug="same", company_id=1)
    same.board_hash = _expected_hash(body)
    moved = fake_company(slug="moved", company_id=2)
    moved.board_hash = "old"
    adapters = {ATSSource.greenhouse: _BodyAdapter(body, [_raw(1)])}
    run, session = drive_run_ingest([same, moved], adapters)
    closes = [c.args[0] for c in session.execute.call_args_list
              if str(c.args[0]).startswith("UPDATE jobs")]
    assert len(closes) == 1
    params = closes[0].compile().params
    assert params["company_id_1"] == [2]  # only the changed board can have vanished roles
    assert params["description_text"] is None and params["embedding"] is None
