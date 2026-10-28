"""Anonymous public GETs are answered from a short in-process cache: an identical repeat
costs zero database queries (Neon compute and egress), per-user requests never touch it."""
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import event

from app.cache import TTLCache, configured_ttl, is_anonymous, normalized_key
from app.routers import jobs as jobs_router
from tests.test_design_api_db import _company, _job, api  # noqa: F401  (fixture)


# ── TTLCache unit behaviour (no database) ─────────────────────────────────────

class _Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def test_entry_expires_after_ttl():
    clock = _Clock()
    c = TTLCache(clock=clock)
    c.set("k", "v")
    assert c.get("k", ttl=60) == "v"
    clock.t += 59
    assert c.get("k", ttl=60) == "v"
    clock.t += 2
    assert c.get("k", ttl=60) is None and len(c) == 0


def test_size_is_bounded_and_least_recently_used_goes_first():
    c = TTLCache(max_entries=3)
    for k in "abc":
        c.set(k, k)
    c.get("a", ttl=60)           # a is now most recent
    c.set("d", "d")              # evicts b
    assert len(c) == 3
    assert c.get("b", ttl=60) is None and c.get("a", ttl=60) == "a"


def test_ttl_is_clamped_to_60_300_and_zero_disables(monkeypatch):
    for raw, want in (("5", 60), ("120", 120), ("9999", 300), ("0", 0), ("-1", 0)):
        monkeypatch.setenv("JOBS_CACHE_TTL_S", raw)
        assert configured_ttl() == want
    monkeypatch.delenv("JOBS_CACHE_TTL_S")
    assert configured_ttl() == 120


def test_key_ignores_order_case_of_names_blanks_and_defaults():
    a = normalized_key("/jobs", [("q", "intern"), ("Remote", "true")])
    b = normalized_key("/jobs", [("remote", "true"), ("q", " intern "), ("page", "1"),
                                 ("page_size", "20"), ("mode", "keyword"), ("company", "")])
    assert a == b
    assert a != normalized_key("/jobs", [("q", "intern"), ("remote", "true"), ("page", "2")])


def test_credentials_make_a_request_non_anonymous():
    assert is_anonymous({})
    assert not is_anonymous({"authorization": "Bearer x"})
    assert not is_anonymous({"cookie": "session=1"})


# ── through the real routes, counting statements sent to Postgres ─────────────

@contextmanager
def count_queries(engine):
    n = {"queries": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        if not statement.lstrip().upper().startswith("SET LOCAL"):
            n["queries"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield n
    finally:
        event.remove(engine, "before_cursor_execute", _before)


@pytest.fixture
def seeded(api, pg_engine):  # noqa: F811
    client, s = api
    co = _company(s, "CacheCo", "Software", "cache-co")
    now = datetime.now(timezone.utc)
    s.add_all([_job(co, f"c{i}", f"Software Intern {i}", first_seen=now) for i in range(3)])
    s.flush()
    jobs_router._JOBS_CACHE.clear()
    return client, pg_engine


def test_jobs_list_repeat_makes_zero_queries(seeded):
    client, eng = seeded
    with count_queries(eng) as first:
        r1 = client.get("/jobs?page_size=2")
    with count_queries(eng) as again:
        r2 = client.get("/jobs?page_size=2")
    print(f"MEASURED /jobs: first={first['queries']} queries, repeat={again['queries']}")
    assert r1.status_code == 200 and r2.json() == r1.json()
    assert first["queries"] > 0
    assert again["queries"] == 0


def test_equivalent_spellings_share_one_cache_entry(seeded):
    client, eng = seeded
    client.get("/jobs?page_size=2&remote=false")
    with count_queries(eng) as n:
        client.get("/jobs?remote=false&page=1&page_size=2&q=")
    assert n["queries"] == 0


def test_different_params_miss_and_credentialed_requests_bypass(seeded):
    client, eng = seeded
    client.get("/jobs?page_size=2")
    with count_queries(eng) as other:
        client.get("/jobs?page_size=3")
    assert other["queries"] > 0
    with count_queries(eng) as authed:
        client.get("/jobs?page_size=2", headers={"Authorization": "Bearer someone"})
    assert authed["queries"] > 0           # per-user requests never read the cache
    before = len(jobs_router._JOBS_CACHE)
    client.get("/jobs?page_size=5", headers={"Authorization": "Bearer someone"})
    assert len(jobs_router._JOBS_CACHE) == before  # ... and never write to it


def test_meta_and_status_repeat_make_zero_queries(seeded):
    client, eng = seeded
    for path in ("/meta", "/status"):
        client.get(path)
        with count_queries(eng) as again:
            r = client.get(path)
        print(f"MEASURED {path}: repeat={again['queries']} queries")
        assert r.status_code == 200 and again["queries"] == 0


def test_a_finished_ingest_run_drops_the_cached_lists(seeded):
    client, eng = seeded
    client.get("/jobs?page_size=2")
    jobs_router.invalidate_meta_cache()
    with count_queries(eng) as n:
        client.get("/jobs?page_size=2")
    assert n["queries"] > 0


def test_cache_off_switch(seeded, monkeypatch):
    client, eng = seeded
    monkeypatch.setenv("JOBS_CACHE_TTL_S", "0")
    client.get("/jobs?page_size=2")
    with count_queries(eng) as n:
        client.get("/jobs?page_size=2")
    assert n["queries"] > 0
