"""/status and /admin/bench against real Postgres (TEST_DATABASE_URL; skips without)."""
from datetime import datetime, timedelta, timezone

from app.models import ATSSource, Company, IngestRun
from tests.test_design_api_db import api  # noqa: F401  (fixture)


def test_status_lists_runs_and_failing_boards(api):  # noqa: F811
    client, s = api
    from app.routers import jobs as jobs_router
    jobs_router._STATUS_CACHE.clear()
    now = datetime.now(timezone.utc)
    co = Company(name="DeadCo", ats=ATSSource.greenhouse, slug="deadco-status-test", active=True)
    s.add(co)
    fail = {"company": "DeadCo", "ats": "greenhouse", "slug": "deadco-status-test", "error": "HTTPStatusError: 404 @ /srv/app/ingest/adapters/base.py:44"}
    s.add_all([
        IngestRun(started_at=now - timedelta(hours=30), finished_at=now - timedelta(hours=29), companies_total=3,
                  companies_ok=2, companies_failed=1, jobs_seen=10, jobs_new=1, jobs_closed=0, failures=[fail]),
        IngestRun(started_at=now - timedelta(hours=20), finished_at=now - timedelta(hours=20), companies_total=0,
                  companies_ok=0, companies_failed=0, jobs_seen=0, jobs_new=0, jobs_closed=0, failures=[]),
        IngestRun(started_at=now - timedelta(hours=6), finished_at=now - timedelta(hours=5), companies_total=3,
                  companies_ok=2, companies_failed=1, jobs_seen=12, jobs_new=2, jobs_closed=1, failures=[fail]),
    ])
    s.flush()
    body = client.get("/status").json()
    runs = body["runs"]
    assert runs[0]["seconds"] == 3600 and runs[0]["boards_failed"] == 1 and not runs[0]["crashed"]
    assert runs[1]["crashed"] is True  # closed at its own start time: reclaimed as crashed
    dead = next(b for b in body["failing_boards"] if b["slug"] == "deadco-status-test")
    assert dead["failed_runs"] == 2 and dead["last_error"] == "HTTPStatusError: 404"
    # Non-network errors publish their class only (a DB error names hosts and SQL).
    from app.routers.jobs import _public_error
    assert _public_error("OperationalError: could not connect to ep-x.neon.tech [SQL: INSERT …]") == "OperationalError"
    assert dead["last_success_at"] is None
    assert body["freshness"]["boards_active"] >= 1


def test_bench_requires_the_secret_and_reports_percentiles(api, monkeypatch):  # noqa: F811
    client, _ = api
    assert client.post("/admin/bench").status_code in (401, 500)
    monkeypatch.setenv("INGEST_SECRET", "bench-test")
    assert client.post("/admin/bench", headers={"X-Ingest-Secret": "nope"}).status_code == 401
    from app.routers import admin

    app_ = client.app
    app_.dependency_overrides[admin._db] = app_.dependency_overrides[next(iter(app_.dependency_overrides))]
    r = client.post("/admin/bench", params={"n": 5, "modes": "keyword"}, headers={"X-Ingest-Secret": "bench-test"})
    assert r.status_code == 200, r.text
    res = r.json()["results"]["keyword"]
    assert res["n"] == 5 and 0 <= res["p50_ms"] <= res["p95_ms"] <= res["max_ms"]
