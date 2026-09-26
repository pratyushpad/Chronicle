"""PR 4 feed filters against real Postgres (TEST_DATABASE_URL; skips without)."""
from datetime import datetime, timezone

from app.models import ATSSource, Company, Job
from tests.test_design_api_db import api  # noqa: F401  (fixture)


def _job(co, sid, **kw):
    now = datetime.now(timezone.utc)
    return Job(company_id=co.id, source=ATSSource.greenhouse, source_job_id=sid, title=f"Filter Intern {sid}",
               title_normalized="x", apply_url="https://example.com", dedup_key=f"dk-sf-{sid}",
               first_seen_at=now, last_seen_at=now, is_active=True, **kw)


def test_student_filters(api):  # noqa: F811
    client, s = api
    co = Company(name="StudentCo", ats=ATSSource.greenhouse, slug="student-co-test", active=True)
    s.add(co)
    s.flush()
    s.add_all([
        _job(co, "a", term_season="summer", term_year=2027, country="US", degree_levels=["bachelor", "master"]),
        _job(co, "b", term_season="fall", term_year=2026, country="CA", degree_levels=["master", "phd"],
             us_citizen_required=True),
        _job(co, "c", clearance_required=True, us_person_required=True),
        _job(co, "d"),  # states nothing: must survive every hide
    ])
    s.flush()

    def titles(**params):
        r = client.get("/jobs", params={"company_id": co.id, **params})
        assert r.status_code == 200, r.text
        return sorted(j["title"][-1] for j in r.json()["items"])

    assert titles() == ["a", "b", "c", "d"]
    assert titles(term="summer-2027") == ["a"]
    assert titles(term="fall") == ["b"]
    assert titles(country="ca") == ["b"]
    assert titles(hide_grad_only=True) == ["a", "c", "d"]
    assert titles(hide_citizen_required=True) == ["a", "c", "d"]
    assert titles(hide_clearance_required=True, hide_us_person_required=True) == ["a", "b", "d"]
    assert client.get("/jobs", params={"term": "summer-27"}).status_code == 422
    item = next(j for j in client.get("/jobs", params={"company_id": co.id}).json()["items"] if j["title"].endswith("b"))
    assert item["us_citizen_required"] is True and item["degree_levels"] == ["master", "phd"]
    meta = client.get("/meta").json()
    assert "fall-2026" in meta["terms"] and "summer-2027" in meta["terms"]
    assert meta["terms"].index("fall-2026") < meta["terms"].index("summer-2027")
    assert "CA" in meta["countries"]
