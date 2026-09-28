"""The upsert keeps an unchanged description in place (no new TOAST copy), against real
Postgres (TEST_DATABASE_URL; skips without)."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ingest import runner
from app.ingest.adapters.base import RawJob
from app.models import ATSSource, Company, Job


class _Adapter:
    source = "greenhouse"

    def __init__(self, raw):
        self.raw = raw

    async def fetch(self, slug, client):
        yield self.raw


def _raw(desc: str) -> RawJob:
    return RawJob(source_job_id="toast-1", title="Intern", location="Austin, TX", department=None,
                  employment_type=None, description_html=f"<p>{desc}</p>", apply_url="https://e.test",
                  posted_at=None, remote=None, updated_at="2026-09-01T00:00:00Z")


def test_unchanged_description_keeps_its_toast_value(pg_engine, monkeypatch):
    """An unchanged posting must not write a new TOAST copy of its description; a changed
    one must. Read directly from the jobs table's TOAST relation (Postgres 16 has no
    pg_column_toast_chunk_id)."""
    import random

    rng = random.Random(7)  # incompressible text, so it is stored out of line
    body = " ".join("".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8)) for _ in range(1500))  # ~13.5k chars: under the 20k cap
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            s = Session(bind=conn)
            s.commit = s.flush
            s.rollback = lambda: None
            co = Company(name="ToastCo", ats=ATSSource.greenhouse, slug="toast-co-test", active=True)
            s.add(co)
            s.flush()
            toast = conn.execute(text(
                "SELECT reltoastrelid::regclass::text FROM pg_class WHERE relname = 'jobs'")).scalar_one()

            def ingest(desc):
                monkeypatch.setattr(runner, "_ADAPTERS", {ATSSource.greenhouse: _Adapter(_raw(desc))})
                asyncio.run(runner._ingest_company(co, client=None, sem=asyncio.Semaphore(1),
                                                   run_start=datetime.now(timezone.utc), session=s))

            def toast_values():
                # Physical locations of the visible TOAST chunks. Writing a copy (even of the
                # same value, even when Postgres reuses the value id) puts new chunk rows at new
                # ctids and hides the old ones, so the set changes iff a copy was written.
                return set(conn.execute(text(f"SELECT ctid::text FROM {toast}")).scalars())

            ingest(body)
            after_insert = toast_values()
            assert after_insert
            ingest(body)  # unchanged: the same TOAST value is kept
            assert toast_values() == after_insert
            ingest(body + " edited")  # changed: a new TOAST value replaces it
            assert toast_values() != after_insert
            desc = s.execute(select(Job.description_text).where(Job.source_job_id == "toast-1")).scalar_one()
            assert desc.endswith("edited</p>")
        finally:
            outer.rollback()

