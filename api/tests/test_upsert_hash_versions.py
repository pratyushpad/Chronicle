"""The upsert's embedding rule, against real Postgres (TEST_DATABASE_URL; skips without).

A row carrying a legacy (all-hex) or NULL content hash ADOPTS the v2 hash and KEEPS its
embedding — changing the hash definition must never re-embed the corpus. Between two v2
hashes, a real content change nulls the embedding so only that row re-embeds. Also pins
the age expression: LEAST(posted_at, first_seen_at), NULL posted_at falling back.

Hermetic: one outer transaction, rolled back; the runner's commits become flushes.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import runner
from app.ingest.adapters.base import RawJob
from app.models import ATSSource, Company, Job
from app.routers.jobs import JOB_AGE

_VEC = [0.01] * 384


def _raw(desc: str) -> RawJob:
    return RawJob(
        source_job_id="hv-1", title="Software Engineer Intern", location="Austin, TX",
        department="Engineering", employment_type=None, description_html=f"<p>{desc}</p>",
        apply_url="https://example.com/1", posted_at="2026-06-01T00:00:00Z", remote=None,
        updated_at="2026-09-01T00:00:00Z",
    )


class _Adapter:
    source = "greenhouse"

    def __init__(self, raw: RawJob):
        self.raw = raw

    async def fetch(self, slug, client):
        yield self.raw


def _ingest(session: Session, company: Company, raw: RawJob, monkeypatch) -> None:
    monkeypatch.setattr(runner, "_ADAPTERS", {ATSSource.greenhouse: _Adapter(raw)})
    import app.ml.embed_jobs as ej

    monkeypatch.setattr(ej, "embed_missing_jobs", lambda *a, **k: 0)
    asyncio.run(runner._ingest_company(
        company, client=None, sem=asyncio.Semaphore(1),
        run_start=datetime.now(timezone.utc), session=session,
    ))


def _session(conn) -> Session:
    s = Session(bind=conn)
    s.commit = s.flush  # hermetic
    s.rollback = lambda: None
    return s


def test_legacy_hash_is_adopted_without_re_embedding_then_v2_changes_re_embed(pg_engine, monkeypatch):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = _session(conn)
            co = Company(name="HashCo", ats=ATSSource.greenhouse, slug="hash-co-test", active=True)
            session.add(co)
            session.flush()
            now = datetime.now(timezone.utc)
            session.add(Job(
                company_id=co.id, source=ATSSource.greenhouse, source_job_id="hv-1",
                title="Software Engineer Intern", title_normalized="software engineer intern",
                apply_url="https://example.com/1", dedup_key="dk-hv-1", first_seen_at=now,
                last_seen_at=now, is_active=True, content_hash="a" * 64, embedding=_VEC,
                description_text="old flattened text",
            ))
            session.flush()

            # Same posting, first ingest with v2 code: hash adopted, vector kept.
            _ingest(session, co, _raw("Build things with Python."), monkeypatch)
            job = session.execute(select(Job).where(Job.source_job_id == "hv-1")).scalar_one()
            session.refresh(job)
            assert job.content_hash.startswith("v2")
            assert job.embedding is not None
            assert job.description_text == "Build things with Python."  # legacy text rewritten once
            first_v2 = job.content_hash

            # Identical re-ingest: stable hash, vector kept.
            _ingest(session, co, _raw("Build things with Python."), monkeypatch)
            session.refresh(job)
            assert job.content_hash == first_v2 and job.embedding is not None

            # Real content change between two v2 hashes: vector nulled for re-embedding.
            _ingest(session, co, _raw("Build different things with Rust."), monkeypatch)
            session.refresh(job)
            assert job.content_hash != first_v2
            assert job.embedding is None
        finally:
            outer.rollback()


def test_null_stored_hash_keeps_embedding(pg_engine, monkeypatch):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = _session(conn)
            co = Company(name="HashCo2", ats=ATSSource.greenhouse, slug="hash-co-test-2", active=True)
            session.add(co)
            session.flush()
            now = datetime.now(timezone.utc)
            session.add(Job(
                company_id=co.id, source=ATSSource.greenhouse, source_job_id="hv-1",
                title="Software Engineer Intern", title_normalized="software engineer intern",
                apply_url="https://example.com/1", dedup_key="dk-hv-2", first_seen_at=now,
                last_seen_at=now, is_active=True, content_hash=None, embedding=_VEC,
            ))
            session.flush()
            _ingest(session, co, _raw("Anything."), monkeypatch)
            job = session.execute(select(Job).where(Job.company_id == co.id)).scalar_one()
            session.refresh(job)
            assert job.content_hash.startswith("v2") and job.embedding is not None
        finally:
            outer.rollback()


def test_age_is_least_of_posted_and_first_seen(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = Session(bind=conn)
            co = Company(name="AgeCo", ats=ATSSource.greenhouse, slug="age-co-test", active=True)
            session.add(co)
            session.flush()
            now = datetime.now(timezone.utc)

            def job(sid, posted, seen):
                return Job(company_id=co.id, source=ATSSource.greenhouse, source_job_id=sid,
                           title=sid, title_normalized=sid, apply_url="https://x", dedup_key=f"dk-{sid}",
                           posted_at=posted, first_seen_at=seen, last_seen_at=now, is_active=True)

            session.add_all([
                job("republished", now, now - timedelta(days=30)),   # posted after first seen → 30d
                job("unknown", None, now - timedelta(days=2)),        # no publish date → 2d
                job("real", now - timedelta(days=10), now),           # true publish date → 10d
            ])
            session.flush()
            order = session.execute(
                select(Job.source_job_id).where(Job.company_id == co.id).order_by(JOB_AGE.desc())
            ).scalars().all()
            assert order == ["unknown", "real", "republished"]
        finally:
            outer.rollback()


def test_listing_only_role_drops_its_stored_description_and_embedding(pg_engine, monkeypatch):
    """A senior role is a listing only: its next ingest clears the stored description and
    embedding (freeing the space) but keeps the row listed."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = _session(conn)
            co = Company(name="ScopeCo", ats=ATSSource.greenhouse, slug="scope-co-test", active=True)
            session.add(co)
            session.flush()
            now = datetime.now(timezone.utc)
            session.add(Job(
                company_id=co.id, source=ATSSource.greenhouse, source_job_id="hv-1",
                title="Senior Software Engineer", title_normalized="senior software engineer",
                apply_url="https://example.com/1", dedup_key="dk-scope-1", first_seen_at=now,
                last_seen_at=now, is_active=True, content_hash="b" * 64, embedding=_VEC,
                description_text="a long stored description",
            ))
            session.flush()

            raw = _raw("Lead our search team.")
            raw.title = "Senior Software Engineer"
            _ingest(session, co, raw, monkeypatch)
            job = session.execute(select(Job).where(Job.source_job_id == "hv-1")).scalar_one()
            session.refresh(job)
            assert job.is_active
            assert job.description_text is None
            assert job.embedding is None
        finally:
            outer.rollback()


