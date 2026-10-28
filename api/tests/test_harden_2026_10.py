"""Hardening from the Oct 2026 cost audit: input bounds, rate limit, caches, 503 on DB loss.

No database: validation and the limiter run before any query, and the cached endpoints'
query helpers are monkeypatched. TestClient is used without `with`, so startup never runs.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.ratelimit import SlidingWindowLimiter, client_id
from app.routers import jobs
from app.schemas import CompanyItem, SitemapJobsResponse


@pytest.fixture
def client():
    app.dependency_overrides[jobs._db] = lambda: MagicMock()
    jobs._COMPANIES_CACHE.clear()
    jobs._SITEMAP_CACHE.clear()
    jobs.search_limiter.reset()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        jobs.search_limiter.reset()


@pytest.mark.parametrize(
    "query",
    [
        "q=" + "a" * 201,
        "company=" + "a" * 201,
        "location=" + "a" * 201,
        "department=" + "a" * 201,
        "industry=" + "a" * 201,
        "q=%00null",
        "company=x%00",
        "page=501",
        "sort=" + "a" * 21,
    ],
)
def test_jobs_rejects_oversized_or_nul_inputs(client, query):
    assert client.get(f"/jobs?{query}").status_code == 422


def test_sitemap_jobs_limit_capped(client):
    assert client.get("/sitemap/jobs?limit=20000").status_code == 422
    assert client.get("/sitemap/jobs?offset=999999999").status_code == 422


def test_semantic_search_rate_limited_before_db(client, monkeypatch):
    monkeypatch.setattr(jobs.search_limiter, "limit", 0)
    r = client.get("/jobs?q=engineer&mode=hybrid")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_trusted_server_exempt_from_search_limit(client, monkeypatch):
    from app.ratelimit import SERVICE_HEADER, service_key

    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    monkeypatch.setattr(jobs.search_limiter, "limit", 0)
    monkeypatch.setattr(jobs, "_last_run_start", MagicMock(side_effect=RuntimeError("past limiter")))
    url = "/jobs?q=engineer&mode=hybrid"
    # Right key: gets past the limiter (then fails on the fake session).
    assert client.get(url, headers={SERVICE_HEADER: service_key("s3cret")}).status_code == 500
    # Wrong key, no key: still limited.
    assert client.get(url, headers={SERVICE_HEADER: service_key("other")}).status_code == 429
    assert client.get(url, headers={SERVICE_HEADER: "x"}).status_code == 429
    assert client.get(url).status_code == 429


def test_no_secret_configured_exempts_nobody(client, monkeypatch):
    from app.ratelimit import SERVICE_HEADER, service_key

    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    monkeypatch.setattr(jobs.search_limiter, "limit", 0)
    r = client.get("/jobs?q=engineer&mode=hybrid", headers={SERVICE_HEADER: service_key("")})
    assert r.status_code == 429


def test_keyword_search_not_rate_limited(client, monkeypatch):
    monkeypatch.setattr(jobs.search_limiter, "limit", 0)
    monkeypatch.setattr(jobs, "_last_run_start", MagicMock(side_effect=RuntimeError("past limiter")))
    # Gets past the limiter into the handler (which then fails on the fake session).
    assert client.get("/jobs?q=engineer&mode=keyword").status_code == 500


def test_sliding_window_allows_then_blocks_then_recovers():
    lim = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert lim.allow("a", now=0)[0]
    assert lim.allow("a", now=1)[0]
    ok, retry = lim.allow("a", now=2)
    assert not ok and 1 <= retry <= 60
    assert lim.allow("b", now=2)[0]  # other clients unaffected
    assert lim.allow("a", now=61)[0]  # window slid


def test_client_id_uses_rightmost_forwarded_for():
    req = MagicMock()
    req.headers = {"x-forwarded-for": "6.6.6.6, 1.2.3.4"}
    assert client_id(req) == "1.2.3.4"  # the spoofable left entry is ignored
    req.headers = {}
    req.client.host = "9.9.9.9"
    assert client_id(req) == "9.9.9.9"


def test_companies_cached_in_process_with_cache_header(client, monkeypatch):
    calls = []

    def fake(session, industry):
        calls.append(industry)
        return [CompanyItem(id=1, name="Acme", ats="greenhouse", careers_url="https://x", industry=None, active_job_count=3)]

    monkeypatch.setattr(jobs, "_list_companies", fake)
    for _ in range(3):
        r = client.get("/companies")
        assert r.status_code == 200
    assert len(calls) == 1
    assert "max-age=300" in r.headers["Cache-Control"]
    jobs.invalidate_meta_cache()  # an ingest run drops it
    client.get("/companies")
    assert len(calls) == 2


def test_sitemap_jobs_cached(client, monkeypatch):
    calls = []

    def fake(session, offset, limit):
        calls.append((offset, limit))
        return SitemapJobsResponse(total=0, items=[])

    monkeypatch.setattr(jobs, "_sitemap_jobs", fake)
    client.get("/sitemap/jobs")
    client.get("/sitemap/jobs")
    assert calls == [(0, 2000)]


def test_database_unavailable_returns_503(client, monkeypatch):
    def boom(session, industry):
        raise OperationalError("SELECT 1", {}, Exception("could not connect"))

    monkeypatch.setattr(jobs, "_list_companies", boom)
    r = client.get("/companies")
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "60"
    assert "Traceback" not in r.text


def test_cors_preflight_cached_for_a_day(client):
    r = client.options(
        "/jobs",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-max-age") == "86400"


def test_db_connect_args_only_bound_connect(monkeypatch):
    """No global statement_timeout: ingest, admin and backfill jobs must not get one."""
    from app import db

    for url in (
        "postgresql://u:p@ep-x.us-east-1.aws.neon.tech/db",
        "postgresql://u:p@ep-x-pooler.us-east-1.aws.neon.tech/db",
    ):
        monkeypatch.setenv("DATABASE_URL", url)
        assert db._connect_args() == {"connect_timeout": 5}




def test_request_session_sets_local_timeout_every_transaction(monkeypatch):
    from unittest.mock import MagicMock

    from app import db

    sess = db.get_request_session()
    conn = MagicMock()
    # Fire the after_begin hook the way the Session does at the start of each transaction.
    sess.dispatch.after_begin(sess, MagicMock(), conn)
    sess.dispatch.after_begin(sess, MagicMock(), conn)  # e.g. a second one after a commit
    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert sqls == ["SET LOCAL statement_timeout = '15000ms'"] * 2
    sess.close()


def test_plain_session_has_no_timeout_hook():
    """get_session() (ingest, admin, backfill, scripts) must stay unbounded."""
    from unittest.mock import MagicMock

    from app import db

    sess = db.get_session()
    conn = MagicMock()
    sess.dispatch.after_begin(sess, MagicMock(), conn)
    conn.execute.assert_not_called()
    sess.close()


def test_public_routers_use_request_session_and_jobs_do_not():
    import inspect

    from app.routers import admin, jobs, users

    assert "get_request_session()" in inspect.getsource(jobs._db)
    assert "get_request_session()" in inspect.getsource(users.get_current_user.__globals__["_db"])
    assert "get_request_session" not in inspect.getsource(admin)
