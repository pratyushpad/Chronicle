"""Maintenance tooling must refuse production unless the run is deliberate."""
import pytest

from app.dbguard import ALLOW_ENV, assert_local_or_allowed, db_host


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://chronicle:chronicle@127.0.0.1:5434/chronicle",
    "postgresql+psycopg2://chronicle:chronicle@localhost:5433/chronicle",
    "postgresql+psycopg2://chronicle:chronicle@db/chronicle",
    "postgresql://u:p@[::1]:5432/x",
])
def test_local_hosts_pass(url, monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    assert_local_or_allowed(url, "test")  # no exit


def test_remote_host_is_refused(monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    url = "postgresql+psycopg2://user:secret@ep-quiet-sky-123.us-east-2.aws.neon.tech/neondb?sslmode=require"
    with pytest.raises(SystemExit) as exc:
        assert_local_or_allowed(url, "alembic migrations")
    message = str(exc.value)
    assert "ep-quiet-sky-123.us-east-2.aws.neon.tech" in message and ALLOW_ENV in message
    assert "secret" not in message  # never echo credentials


def test_deliberate_remote_run_is_allowed(monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    assert_local_or_allowed("postgresql://u:p@db.example.com/x", "test")


def test_db_host_parses_driver_urls():
    assert db_host("postgresql+psycopg2://u:p@host.example:5432/db") == "host.example"
    assert db_host(None) is None and db_host("not a url") is None
