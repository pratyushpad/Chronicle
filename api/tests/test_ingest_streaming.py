"""Bounded-memory ingest: adapters stream, the runner consumes one job at a time,
and stored descriptions are capped.

Regression cover for the Aug 29 OOM — a 36 MB / ~2,100-job Greenhouse board that
fit in RAM as a download but not as a list[RawJob] of description HTML.
"""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.ingest import runner
from app.ingest.adapters.base import RawJob
from app.ingest.adapters.greenhouse import GreenhouseAdapter
from app.models import ATSSource


# ── (a) adapters yield incrementally ──────────────────────────────────────────

def _gh_item(i: int) -> dict:
    return {
        "id": i,
        "title": f"Software Engineer {i}",
        "location": {"name": "San Francisco, CA"},
        "departments": [{"name": "Engineering"}],
        "content": "<p>build things</p>",
        "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{i}",
        "updated_at": "2026-06-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_adapter_fetch_is_an_async_generator(mock_client, greenhouse_response):
    """fetch() must return an async iterator, not a materialized list."""
    client, response = mock_client
    response.json.return_value = greenhouse_response

    stream = GreenhouseAdapter().fetch("stripe", client)

    assert not isinstance(stream, list)
    assert inspect.isasyncgen(stream)
    assert hasattr(stream, "__anext__")
    await stream.aclose()


@pytest.mark.asyncio
async def test_adapter_does_not_run_ahead_of_its_consumer(monkeypatch):
    """Taking one job must pull exactly one item from the underlying board stream —
    no read-ahead, so peak memory stays O(one job)."""
    from app.ingest.adapters import greenhouse as gh

    produced: list[int] = []

    async def fake_iter(client, url, prefix, slug, max_bytes=None):
        for i in range(3):
            produced.append(i)
            yield _gh_item(i)

    monkeypatch.setattr(gh, "iter_board_json", fake_iter)

    stream = gh.GreenhouseAdapter().fetch("acme", client=None)
    assert produced == []  # nothing happens until consumption starts

    first = await stream.__anext__()
    assert isinstance(first, RawJob)
    assert first.source_job_id == "0"
    assert produced == [0]  # exactly one item pulled, board not drained

    second = await stream.__anext__()
    assert second.source_job_id == "1"
    assert produced == [0, 1]

    await stream.aclose()


# ── runner harness ────────────────────────────────────────────────────────────


class _FakeAdapter:
    """Adapter stub whose fetch() is a real async generator over canned RawJobs.

    `fail_after` makes the first consume raise partway through, exercising the
    mid-stream failure path.
    """

    source = "greenhouse"

    def __init__(self, jobs: list[RawJob], fail_after: int | None = None):
        self._jobs = jobs
        self._fail_after = fail_after
        self.calls = 0

    async def fetch(self, slug, client):
        self.calls += 1
        should_fail = self._fail_after is not None and self.calls == 1
        for i, job in enumerate(self._jobs):
            if should_fail and i == self._fail_after:
                raise RuntimeError("connection reset mid-board")
            yield job


def _raw(i: int, description_html: str) -> RawJob:
    return RawJob(
        source_job_id=str(i),
        title=f"Software Engineer {i}",
        location="San Francisco, CA",
        department="Engineering",
        employment_type=None,
        description_html=description_html,
        apply_url=f"https://example.com/jobs/{i}",
        posted_at="2026-06-01T00:00:00Z",
        remote=None,
    )


def _company():
    return SimpleNamespace(id=7, ats=ATSSource.greenhouse, slug="acme")


def _session():
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = True  # every row is an insert
    return session


def _run(adapter, session, monkeypatch):
    """Drive _ingest_company against a stubbed adapter, with embedding disabled."""
    import app.ml.embed_jobs as embed_jobs

    monkeypatch.setattr(runner, "_ADAPTERS", {ATSSource.greenhouse: adapter})
    monkeypatch.setattr(embed_jobs, "embed_missing_jobs", lambda *a, **kw: 0)

    from datetime import datetime, timezone

    return asyncio.run(
        runner._ingest_company(
            _company(),
            client=None,
            sem=asyncio.Semaphore(1),
            run_start=datetime.now(tz=timezone.utc),
            session=session,
        )
    )


def _skip_retry_backoff(monkeypatch):
    """Collapse the runner's 2s retry backoff so the retry tests stay fast."""
    real_sleep = asyncio.sleep
    slept: list[float] = []

    async def _instant(seconds):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _instant)
    return slept


def _insert_params(session) -> dict:
    """Bound parameters of the first statement the runner executed (the job upsert)."""
    stmt = session.execute.call_args_list[0].args[0]
    return stmt.compile(dialect=postgresql.dialect()).params


# ── (b) description cap ───────────────────────────────────────────────────────


def _long_description_with_trailing_salary() -> str:
    """A posting far longer than the cap, with the comp band only at the very bottom —
    the real shape of a mega-board posting (boilerplate, then salary)."""
    filler = "<p>We value collaboration and impact. </p>" * 2000
    tail = "<p>The base salary range for this role is $180,000 - $240,000.</p>"
    return filler + tail