def test_description_is_rewritten_only_when_its_text_changes(pg_engine, monkeypatch):
    """The stored description is kept when the new text is identical (no TOAST rewrite) and
    replaced whenever it differs, even under the same content hash: a row stored as a
    listing (NULL) whose title is now in scope gets its text back, then its embedding."""
    from app.ingest.dedupe import make_content_hash
    from app.ingest.normalize import plain_text

    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = _session(conn)
            co = Company(name="KeepCo", ats=ATSSource.greenhouse, slug="keep-co-test", active=True)
            session.add(co)
            session.flush()
            raw = _raw("Build things with Python.")
            same_hash = make_content_hash(raw.title, raw.department, raw.location,
                                          plain_text(raw.description_html))
            now = datetime.now(timezone.utc)
            session.add(Job(
                company_id=co.id, source=ATSSource.greenhouse, source_job_id="hv-1",
                title=raw.title, title_normalized="software engineer intern",
                apply_url="https://example.com/1", dedup_key="dk-keep-1", first_seen_at=now,
                last_seen_at=now, is_active=True, content_hash=same_hash, embedding=None,
                description_text=None,
            ))
            session.flush()

            _ingest(session, co, raw, monkeypatch)
            job = session.execute(select(Job).where(Job.source_job_id == "hv-1")).scalar_one()
            session.refresh(job)
            assert job.description_text == "Build things with Python."  # restored
            assert job.embedding is None  # so embed_jobs (description present) embeds it

            _ingest(session, co, raw, monkeypatch)
            session.refresh(job)
            assert job.description_text == "Build things with Python."  # unchanged: kept

            _ingest(session, co, _raw("Build different things with Rust."), monkeypatch)
            session.refresh(job)
            assert job.description_text == "Build different things with Rust."
        finally:
            outer.rollback()
