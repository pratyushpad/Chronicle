"""Anonymous public GETs are answered from a short in-process cache: an identical repeat
costs zero database queries (Neon compute and egress), per-user requests never touch it."""
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import event

from app.cache import TTLCache, bound_key, configured_ttl, is_anonymous, raw_query_is_plain
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


def test_bound_key_is_case_and_whitespace_sensitive_and_skips_request_objects():
    base = {"q": "x", "page": 1, "request": object(), "session": object()}
    assert bound_key("/jobs", base) == bound_key("/jobs", {**base, "request": object()})
    assert bound_key("/jobs", base) != bound_key("/jobs", {**base, "q": "X"})
    assert bound_key("/jobs", base) != bound_key("/jobs", {**base, "q": " x"})
    assert bound_key("/jobs", base) != bound_key("/jobs", {**base, "page": 2})


def test_plain_query_check():
    names = {"q", "page", "request"}
    assert raw_query_is_plain([("q", "x"), ("page", "2")], names)
    assert not raw_query_is_plain([("Q", "x")], names)                 # unknown spelling
    assert not raw_query_is_plain([("q", "a"), ("q", "b")], names)     # repeated
    assert not raw_query_is_plain([("zzz", "1")], names)               # unknown


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


def test_default_valued_spellings_share_one_entry(seeded):
    client, eng = seeded
    client.get("/jobs?page_size=2")
    with count_queries(eng) as n:
        client.get("/jobs?page_size=2&page=1&mode=keyword")  # bound args identical
    assert n["queries"] == 0


def _titles(r):
    return [i["title"] for i in r.json()["items"]]


def test_case_variant_name_cannot_read_or_poison_another_entry(seeded):
    client, eng = seeded
    a = client.get("/jobs?q=Intern%201&page_size=5")          # filtered to one role
    plain = client.get("/jobs?page_size=5")                    # all three roles
    wrong = client.get("/jobs?Q=Intern%201&page_size=5")       # unknown name: q is ignored
    assert len(_titles(a)) == 1 and len(_titles(plain)) == 3
    assert _titles(wrong) == _titles(plain)                    # not the ?q= body
    assert _titles(client.get("/jobs?q=Intern%201&page_size=5")) == _titles(a)
    assert _titles(client.get("/jobs?page_size=5")) == _titles(plain)


def test_repeated_params_are_not_cached(seeded):
    client, eng = seeded
    r1 = client.get("/jobs?q=Intern%201&q=Intern%202&page_size=5")
    with count_queries(eng) as n:
        r2 = client.get("/jobs?q=Intern%201&q=Intern%202&page_size=5")
    assert n["queries"] > 0 and r1.json() == r2.json()
    assert len(_titles(client.get("/jobs?q=Intern%201&page_size=5"))) == 1  # not poisoned


def test_whitespace_padded_value_is_its_own_entry(seeded):
    client, eng = seeded
    padded = client.get("/jobs?company=%20CacheCo&page_size=5")   # ILIKE '% CacheCo%': no match
    exact = client.get("/jobs?company=CacheCo&page_size=5")
    assert _titles(padded) == [] and len(_titles(exact)) == 3
    assert _titles(client.get("/jobs?company=%20CacheCo&page_size=5")) == []
    assert len(_titles(client.get("/jobs?company=CacheCo&page_size=5"))) == 3


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
