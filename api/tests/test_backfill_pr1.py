"""backfill_pr1 against real Postgres (TEST_DATABASE_URL; skips without).

Pins what the production run will do: it terminates (the first version's raw-SQL OR was
ANDed with the keyset predicate unparenthesized and returned the same batch forever),
fixes hourly pay stored x1000, clears salaries the old parser invented from non-pay
text, re-derives departments, nulls Greenhouse posted_at (it held updated_at), and never
touches content_hash or embedding. Hermetic: rolled back.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import backfill_pr1
from app.models import ATSSource, Company, Job

_VEC = [0.02] * 384


def _job(co, sid, source=ATSSource.greenhouse, **kw) -> Job:
    now = datetime.now(timezone.utc)
    base = dict(
        company_id=co.id, source=source, source_job_id=sid, title="Software Engineer Intern",
        title_normalized="software engineer intern", apply_url="https://x", dedup_key=f"dk-{sid}",
        first_seen_at=now, last_seen_at=now, is_active=True, content_hash="b" * 64, embedding=_VEC,
    )
    base.update(kw)
    return Job(**base)


def test_backfill_terminates_and_rewrites_only_what_it_should(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = Session(bind=conn)
            session.commit = session.flush  # hermetic
            co = Company(name="BackfillCo", ats=ATSSource.greenhouse, slug="backfill-co-test", active=True)
            session.add(co)
            session.flush()
            posted = datetime(2026, 9, 21, tzinfo=timezone.utc)
            session.add_all([
                # Anduril-style: hourly pay stored as $30k-45k/yr, program-label department.
                _job(co, "b1", department_raw="Internships", department="Other", posted_at=posted,
                     description_text="Compensation US Salary Range $30 — $45 USD The range is an estimate.",
                     salary_min=30000, salary_max=45000),
                # Complete text with no base pay: the legacy salary came from equity text.
                _job(co, "b2", department_raw="Engineering", department="Engineering",
                     description_text="Join us. Equity grant of $40k over four years.",
                     salary_min=40000, salary_max=None),
                # Annual salary that was already right stays right.
                _job(co, "b3", department_raw="Engineering", department="Engineering",
                     description_text="The base salary range is $150,000 - $190,000 per year.",
                     salary_min=150000, salary_max=190000),
                # No money at all: untouched by the pay pass; Lever keeps its posted_at.
                _job(co, "b4", source=ATSSource.lever, department_raw="Internships", department="Other",
                     title="Accounting Intern", description_text="Help close the books.", posted_at=posted),
            ])
            session.flush()

            stats = backfill_pr1.run(apply=True, batch=2, session=session)  # batch=2 → many pages
            assert stats["scanned"] >= 4

            rows = {j.source_job_id: j for j in session.execute(
                select(Job).where(Job.company_id == co.id)).scalars()}
            for j in rows.values():
                session.refresh(j)

            b1 = rows["b1"]
            assert (float(b1.pay_min), float(b1.pay_max), b1.pay_currency, b1.pay_period) == (30.0, 45.0, "USD", "hour")
            assert (b1.salary_min, b1.salary_max) == (62400, 93600)  # annualized sort keys, not "$30k"
            assert b1.department == "Engineering"
            assert b1.posted_at is None  # greenhouse updated_at cleared

            b2 = rows["b2"]
            assert b2.salary_min is None and b2.pay_period is None  # invented salary cleared

            b3 = rows["b3"]
            assert (b3.salary_min, b3.salary_max, b3.pay_period) == (150000, 190000, "year")

            b4 = rows["b4"]
            assert b4.department == "Finance"
            assert b4.posted_at == posted  # lever createdAt is a real publish time — kept

            for j in rows.values():  # nothing is ever queued for re-embedding
                assert j.content_hash == "b" * 64 and j.embedding is not None
        finally:
            outer.rollback()


def test_dry_run_writes_nothing(pg_engine):
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            session = Session(bind=conn)
            session.commit = session.flush
            co = Company(name="DryCo", ats=ATSSource.greenhouse, slug="dry-co-test", active=True)
            session.add(co)
            session.flush()
            session.add(_job(co, "d1", department_raw="Internships", department="Other",
                             description_text="$45-$70 per hour", salary_min=45000, salary_max=70000))
            session.flush()
            stats = backfill_pr1.run(apply=False, batch=10, session=session)
            assert stats["dept_changed"] >= 1 and stats["pay_set"] >= 1
            job = session.execute(select(Job).where(Job.company_id == co.id)).scalar_one()
            session.refresh(job)
            assert job.department == "Other" and job.salary_min == 45000 and job.pay_min is None
        finally:
            outer.rollback()
