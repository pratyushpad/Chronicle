"""PR 3 API behaviour against real Postgres (TEST_DATABASE_URL; skips without):
feed sorts, canonical industry filters, and hiring velocity without first-ingest
artifacts. Hermetic: one outer transaction, rolled back."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import ATSSource, Company, Job
from app.routers import jobs as jobs_router


@pytest.fixture
def api(pg_engine):
    conn = pg_engine.connect()
    outer = conn.begin()
    session = Session(bind=conn)
    session.commit = session.flush
    session.rollback = lambda: None

    def _db():
        yield session

    app.dependency_overrides[jobs_router._db] = _db
    jobs_router.invalidate_meta_cache()
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        jobs_router.invalidate_meta_cache()
        outer.rollback()
        conn.close()


def _company(s, name, industry, slug):
    co = Company(name=name, ats=ATSSource.greenhouse, slug=slug, active=True, industry=industry)
    s.add(co)
    s.flush()
    return co


def _job(co, sid, title, *, first_seen, posted=None, sal=None, active=True):
    return Job(
        company_id=co.id, source=ATSSource.greenhouse, source_job_id=sid, title=title,
        title_normalized=title.lower(), apply_url="https://example.com", dedup_key=f"dk-{sid}",
        first_seen_at=first_seen, last_seen_at=first_seen, posted_at=posted, is_active=active,
        salary_min=sal, salary_max=sal,
    )


def test_pay_sort_puts_stated_pay_first_highest_first(api):
    client, s = api
    now = datetime.now(timezone.utc)
    co = _company(s, "SortCo", "AI", "sort-co-test")
    s.add_all([
        _job(co, "p1", "Zeta Intern", first_seen=now, sal=None),
        _job(co, "p2", "Zeta Intern Two", first_seen=now - timedelta(days=3), sal=93_600),
        _job(co, "p3", "Zeta Intern Three", first_seen=now - timedelta(days=9), sal=124_800),
        # Same pay as p2, newer: ties go newest first.
        _job(co, "p4", "Zeta Intern Four", first_seen=now - timedelta(days=1), sal=93_600),
    ])
    s.flush()
    ids = lambda r: [j["title"] for j in r.json()["items"]]
    by_pay = client.get("/jobs", params={"company_id": co.id, "sort": "pay"})
    assert ids(by_pay) == ["Zeta Intern Three", "Zeta Intern Four", "Zeta Intern Two", "Zeta Intern"]
    newest = client.get("/jobs", params={"company_id": co.id})
    assert ids(newest) == ["Zeta Intern", "Zeta Intern Four", "Zeta Intern Two", "Zeta Intern Three"]
    # With a query: relevance by default, and an explicit newest keeps the text match.
    q_newest = client.get("/jobs", params={"company_id": co.id, "q": "zeta", "sort": "newest"})
    assert ids(q_newest) == ["Zeta Intern", "Zeta Intern Four", "Zeta Intern Two", "Zeta Intern Three"]
    q_pay = client.get("/jobs", params={"company_id": co.id, "q": "zeta", "sort": "pay"})
    assert ids(q_pay)[0] == "Zeta Intern Three"


def test_canonical_industry_filters_and_labels(api):
    client, s = api
    now = datetime.now(timezone.utc)
    a = _company(s, "IndA", "AI", "ind-a-test")
    b = _company(s, "IndB", "AI/ML", "ind-b-test")
    c = _company(s, "IndC", "FinTech", "ind-c-test")
    s.add_all([_job(a, "i1", "Role A", first_seen=now), _job(b, "i2", "Role B", first_seen=now),
               _job(c, "i3", "Role C", first_seen=now)])
    s.flush()
    got = client.get("/jobs", params={"industry": "AI & ML", "q": "role"}).json()["items"]
    assert {j["company_name"] for j in got} >= {"IndA", "IndB"}
    assert "IndC" not in {j["company_name"] for j in got}
    # Old links send a raw label ("AI/ML" was a quick pill): it matches its whole group,
    # including companies labelled "AI".
    legacy = client.get("/jobs", params={"industry": "AI/ML", "q": "role"}).json()["items"]
    assert {"IndA", "IndB"} <= {j["company_name"] for j in legacy}
    assert "IndC" not in {j["company_name"] for j in legacy}
    # A label outside the vocabulary keeps the old substring match.
    assert client.get("/jobs", params={"industry": "Fin"}).status_code == 200
    companies = {co["name"]: co["industry"] for co in client.get("/companies").json()}
    assert companies["IndA"] == companies["IndB"] == "AI & ML"
    assert companies["IndC"] == "Fintech"
    meta = client.get("/meta").json()
    assert "AI & ML" in meta["industries"] and "AI/ML" not in meta["industries"]


def test_velocity_leaves_out_roles_already_open_at_first_ingest(api):
    client, s = api
    now = datetime.now(timezone.utc)
    co = _company(s, "VelCo", "Space", "vel-co-test")
    first_ingest = now - timedelta(weeks=3)
    jobs = [
        # 30 roles already open when the board was first read: no publish date.
        *[_job(co, f"old{i}", f"Old {i}", first_seen=first_ingest) for i in range(30)],
        # Same week, but the board says it was published then: a real opening.
        _job(co, "pub", "Published", first_seen=first_ingest, posted=first_ingest - timedelta(hours=2)),
        # Found later without a publish date: counted in the week it was first seen.
        _job(co, "new", "New later", first_seen=now - timedelta(days=1)),
    ]
    s.add_all(jobs)
    s.flush()
    v = client.get(f"/companies/{co.id}/velocity", params={"weeks": 8}).json()
    assert sum(w["opened"] for w in v["weeks"]) == 2
    assert v["first_ingest_excluded"] == 30
    assert v["active_now"] == 32
