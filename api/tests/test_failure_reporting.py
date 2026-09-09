"""Ingest failure records must name the crash site, not just the symptom.

Four Lever boards failed in prod with a bare "'NoneType' object is not subscriptable"
and nothing in the run row said which line raised it — not reproducible locally, since
it depends on the shape of that board's data. _describe_error appends "@ file:line"
for the deepest frame inside our own code.
"""
import pytest

from app.ingest import runner
from tests.test_ingest_streaming import (
    _FakeAdapter,
    _raw,
    _run,
    _session,
    _skip_retry_backoff,
)


# ── _describe_error ───────────────────────────────────────────────────────────


def _raised_in_app_code() -> Exception:
    """A live exception whose traceback really does pass through app/."""
    from app.ingest.normalize import normalize_title

    try:
        normalize_title(None)  # re.sub on None -> TypeError, inside app/ingest/normalize.py
    except Exception as exc:
        return exc
    raise AssertionError("normalize_title(None) was expected to raise")


def test_app_code_exception_names_file_and_line():
    described = runner._describe_error(_raised_in_app_code())

    assert described.startswith("TypeError: ")
    _, sep, site = described.partition(" @ ")
    assert sep, f"no crash site in {described!r}"
    file_part, _, line_part = site.rpartition(":")
    assert file_part.endswith("app/ingest/normalize.py")
    assert line_part.isdigit() and int(line_part) > 0


def test_exception_without_traceback_degrades_to_type_and_message():
    """A never-raised exception has no __traceback__ — still a useful record, no crash."""
    described = runner._describe_error(ValueError("boom"))

    assert described == "ValueError: boom"
    assert " @ " not in described


def test_no_app_frame_falls_back_to_the_last_frame():
    """A traceback entirely outside app/ still gets a location rather than nothing."""
    try:
        raise TypeError("'NoneType' object is not subscriptable")
    except Exception as exc:
        described = runner._describe_error(exc)

    assert described.startswith("TypeError: 'NoneType' object is not subscriptable @ ")
    assert "test_failure_reporting.py:" in described


# ── the records themselves ────────────────────────────────────────────────────


class _AlwaysFails(_FakeAdapter):
    """Mimics the prod shape: a board that dies partway with a bare TypeError."""

    async def fetch(self, slug, client):
        self.calls += 1
        yield self._jobs[0]
        raise TypeError("'NoneType' object is not subscriptable")


def test_retry_loop_records_the_enriched_error(monkeypatch):
    """_ingest_company's give-up path stores the crash site, not str(exc)."""
    _skip_retry_backoff(monkeypatch)
    adapter = _AlwaysFails([_raw(0, "<p>role</p>")])

    result = _run(adapter, _session(), monkeypatch)

    assert result["error"].startswith("TypeError: 'NoneType' object is not subscriptable @ ")
    # The consumer loop lives in the runner, which is where a board-shape surprise
    # actually surfaces — that is the line worth naming.
    assert "app/ingest/runner.py:" in result["error"]


def test_run_failures_carry_the_crash_site(drive_run_ingest, fake_company):
    """End of run: the failure written to the IngestRun row is the enriched string."""
    company = fake_company(slug="ghost", name="Ghost Corp")
    adapter = _AlwaysFails([_raw(0, "<p>role</p>")])

    run, _ = drive_run_ingest([company], {company.ats: adapter})

    assert run.companies_failed == 1
    (failure,) = run.failures
    assert failure["slug"] == "ghost"
    assert failure["error"].startswith("TypeError: 'NoneType' object is not subscriptable @ ")
    assert "app/ingest/runner.py:" in failure["error"]


def test_gathered_exception_also_gets_a_crash_site(drive_run_ingest, fake_company):
    """An exception that escapes _ingest_company entirely comes back through
    gather(return_exceptions=True) with __traceback__ intact, so that branch can
    name a site too. An unknown ATS raises on the _ADAPTERS lookup, which sits
    above the per-attempt try/except."""
    company = fake_company(slug="ghost")

    run, _ = drive_run_ingest([company], {})  # empty adapter map -> KeyError

    assert run.companies_failed == 1
    (failure,) = run.failures
    assert failure["error"].startswith("KeyError: ")
    assert "app/ingest/runner.py:" in failure["error"]


def test_boardtoolarge_message_is_left_alone(monkeypatch):
    """Already specific (names the slug and the cap) — no file:line noise added."""
    from app.ingest.adapters.base import BoardTooLarge

    class _TooLarge(_FakeAdapter):
        async def fetch(self, slug, client):
            self.calls += 1
            raise BoardTooLarge(slug, 64 * 1024 * 1024)
            yield  # pragma: no cover — keeps this an async generator

    result = _run(_TooLarge([]), _session(), monkeypatch)

    assert "payload cap" in result["error"]
    assert " @ " not in result["error"]


@pytest.mark.parametrize("exc", [ValueError("x"), KeyError("k"), RuntimeError("")])
def test_describe_error_never_raises(exc):
    """It runs on the failure path; it must not be able to create a second failure."""
    assert runner._describe_error(exc).startswith(type(exc).__name__ + ":")
