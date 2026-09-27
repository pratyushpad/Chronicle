"""Maintenance tooling must refuse production unless the run is deliberate."""
import pytest

from app.dbguard import ALLOW_ENV, assert_local_or_allowed, db_host, sqlalchemy_url


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


def test_host_query_parameter_cannot_smuggle_a_remote_host(monkeypatch):
    """libpq connects to a `host=` query parameter, so it counts as the host."""
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        assert_local_or_allowed("postgresql://u:p@localhost/db?host=ep-fake.neon.tech", "test")
    assert "ep-fake.neon.tech" in str(exc.value)


def test_unix_socket_host_is_local(monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    assert_local_or_allowed("postgresql://u:p@/chronicle?host=/tmp", "test")  # no exit


@pytest.mark.parametrize("url,expected", [
    # A Neon console string has no driver; SQLAlchemy 2.1 would pick uninstalled psycopg 3.
    ("postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require",
     "postgresql+psycopg2://u:p@ep-x.neon.tech/neondb?sslmode=require"),
    ("postgres://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
    ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
])
def test_sqlalchemy_url_pins_the_installed_driver(url, expected):
    assert sqlalchemy_url(url) == expected


@pytest.mark.parametrize("url", [
    "postgresql://u:p@localhost:5432,ep-x.neon.tech:5432/db",  # libpq host list
    "postgresql://u:p@ep-x.neon.tech,x@localhost/db",  # libpq splits user info at the first @
    "postgresql://u:p@localhost/db?hostaddr=54.0.0.1",
])
def test_every_host_libpq_could_use_must_be_local(url, monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    with pytest.raises(SystemExit):
        assert_local_or_allowed(url, "test")