def test_description_stored_truncated_at_cap(monkeypatch):
    adapter = _FakeAdapter([_raw(1, _long_description_with_trailing_salary())])
    session = _session()

    result = _run(adapter, session, monkeypatch)

    assert result["error"] is None
    params = _insert_params(session)
    stored = params["description_text"]
    assert len(stored) == runner._MAX_DESC_CHARS
    assert "$180,000" not in stored  # the tail really is past the cap


def test_salary_past_the_cap_is_still_extracted(monkeypatch):
    """Extraction runs on the FULL text; only storage is truncated. If these ever
    swap order, long postings silently lose their comp data."""
    adapter = _FakeAdapter([_raw(1, _long_description_with_trailing_salary())])
    session = _session()

    _run(adapter, session, monkeypatch)

    params = _insert_params(session)
    assert params["salary_min"] == 180_000
    assert params["salary_max"] == 240_000


def test_short_description_is_untouched(monkeypatch):
    html = "<p>Backend role. Python and Postgres. Base salary $150,000 - $190,000.</p>"
    adapter = _FakeAdapter([_raw(1, html)])
    session = _session()

    _run(adapter, session, monkeypatch)

    params = _insert_params(session)
    assert params["description_text"].endswith("$150,000 - $190,000.")
    assert len(params["description_text"]) < runner._MAX_DESC_CHARS


def test_content_hash_matches_the_stored_truncated_text(monkeypatch):
    """Hash covers exactly what's persisted, so an unchanged long posting hashes the
    same every run and never re-embeds."""
    from app.ingest.dedupe import make_content_hash
    from app.ingest.normalize import extract_tech_tags, normalize_location, strip_html

    desc = _long_description_with_trailing_salary()
    adapter = _FakeAdapter([_raw(1, desc)])
    session = _session()

    _run(adapter, session, monkeypatch)
    params = _insert_params(session)

    full = strip_html(desc)
    expected = make_content_hash(
        "Software Engineer 1",
        full[: runner._MAX_DESC_CHARS],
        normalize_location("San Francisco, CA"),
        "Engineering",
        extract_tech_tags(full),
    )
    assert params["content_hash"] == expected


# ── (c) mid-stream failure retry ──────────────────────────────────────────────


def test_midstream_failure_retries_and_does_not_double_count(monkeypatch):
    """First consume dies after 2 of 4 jobs; the retry must roll the partial upserts
    back and report only the successful pass's counts."""
    slept = _skip_retry_backoff(monkeypatch)
    jobs = [_raw(i, f"<p>role {i}</p>") for i in range(4)]
    adapter = _FakeAdapter(jobs, fail_after=2)
    session = _session()

    result = _run(adapter, session, monkeypatch)

    assert result["error"] is None
    assert adapter.calls == 2
    assert slept == [2]  # one backoff between the two attempts
    assert session.rollback.call_count == 1
    assert result["jobs_seen"] == 4  # not 6 — the failed attempt's 2 don't carry over
    assert result["jobs_new"] == 4
    session.commit.assert_called_once()


def test_midstream_failure_twice_gives_up_without_committing(monkeypatch):
    class _AlwaysFails(_FakeAdapter):
        async def fetch(self, slug, client):
            self.calls += 1
            yield self._jobs[0]
            raise RuntimeError("connection reset mid-board")

    _skip_retry_backoff(monkeypatch)
    adapter = _AlwaysFails([_raw(i, f"<p>role {i}</p>") for i in range(3)])
    session = _session()

    result = _run(adapter, session, monkeypatch)

    assert "connection reset" in result["error"]
    assert adapter.calls == 2
    assert session.rollback.call_count == 2
    session.commit.assert_not_called()  # no checkpoint for a company we never finished


def test_board_too_large_rolls_back_and_does_not_retry(monkeypatch):
    from app.ingest.adapters.base import BoardTooLarge

    class _TooLarge(_FakeAdapter):
        async def fetch(self, slug, client):
            self.calls += 1
            raise BoardTooLarge(slug, 64 * 1024 * 1024)
            yield  # pragma: no cover — keeps this an async generator

    adapter = _TooLarge([])
    session = _session()

    result = _run(adapter, session, monkeypatch)

    assert "payload cap" in result["error"]
    assert adapter.calls == 1  # deterministic failure, never retried
    assert session.rollback.call_count == 1
    session.commit.assert_not_called()


def test_successful_stream_commits_checkpoint_once(monkeypatch):
    adapter = _FakeAdapter([_raw(i, f"<p>role {i}</p>") for i in range(3)])
    session = _session()

    result = _run(adapter, session, monkeypatch)

    assert result["jobs_seen"] == 3
    session.rollback.assert_not_called()
    session.commit.assert_called_once()
    # 3 job upserts + 1 last_ingested_at checkpoint
    assert session.execute.call_count == 4
