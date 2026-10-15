"""Neon egress regression tests, against real Postgres (TEST_DATABASE_URL; skips without).

Everything a query sends back is billed as egress, and anonymous crawlers render job pages
all day. Two kinds of test live here:

* "loads only ..." tests record the result sets the database returns during ONE API request
  (conftest.record_selects) and fail when a request pulls a column, or a row volume, that
  its response never uses (the 6 KB description and the 4.7 KB embedding vector on every
  list card, 4,914 location rows for 42 metro counts, ...).
* "is unchanged" tests pin the response itself, so trimming a query can never change what
  a user or a crawler receives.

Hermetic: one outer transaction, rolled back."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import InvalidRequestError

from app.ingest.description import description_blocks, description_plain, description_summary
from app.job_items import job_list_item
from app.main import app
from app.models import (
    Application, ApplicationEvent, AppStatus, ATSSource, Company, IngestRun, Job, Profile,
    RemotePref, User,
)
from app.routers import applications, recommendations, saved
from app.routers.users import get_current_user
from tests.test_design_api_db import api  # noqa: F401  (fixture)

# Columns of `jobs` that no list card reads. The first two are the heavy ones (avg 6.4 KB of
# description, avg 4.7 KB of vector text per row); the rest are bookkeeping the card ignores.
HEAVY = ("description_text", "embedding")
NOT_ON_A_CARD = HEAVY + (
    "content_hash", "source_job_id", "title_normalized", "department_raw", "location_raw", "source",
)


def _vec(*head: float) -> list[float]:
    return list(head) + [0.0] * (384 - len(head))


# About 7 KB, like a real posting: any query that ships it is obvious in the log.
_BODY = "<p>" + "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 120 + "</p>"

# Every field a card shows, filled in, so a column the loader forgot cannot hide behind a None.
_CARD_FIELDS = dict(
    location_raw="San Francisco, CA, USA", remote=False, department="Engineering",
    department_raw="Software Engineering", employment_type="Internship", experience_level="Internship",
    tech_tags=["python", "ros"], sponsorship_flag="likely_yes", salary_min=93_600, salary_max=114_400,
    pay_min=Decimal("45.00"), pay_max=Decimal("55.00"), pay_currency="USD", pay_period="hour",
    pay_source="ats", term_season="summer", term_year=2027, degree_levels=["bachelor", "master"],
    grad_year_min=2027, grad_year_max=2028, us_citizen_required=False, us_person_required=True,
    clearance_required=False, workplace_type="onsite", country="US", content_hash="c" * 64,
    description_text=_BODY,
)


def _job(co_id, sid, dedup, title, *, first_seen, posted=None, emb=None, active=True,
         loc="san francisco, ca", **kw):
    return Job(
        company_id=co_id, source=ATSSource.greenhouse, source_job_id=sid, title=title,
        title_normalized=title.lower(), location_normalized=loc, apply_url=f"https://example.com/apply/{sid}",
        dedup_key=dedup, first_seen_at=first_seen, last_seen_at=first_seen, posted_at=posted,
        is_active=active, embedding=emb, **{**_CARD_FIELDS, **kw},
    )


def _seed(s) -> SimpleNamespace:
    """Two companies, six jobs and one ingest run, every card field filled in.

    Feed order (newest first): fresh, plat, gold, zeta. `gold` is posted in two cities
    (gold_ny is the older posting of the same role), `closed` is inactive, `fresh` arrived
    after the last run. Returns ids and the cards the API must return for them; the seeded
    rows are detached so the API under test loads its own."""
    now = datetime.now(timezone.utc)
    co = Company(name="EgressCo", ats=ATSSource.greenhouse, slug="egress-co-test", active=True,
                 industry="AI", careers_url="https://careers.egressco.com/open-roles")
    other = Company(name="OtherCo", ats=ATSSource.greenhouse, slug="egress-other-test", active=True)
    s.add_all([co, other])
    s.flush()
    run = IngestRun(started_at=now - timedelta(hours=6), finished_at=now - timedelta(hours=5),
                    companies_total=2, companies_ok=2, companies_failed=0, jobs_seen=5, jobs_new=1,
                    jobs_closed=0, failures=[])
    jobs = {
        "gold": _job(co.id, "e1", "dk-gold", "Robotics Intern", first_seen=now - timedelta(days=10),
                     posted=now - timedelta(days=12), emb=_vec(1, 0)),
        "gold_ny": _job(co.id, "e1b", "dk-gold", "Robotics Trainee", first_seen=now - timedelta(days=30),
                        emb=_vec(0.8, 0.2), loc="new york, ny"),
        "fresh": _job(co.id, "e2", "dk-fresh", "Data Intern", first_seen=now - timedelta(hours=1),
                      emb=_vec(0.9, 0.1)),
        "plat": _job(co.id, "e3", "dk-plat", "Platform Engineer", first_seen=now - timedelta(days=3),
                     emb=_vec(0.5, 0.5)),
        "closed": _job(co.id, "e4", "dk-closed", "Closed Role", first_seen=now - timedelta(days=4),
                       emb=_vec(1, 0.01), active=False),
        "zeta": _job(other.id, "e5", "dk-zeta", "Zeta Analyst", first_seen=now - timedelta(days=20),
                     emb=_vec(0, 1)),
    }
    s.add(run)
    s.add_all(jobs.values())
    s.flush()
    corpus = SimpleNamespace(
        co_id=co.id, other_id=other.id, ids={k: j.id for k, j in jobs.items()},
        run_started_at=run.started_at, now=now,
    )
    for obj in (co, other, run, *jobs.values()):
        s.expunge(obj)
    corpus.feed_cards = _expected_cards(s, feed=True)
    corpus.bare_cards = _expected_cards(s, feed=False)
    return corpus


def _expected_cards(s, *, feed: bool) -> dict[int, dict]:
    """The card the API must return for every job: built by the same job_list_item, but from
    fully loaded rows (no loader option), so it does not depend on what the list queries
    fetch. Feed cards also carry the sibling-location list and is_new, worked out here from
    the data."""
    last_start = s.execute(select(func.max(IngestRun.started_at))).scalar_one()
    rows = s.execute(
        select(Job, Company.name, Company.careers_url).join(Company)
    ).all()
    places: dict[str, set[str]] = {}
    for job, _, _ in rows:
        if job.is_active and job.location_normalized:
            places.setdefault(job.dedup_key, set()).add(job.location_normalized)
    cards = {}
    for job, name, careers_url in rows:
        if feed:
            locs = sorted(places.get(job.dedup_key, ()))
            extra = {"locations": locs or None, "location_count": len(locs) or None,
                     "is_new": bool(last_start and job.first_seen_at >= last_start)}
        else:
            extra = {"is_new": False}
        cards[job.id] = job_list_item(job, name, careers_url, **extra).model_dump(mode="json")
    for job, _, _ in rows:
        s.expunge(job)
    return cards


def _ids(body) -> list[int]:
    return [it["id"] for it in body["items"]]


@pytest.fixture
def stub_embedder(monkeypatch):
    """The semantic arm embeds the query with the ONNX model; every query becomes vec(1, 0)."""
    class _Stub:
        def encode(self, texts, batch_size=None):
            return [_vec(1, 0) for _ in texts]

    monkeypatch.setattr("app.ml.embedder.get_embedder", lambda: _Stub())


# ── Fix 1: every list path loads card columns only ───────────────────────────────────────

# kind -> (query params, expected ids in order, by corpus key).
_FEEDS = {
    "recency": ({}, ["fresh", "plat", "gold", "zeta"]),
    "more_at_company": ({"company_id": "co", "page_size": 5}, ["fresh", "plat", "gold"]),
    "keyword": ({"q": "intern"}, ["fresh", "gold"]),
    "keyword_newest": ({"q": "intern", "sort": "newest"}, ["fresh", "gold"]),
    "semantic": ({"q": "robotics", "mode": "semantic"}, ["gold", "fresh", "plat", "zeta"]),
    "hybrid": ({"q": "intern", "mode": "hybrid"}, ["gold", "fresh", "plat", "zeta"]),
}


def _feed_params(corpus, kind):
    params = dict(_FEEDS[kind][0])
    if params.get("company_id") == "co":
        params["company_id"] = corpus.co_id
    return params


@pytest.mark.parametrize("kind", list(_FEEDS))
def test_feed_response_is_unchanged(api, stub_embedder, kind):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    r = client.get("/jobs", params=_feed_params(corpus, kind))
    assert r.status_code == 200, r.text
    body = r.json()
    assert _ids(body) == [corpus.ids[k] for k in _FEEDS[kind][1]]
    assert body["items"] == [corpus.feed_cards[i] for i in _ids(body)]
    assert body["total"] == len(_FEEDS[kind][1])
    if kind in ("semantic", "hybrid"):
        # Not the keyword fallback that swallows a broken semantic path.
        assert body["search_mode"] == kind


@pytest.mark.parametrize("kind", list(_FEEDS))
def test_feed_loads_card_columns_only(api, record_selects, stub_embedder, kind):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    with record_selects() as log:
        r = client.get("/jobs", params=_feed_params(corpus, kind))
    assert r.status_code == 200, r.text
    if kind in ("semantic", "hybrid"):
        assert r.json()["search_mode"] == kind  # the semantic path ran, not the fallback
    assert log.with_column("apply_url"), "no job cards were queried: the recorder saw nothing"
    log.assert_never_returned(*NOT_ON_A_CARD)


def test_card_fields_are_pinned(api):  # noqa: F811
    """Hand-written, so a field dropped from or renamed in the card cannot pass by the
    expected value being built from the same code."""
    client, s = api
    corpus = _seed(s)
    items = client.get("/jobs").json()["items"]
    gold = next(it for it in items if it["id"] == corpus.ids["gold"])
    stamps = {k: datetime.fromisoformat(gold.pop(k)) for k in ("posted_at", "first_seen_at", "last_seen_at")}
    assert gold == {
        "id": corpus.ids["gold"], "title": "Robotics Intern", "company_name": "EgressCo",
        "company_id": corpus.co_id, "company_domain": "egressco.com",
        "location_normalized": "san francisco, ca", "locations": ["new york, ny", "san francisco, ca"],
        "location_count": 2, "remote": False, "department": "Engineering",
        "employment_type": "Internship", "experience_level": "Internship", "tech_tags": ["python", "ros"],
        "sponsorship_flag": "likely_yes", "salary_min": 93_600, "salary_max": 114_400,
        "pay_min": 45.0, "pay_max": 55.0, "pay_currency": "USD", "pay_period": "hour", "pay_source": "ats",
        "term_season": "summer", "term_year": 2027, "degree_levels": ["bachelor", "master"],
        "grad_year_min": 2027, "grad_year_max": 2028, "us_citizen_required": False,
        "us_person_required": True, "clearance_required": False, "workplace_type": "onsite",
        "country": "US", "is_active": True, "apply_url": "https://example.com/apply/e1", "is_new": False,
    }
    assert stamps["posted_at"] == corpus.now - timedelta(days=12)
    assert stamps["first_seen_at"] == corpus.now - timedelta(days=10)
    fresh = next(it for it in items if it["id"] == corpus.ids["fresh"])
    assert fresh["is_new"] is True and fresh["posted_at"] is None


def test_list_loader_raises_instead_of_lazy_loading(api):  # noqa: F811
    """A column the card needs but the loader forgot must fail loudly, not turn into one
    extra query per row."""
    from app.job_items import LIST_LOAD

    client, s = api
    corpus = _seed(s)
    job = s.execute(select(Job).options(LIST_LOAD).where(Job.id == corpus.ids["gold"])).scalar_one()
    assert job.title == "Robotics Intern" and job.dedup_key == "dk-gold"
    for column in ("description_text", "embedding", "content_hash"):
        with pytest.raises(InvalidRequestError):
            getattr(job, column)


# ── Signed-in surfaces: For You, saved, tracker ──────────────────────────────────────────

@pytest.fixture
def signed_in(api):  # noqa: F811
    """A user with a profile (attached in memory, so no profile query runs during a request),
    and the dependency overrides that make the three signed-in routers use the test session."""
    client, s = api
    user = User(auth_provider="test", auth_provider_id="egress-user", email="egress-user@example.com",
                profile=Profile(tracks=["robotics", "data"], tech_tags=["python"], seniority_pref=["intern"],
                                remote_pref=RemotePref.any, location="San Francisco, CA",
                                needs_sponsorship=False))
    s.add(user)
    s.flush()
    app.dependency_overrides[get_current_user] = lambda: user
    for router in (recommendations, saved, applications):
        app.dependency_overrides[router._db] = lambda: s
    return client, s, user


def _track(s, user, corpus, key, status=AppStatus.saved):
    now = datetime.now(timezone.utc)
    tracked = Application(user_id=user.id, job_id=corpus.ids[key], status=status, created_at=now, updated_at=now)
    s.add(tracked)
    s.flush()
    s.add(ApplicationEvent(application_id=tracked.id, from_status=None, to_status=status.value, at=now))
    s.flush()
    return tracked


def _for_you(s, user, corpus):
    """What For You must return, scored by the same pure functions over fully loaded rows."""
    profile = user.profile
    ctx = recommendations.RuleContext(
        tracks=profile.tracks, user_tech=profile.tech_tags, seniority_pref=profile.seniority_pref,
        remote_pref="any", location_pref=profile.location, needs_sponsorship=False,
    )
    rows = s.execute(
        select(Job, Company.name, Company.careers_url).join(Company).where(Job.is_active == True)  # noqa: E712
    ).all()
    scored = []
    for job, name, careers_url in rows:
        total, why = recommendations.rule_score(job, ctx)
        if profile.embedding is not None:
            cosine = float(sum(a * b for a, b in zip(job.embedding, profile.embedding)) /
                           ((sum(a * a for a in job.embedding) ** 0.5) *
                            (sum(b * b for b in profile.embedding) ** 0.5)))
            scored.append((cosine, total, why, job, name, careers_url))
        elif total > 0:
            scored.append((total, total, why, job, name, careers_url))
    if profile.embedding is not None:
        max_rule = max(t for _, t, *_ in scored)
        scored = [(recommendations.blend_score(c, t, max_rule), t, w, j, n, u) for c, t, w, j, n, u in scored]
    scored.sort(key=lambda x: x[0], reverse=True)
    expected, seen = [], set()
    for sc, _, w, j, n, u in scored:
        if j.dedup_key in seen:  # one posting per role: the best-scored
            continue
        seen.add(j.dedup_key)
        expected.append({
            "job": job_list_item(j, n, u, is_new=False).model_dump(mode="json"),
            "score": round(sc, 3), "why": w,
        })
    for _, _, _, j, _, _ in scored:
        s.expunge(j)
    return expected


def test_for_you_rule_path_is_unchanged(signed_in):
    client, s, user = signed_in
    corpus = _seed(s)
    expected = _for_you(s, user, corpus)
    got = client.get("/users/me/recommendations").json()
    assert [g["job"]["id"] for g in got] == [e["job"]["id"] for e in expected]
    assert got == expected
    assert len(got) == 4  # fresh, plat, gold, zeta: a cross-posted role appears once


def test_for_you_rule_path_loads_card_columns_only(signed_in, record_selects):
    client, s, user = signed_in
    _seed(s)
    with record_selects() as log:
        r = client.get("/users/me/recommendations")
    assert r.status_code == 200 and r.json()
    assert log.with_column("apply_url")
    log.assert_never_returned(*NOT_ON_A_CARD)


def test_for_you_two_stage_path_is_unchanged(signed_in):
    client, s, user = signed_in
    user.profile.embedding = _vec(1, 0)
    s.flush()
    corpus = _seed(s)
    expected = _for_you(s, user, corpus)
    got = client.get("/users/me/recommendations").json()
    assert [g["job"]["id"] for g in got] == [e["job"]["id"] for e in expected]
    assert got == expected


def test_for_you_two_stage_path_loads_card_columns_only(signed_in, record_selects):
    client, s, user = signed_in
    user.profile.embedding = _vec(1, 0)
    s.flush()
    _seed(s)
    with record_selects() as log:
        r = client.get("/users/me/recommendations")
    assert r.status_code == 200 and r.json()
    assert log.with_column("distance"), "the two-stage query did not run"
    log.assert_never_returned(*NOT_ON_A_CARD)


def test_saved_list_is_unchanged(signed_in):
    client, s, user = signed_in
    corpus = _seed(s)
    a = _track(s, user, corpus, "gold")
    b = _track(s, user, corpus, "zeta")
    got = client.get("/users/me/saved").json()
    assert [(g["id"], g["job_id"]) for g in got] == [(b.id, corpus.ids["zeta"]), (a.id, corpus.ids["gold"])]
    assert [g["job"] for g in got] == [corpus.bare_cards[corpus.ids["zeta"]], corpus.bare_cards[corpus.ids["gold"]]]


def test_saved_list_loads_card_columns_only(signed_in, record_selects):
    client, s, user = signed_in
    corpus = _seed(s)
    _track(s, user, corpus, "gold")
    with record_selects() as log:
        r = client.get("/users/me/saved")
    assert r.status_code == 200 and r.json()
    assert log.with_column("apply_url")
    log.assert_never_returned(*NOT_ON_A_CARD)


def test_tracker_list_is_unchanged(signed_in):
    client, s, user = signed_in
    corpus = _seed(s)
    a = _track(s, user, corpus, "gold", AppStatus.applied)
    b = _track(s, user, corpus, "fresh")
    got = client.get("/users/me/applications").json()
    assert [g["id"] for g in got] == [b.id, a.id]
    assert [g["job"] for g in got] == [corpus.bare_cards[corpus.ids["fresh"]], corpus.bare_cards[corpus.ids["gold"]]]
    assert [g["status"] for g in got] == ["saved", "applied"]
    assert [[e["to_status"] for e in g["events"]] for g in got] == [["saved"], ["applied"]]


def test_tracker_list_loads_card_columns_only(signed_in, record_selects):
    client, s, user = signed_in
    corpus = _seed(s)
    _track(s, user, corpus, "gold", AppStatus.applied)
    with record_selects() as log:
        r = client.get("/users/me/applications")
    assert r.status_code == 200 and r.json()
    assert log.with_column("apply_url")
    log.assert_never_returned(*NOT_ON_A_CARD)


def test_tracker_update_is_unchanged_and_loads_card_columns_only(signed_in, record_selects):
    """PUT answers with the application and its job card (applications._get_app_with_job)."""
    client, s, user = signed_in
    corpus = _seed(s)
    tracked = _track(s, user, corpus, "gold")
    with record_selects() as log:
        r = client.put(f"/users/me/applications/{tracked.id}", json={"status": "applied", "notes": "emailed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"] == corpus.bare_cards[corpus.ids["gold"]]
    assert (body["status"], body["notes"]) == ("applied", "emailed")
    assert [e["to_status"] for e in body["events"]] == ["saved", "applied"]
    assert log.with_column("apply_url")
    log.assert_never_returned(*NOT_ON_A_CARD)


# ── Fix 2: the job page loads the columns it shows, and never the vector ─────────────────

# Columns of `jobs` that JobDetail never reads. embedding is the heavy one.
NOT_ON_A_DETAIL = (
    "embedding", "content_hash", "source_job_id", "title_normalized", "department_raw", "dedup_key", "source",
)


def test_detail_response_is_unchanged(api):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    r = client.get(f"/jobs/{corpus.ids['gold']}")
    assert r.status_code == 200, r.text
    body = r.json()
    stamps = {k: datetime.fromisoformat(body.pop(k)) for k in ("posted_at", "first_seen_at", "last_seen_at")}
    assert body == {
        "id": corpus.ids["gold"], "title": "Robotics Intern", "company_name": "EgressCo",
        "company_id": corpus.co_id, "company_industry": "AI & ML",
        "location_raw": "San Francisco, CA, USA", "location_normalized": "san francisco, ca",
        "remote": False, "department": "Engineering", "employment_type": "Internship",
        "experience_level": "Internship", "tech_tags": ["python", "ros"], "sponsorship_flag": "likely_yes",
        "salary_min": 93_600, "salary_max": 114_400, "pay_min": 45.0, "pay_max": 55.0,
        "pay_currency": "USD", "pay_period": "hour", "pay_source": "ats", "term_season": "summer",
        "term_year": 2027, "degree_levels": ["bachelor", "master"], "grad_year_min": 2027,
        "grad_year_max": 2028, "us_citizen_required": False, "us_person_required": True,
        "clearance_required": False, "workplace_type": "onsite", "country": "US",
        "description_text": description_plain(_BODY), "description_blocks": description_blocks(_BODY),
        "description_summary": description_summary(_BODY), "apply_url": "https://example.com/apply/e1",
        "is_active": True,
    }
    assert body["description_text"].startswith("Lorem ipsum dolor sit amet") and body["description_blocks"]
    assert stamps["posted_at"] == corpus.now - timedelta(days=12)
    assert stamps["first_seen_at"] == corpus.now - timedelta(days=10)
    assert stamps["last_seen_at"] == stamps["first_seen_at"]


def test_detail_of_a_job_without_description_or_company_industry_is_unchanged(api):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    bare = _job(corpus.other_id, "bare", "dk-bare", "Bare Role", first_seen=corpus.now, loc=None,
                description_text=None, location_raw=None, remote=None, tech_tags=None, pay_min=None,
                pay_max=None)
    s.add(bare)
    s.flush()
    body = client.get(f"/jobs/{bare.id}").json()
    assert body["company_industry"] is None and body["location_raw"] is None
    assert (body["description_text"], body["description_blocks"], body["description_summary"]) == (None, [], None)
    assert (body["pay_min"], body["pay_max"], body["tech_tags"], body["posted_at"]) == (None, None, None, None)


def test_detail_of_a_missing_job_is_a_404(api):  # noqa: F811
    client, s = api
    r = client.get("/jobs/2147483000")
    assert r.status_code == 404 and r.json() == {"detail": "Job not found"}


def test_detail_loads_the_description_but_not_the_vector(api, record_selects):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    with record_selects() as log:
        r = client.get(f"/jobs/{corpus.ids['gold']}")
    assert r.status_code == 200 and r.json()["description_text"]
    assert log.with_column("description_text"), "the page shows the description: it must still be loaded"
    log.assert_never_returned(*NOT_ON_A_DETAIL)


# ── Fix 3: similar roles never ship the source vector to Python ──────────────────────────

def test_similar_response_is_unchanged(api):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    r = client.get(f"/jobs/{corpus.ids['gold']}/similar")
    assert r.status_code == 200, r.text
    # Nearest first; the role's own cross-post (gold_ny) and the inactive role are left out.
    assert [it["id"] for it in r.json()] == [corpus.ids[k] for k in ("fresh", "plat", "zeta")]
    assert r.json() == [corpus.bare_cards[corpus.ids[k]] for k in ("fresh", "plat", "zeta")]


def test_similar_still_overfetches_four_candidates_per_result(api):  # noqa: F811
    """Five postings of one role are the nearest rows. Asking for two roles must still reach
    past them (limit * 4 = 8 candidates) to the next distinct role."""
    client, s = api
    corpus = _seed(s)
    src = _job(corpus.co_id, "s0", "dk-src", "Source", first_seen=corpus.now, emb=_vec(0, 0, 1))
    near = [_job(corpus.co_id, f"n{i}", "dk-near", "Near", first_seen=corpus.now, emb=_vec(0, 0, 1, 0.01 * i))
            for i in range(5)]
    next_a = _job(corpus.co_id, "x1", "dk-x1", "Next A", first_seen=corpus.now, emb=_vec(0, 0.3, 1))
    next_b = _job(corpus.co_id, "x2", "dk-x2", "Next B", first_seen=corpus.now, emb=_vec(0, 0.6, 1))
    s.add_all([src, *near, next_a, next_b])
    s.flush()
    got = client.get(f"/jobs/{src.id}/similar", params={"limit": 2}).json()
    assert len(got) == 2
    assert got[0]["id"] in {n.id for n in near} and got[1]["id"] == next_a.id


def test_similar_of_missing_or_unembedded_jobs(api):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    bare = _job(corpus.co_id, "ne", "dk-ne", "No Vector", first_seen=corpus.now, emb=None)
    s.add(bare)
    s.flush()
    assert client.get("/jobs/2147483000/similar").status_code == 404
    r = client.get(f"/jobs/{bare.id}/similar")
    assert r.status_code == 200 and r.json() == []


def test_similar_never_returns_a_vector_or_a_description(api, record_selects):  # noqa: F811
    """The source vector (4.7 KB as text) used to be fetched into Python only to be sent
    straight back as a bind parameter. It now stays inside the database, in the ORDER BY."""
    client, s = api
    corpus = _seed(s)
    with record_selects() as log:
        r = client.get(f"/jobs/{corpus.ids['gold']}/similar")
    assert r.status_code == 200 and len(r.json()) == 3
    assert log.with_column("apply_url"), "no neighbour cards were queried"
    log.assert_never_returned(*NOT_ON_A_CARD)


def test_similar_order_by_can_still_use_the_hnsw_index(api, record_selects):  # noqa: F811
    """EXPLAIN the exact statement the endpoint ran. On a test-sized table the planner would
    never pick the index on cost, so sequential scans, bitmap scans and sorts are switched
    off: the only ordered input left is the HNSW index, which it can use only if the ORDER BY
    is a distance to something it can treat as a constant."""
    client, s = api
    corpus = _seed(s)
    with record_selects() as log:
        assert client.get(f"/jobs/{corpus.ids['gold']}/similar").status_code == 200
    (neighbours,) = [rs for rs in log if "<=>" in rs.sql and "apply_url" in rs.columns]
    conn = s.get_bind()
    knobs = ("enable_seqscan", "enable_bitmapscan", "enable_sort")
    for knob in knobs:
        conn.exec_driver_sql(f"SET LOCAL {knob} = off")
    try:
        plan = "\n".join(r[0] for r in conn.exec_driver_sql("EXPLAIN " + neighbours.sql, neighbours.params))
    finally:
        for knob in knobs:
            conn.exec_driver_sql(f"RESET {knob}")
    assert "Index Scan using ix_jobs_embedding_hnsw on jobs" in plan, plan


# ── Fix 4: /meta aggregates in SQL instead of streaming location rows and timestamps ─────

def _seed_meta(s, corpus) -> None:
    """Enough roles per place for the metro filter (5+), raw variants of one metro, remote
    roles, places below the threshold, and boards checked at several ages."""
    places = (
        ["chicago, il"] * 3 + ["chicago, il, usa"] * 2      # 5 roles over 2 variants: listed
        + ["seattle, wa"] * 4                                 # 4: below the threshold
        + ["remote - us"] * 2 + ["new york, ny; remote"]      # remote in two spellings
        + ["Austin, TX"] * 6                                  # not lower-case: never matches
        + ["london"] * 5
    )
    for i, loc in enumerate(places):
        s.add(_job(corpus.co_id, f"m{i}", f"dk-m{i}", f"Meta Role {i}",
                   first_seen=corpus.now - timedelta(days=2), loc=loc))
    for i, hours in enumerate((1, 30, 200, None)):
        s.add(Company(name=f"Fresh{i}", ats=ATSSource.greenhouse, slug=f"egress-fresh-{i}", active=True,
                      last_ingested_at=None if hours is None else corpus.now - timedelta(hours=hours)))
    s.flush()


def _reference_locations(s) -> list[str]:
    """The pre-fix Python aggregation, kept as the oracle."""
    from app.routers.jobs import _LOCATION_MIN_COUNT, _MAJOR_METROS
    rows = s.execute(
        select(Job.location_normalized, func.count())
        .where(Job.is_active == True, Job.location_normalized != None)  # noqa: E711,E712
        .group_by(Job.location_normalized)
    ).all()
    remote = sum(cnt for loc, cnt in rows if "remote" in loc)
    present = sorted(d for d, tok in _MAJOR_METROS if sum(c for loc, c in rows if tok in loc) >= _LOCATION_MIN_COUNT)
    return (["remote"] + present) if remote else present


def _reference_freshness(s) -> dict:
    now = datetime.now(timezone.utc)
    stamps = s.execute(select(Company.last_ingested_at).where(Company.active == True)).scalars().all()  # noqa: E712
    checked = [t for t in stamps if t is not None]
    ages = sorted((now - t).total_seconds() / 3600 for t in checked)
    mid = len(ages) // 2
    median = (ages[mid] if len(ages) % 2 else (ages[mid - 1] + ages[mid]) / 2) if ages else None
    return dict(boards_active=len(stamps), boards_checked_24h=sum(a <= 24 for a in ages),
                boards_checked_7d=sum(a <= 168 for a in ages), median=median,
                oldest=min(checked) if checked else None)


def _assert_freshness(got: dict, ref: dict) -> None:
    assert got["boards_active"] == ref["boards_active"]
    assert got["boards_checked_24h"] == ref["boards_checked_24h"]
    assert got["boards_checked_7d"] == ref["boards_checked_7d"]
    if ref["median"] is None:
        assert got["median_check_age_hours"] is None and got["oldest_check_at"] is None
        return
    assert got["median_check_age_hours"] == pytest.approx(ref["median"], abs=0.11)
    assert datetime.fromisoformat(got["oldest_check_at"]) == ref["oldest"]


def test_meta_locations_and_freshness_are_unchanged(api):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    _seed_meta(s, corpus)
    body = client.get("/meta").json()
    assert body["locations"] == _reference_locations(s)
    assert "chicago, il" in body["locations"] and "seattle, wa" not in body["locations"]
    _assert_freshness(body["freshness"], _reference_freshness(s))
    run = s.execute(select(IngestRun).order_by(IngestRun.started_at.desc())).scalars().first()
    assert body["last_run"]["jobs_seen"] == run.jobs_seen and body["last_run"]["companies_ok"] == run.companies_ok


def test_meta_without_remote_roles_or_checked_boards(api):  # noqa: F811
    client, s = api
    s.add(Company(name="Lonely", ats=ATSSource.greenhouse, slug="egress-lonely", active=True))
    s.flush()
    body = client.get("/meta").json()
    assert body["locations"] == _reference_locations(s)
    _assert_freshness(body["freshness"], _reference_freshness(s))


def test_meta_never_streams_rows(api, record_selects):  # noqa: F811
    """No query behind /meta returns a row per location, per board or the run's failure list."""
    client, s = api
    corpus = _seed(s)
    _seed_meta(s, corpus)
    with record_selects() as log:
        assert client.get("/meta").status_code == 200
    log.assert_never_returned("location_normalized", "last_ingested_at", "failures")


# ── Fix 5: the sitemap only needs ids ─────────────────────────────────────────────────

def test_sitemap_returns_ids_without_timestamps(api, record_selects):  # noqa: F811
    client, s = api
    corpus = _seed(s)
    with record_selects() as log:
        body = client.get("/sitemap/jobs", params={"limit": 100}).json()
    active = {k for k in corpus.ids if k not in ("closed", "gold_ny")}
    assert [it["id"] for it in body["items"]] == sorted(corpus.ids[k] for k in active)
    assert body["total"] == len(active)
    log.assert_never_returned("last_seen_at")


# ── Fix 6: /status is cached long enough that crawlers cannot keep it hot ────────────────

def test_status_and_meta_cache_windows():
    from app.routers import jobs as jobs_router
    assert jobs_router._META_TTL_SECONDS >= 3600
    assert jobs_router._STATUS_TTL_SECONDS >= 900
