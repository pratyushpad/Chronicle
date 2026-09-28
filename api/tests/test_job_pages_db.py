"""Job-page endpoints and the stored-description switch, against real Postgres
(TEST_DATABASE_URL; skips without). Hermetic: one outer transaction, rolled back."""
import asyncio
import html
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import runner
from app.ingest.adapters.base import RawJob
from app.ingest.dedupe import make_content_hash
from app.ingest.normalize import plain_text
from app.models import ATSSource, Company, Job
from app.routers.jobs import get_job, similar_jobs, sitemap_jobs
from tests.conftest import FIXTURES


def _session(conn) -> Session:
    s = Session(bind=conn)
    s.commit = s.flush
    s.rollback = lambda: None
    return s


def _vec(*head: float) -> list[float]:
    v = list(head) + [0.0] * (384 - len(head))
    return v


def _job(co, sid, dedup, emb=None, active=True, **kw):
    now = datetime.now(timezone.utc)
    return Job(
        company_id=co.id, source=ATSSource.greenhouse, source_job_id=sid,
        title=kw.pop("title", f"Role {sid}"), title_normalized="role", apply_url="https://example.com",
        dedup_key=dedup, first_seen_at=now, last_seen_at=now, is_active=active,
        embedding=emb, **kw,
    )


def test_similar_roles_are_nearest_active_distinct_roles(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            s = _session(conn)
            co = Company(name="SimCo", ats=ATSSource.greenhouse, slug="sim-co-test", active=True)
            s.add(co)
            s.flush()
            src = _job(co, "s0", "dk-src", _vec(1, 0))
            twin = _job(co, "s0b", "dk-src", _vec(1, 0))            # same role, another city
            near = _job(co, "s1", "dk-near", _vec(0.9, 0.1))
            near_dup = _job(co, "s1b", "dk-near", _vec(0.9, 0.1))   # duplicate of `near`
            mid = _job(co, "s2", "dk-mid", _vec(0.5, 0.5))
            closed = _job(co, "s3", "dk-closed", _vec(1, 0.01), active=False)
            unembedded = _job(co, "s4", "dk-none", None)
            s.add_all([src, twin, near, near_dup, mid, closed, unembedded])
            s.flush()

            got = similar_jobs(src.id, limit=4, session=s)
            ids = [j.id for j in got]
            assert ids[0] in (near.id, near_dup.id) and len(ids) == 2
            assert ids[1] == mid.id
            assert twin.id not in ids and closed.id not in ids and unembedded.id not in ids

            # A role with no embedding yet has no honest neighbours.
            assert similar_jobs(unembedded.id, limit=4, session=s) == []
        finally:
            outer.rollback()


def test_sitemap_lists_one_stable_url_per_active_role(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            s = _session(conn)
            before = sitemap_jobs(offset=0, limit=20_000, session=s).total
            co = Company(name="MapCo", ats=ATSSource.greenhouse, slug="map-co-test", active=True)
            s.add(co)
            s.flush()
            a1, a2 = _job(co, "m1", "dk-m-a"), _job(co, "m2", "dk-m-a")
            b = _job(co, "m3", "dk-m-b")
            gone = _job(co, "m4", "dk-m-c", active=False)
            s.add_all([a1, a2, b, gone])
            s.flush()
            res = sitemap_jobs(offset=0, limit=20_000, session=s)
            assert res.total == before + 2
            ids = {i.id for i in res.items}
            assert min(a1.id, a2.id) in ids and max(a1.id, a2.id) not in ids
            assert b.id in ids and gone.id not in ids
        finally:
            outer.rollback()


def test_detail_returns_blocks_and_plain_text(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            s = _session(conn)
            co = Company(name="DetCo", ats=ATSSource.greenhouse, slug="det-co-test", active=True)
            s.add(co)
            s.flush()
            job = _job(co, "d1", "dk-d1", description_text="<h3>What you'll do</h3><ul><li>Ship &amp; learn</li></ul>")
            s.add(job)
            s.flush()
            detail = get_job(job.id, session=s)
            assert detail.description_text == "What you'll do\nShip & learn"
            assert detail.description_blocks[0] == {
                "type": "heading", "level": 3, "content": [{"type": "text", "text": "What you'll do"}]}
            assert detail.description_blocks[1]["items"][0]["content"][0]["text"] == "Ship & learn"
            assert detail.description_summary == "What you'll do Ship & learn"
        finally:
            outer.rollback()


class _Adapter:
    source = "greenhouse"

    def __init__(self, raw):
        self.raw = raw

    async def fetch(self, slug, client):
        yield self.raw


def test_switching_a_legacy_row_to_the_new_format_keeps_its_embedding(pg_engine, monkeypatch):
    """A row stored as plain text by PR 1 code, re-ingested unchanged by PR 2 code, gets
    the structured description and keeps its vector: formatting never re-embeds."""
    jobs = json.loads((FIXTURES / "pr1_greenhouse.json").read_text())["jobs"]
    posting = next(j for j in jobs if j["title"] == "2027 Electrical Engineer Intern")
    body = html.unescape(posting["content"])
    raw = RawJob(
        source_job_id="fmt-1", title=posting["title"], location="Atlanta, GA",
        department="Hardware", employment_type=None, description_html=body,
        apply_url="https://example.com/fmt", posted_at="2026-06-11T17:00:56Z", remote=None,
        updated_at="2026-09-24T19:54:51Z",
    )
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            s = _session(conn)
            co = Company(name="FmtCo", ats=ATSSource.greenhouse, slug="fmt-co-test", active=True)
            s.add(co)
            s.flush()
            now = datetime.now(timezone.utc) - timedelta(days=1)
            s.add(Job(
                company_id=co.id, source=ATSSource.greenhouse, source_job_id="fmt-1",
                title=raw.title, title_normalized="x", apply_url=raw.apply_url, dedup_key="dk-fmt",
                first_seen_at=now, last_seen_at=now, is_active=True, embedding=_vec(0.3, 0.4),
                content_hash=make_content_hash(raw.title, raw.department, raw.location, plain_text(body)),
                description_text=plain_text(body)[:20_000],  # PR 1's stored form
            ))
            s.flush()
            monkeypatch.setattr(runner, "_ADAPTERS", {ATSSource.greenhouse: _Adapter(raw)})
            asyncio.run(runner._ingest_company(
                co, client=None, sem=asyncio.Semaphore(1),
                run_start=datetime.now(timezone.utc), session=s,
            ))
            s.expire_all()
            row = s.execute(select(Job).where(Job.source_job_id == "fmt-1")).scalar_one()
            assert row.description_text.startswith("<p>Anduril Industries")
            assert "<ul><li>" in row.description_text
            assert row.embedding is not None
        finally:
            outer.rollback()
