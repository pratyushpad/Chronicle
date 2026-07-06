import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ATSSource, Company, IngestRun, Job
from .adapters.ashby import AshbyAdapter
from .adapters.greenhouse import GreenhouseAdapter
from .adapters.lever import LeverAdapter
from .dedupe import make_dedup_key
from .normalize import (
    dedup_title,
    extract_salary,
    extract_tech_tags,
    infer_experience_level,
    infer_remote,
    infer_sponsorship,
    keying_title,
    normalize_department,
    normalize_location,
    normalize_title,
    parse_posted_at,
    strip_html,
)
from .registry import load_active_companies

log = logging.getLogger(__name__)

_ADAPTERS = {
    ATSSource.greenhouse: GreenhouseAdapter(),
    ATSSource.lever: LeverAdapter(),
    ATSSource.ashby: AshbyAdapter(),
}
_CONCURRENCY = 10


async def _ingest_company(
    company: Company,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    run_start: datetime,
    session: Session,
) -> dict:
    adapter = _ADAPTERS[company.ats]
    result = {"company_id": company.id, "jobs_seen": 0, "jobs_new": 0, "error": None}

    async with sem:
        for attempt in range(2):
            try:
                raw_jobs = await adapter.fetch(company.slug, client)
                break
            except Exception as exc:
                if attempt == 0:
                    await asyncio.sleep(2)
                else:
                    result["error"] = str(exc)
                    return result

    _CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    for raw in raw_jobs:
        posted = parse_posted_at(raw.posted_at)
        if posted is not None and posted < _CUTOFF:
            continue  # skip stale pre-2026 postings

        result["jobs_seen"] += 1
        t_norm = normalize_title(raw.title)
        l_norm = normalize_location(raw.location)
        # Key off keying_title (preserves the distinguishing team qualifier), NOT t_norm.
        dedup = make_dedup_key(company.id, dedup_title(keying_title(raw.title), l_norm))
        desc_text = strip_html(raw.description_html)
        sal_min, sal_max = extract_salary(desc_text)
        tags = extract_tech_tags(desc_text)
        sponsor = infer_sponsorship(desc_text)

        stmt = (
            insert(Job)
            .values(
                company_id=company.id,
                source=ATSSource(adapter.source),
                source_job_id=raw.source_job_id,
                title=raw.title,
                title_normalized=t_norm,
                location_raw=raw.location,
                location_normalized=l_norm,
                remote=infer_remote(raw),
                department=normalize_department(raw.department),
                department_raw=raw.department,
                employment_type=raw.employment_type,
                description_html=raw.description_html,
                description_text=desc_text,
                apply_url=raw.apply_url,
                posted_at=parse_posted_at(raw.posted_at),
                dedup_key=dedup,
                experience_level=infer_experience_level(raw.title),
                tech_tags=tags,
                salary_min=sal_min,
                salary_max=sal_max,
                sponsorship_flag=sponsor,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
            )
            .on_conflict_do_update(
                constraint="jobs_source_source_job_id_key",
                set_={"last_seen_at": now, "is_active": True, "tech_tags": tags, "sponsorship_flag": sponsor},
            )
        )
        inserted = session.execute(stmt)
        if inserted.rowcount and inserted.inserted_primary_key:
            result["jobs_new"] += 1

    session.commit()

    # Embed the rows we just inserted (embedding IS NULL). Best-effort:
    # a missing/broken model must never fail an ingest run.
    try:
        from app.ml.embed_jobs import embed_missing_jobs

        embed_missing_jobs(session, company_id=company.id)
    except Exception:
        log.exception("embedding failed for company %s (ingest itself succeeded)", company.slug)

    # Cross-source dedup: prefer earliest first_seen_at for same dedup_key
    # (handled via on_conflict: we keep existing first_seen_at untouched on update)

    return result


async def run_ingest(session: Session) -> IngestRun:
    run_start = datetime.now(tz=timezone.utc)
    run = IngestRun(started_at=run_start, failures=[])
    session.add(run)
    session.commit()
    session.refresh(run)

    companies = load_active_companies(session)
    run.companies_total = len(companies)
    session.commit()

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        tasks = [
            _ingest_company(c, client, sem, run_start, session)
            for c in companies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    jobs_seen = 0
    jobs_new = 0
    failures = []
    ok = 0

    for company, result in zip(companies, results):
        if isinstance(result, Exception):
            failures.append({
                "company": company.name,
                "ats": company.ats.value,
                "slug": company.slug,
                "error": str(result),
            })
            run.companies_failed += 1
        elif result.get("error"):
            failures.append({
                "company": company.name,
                "ats": company.ats.value,
                "slug": company.slug,
                "error": result["error"],
            })
            run.companies_failed += 1
        else:
            ok += 1
            jobs_seen += result["jobs_seen"]
            jobs_new += result["jobs_new"]
            session.execute(
                update(Company)
                .where(Company.id == company.id)
                .values(last_ingested_at=datetime.now(tz=timezone.utc))
            )

    # Mark closed roles: not seen in this run
    closed_result = session.execute(
        update(Job)
        .where(Job.last_seen_at < run_start, Job.is_active == True)
        .values(is_active=False)
    )
    jobs_closed = closed_result.rowcount

    run.companies_ok = ok
    run.jobs_seen = jobs_seen
    run.jobs_new = jobs_new
    run.jobs_closed = jobs_closed
    run.failures = failures
    run.finished_at = datetime.now(tz=timezone.utc)
    session.commit()

    log.info(
        "Ingest complete: %d/%d companies OK, %d new jobs, %d closed, %d failures",
        ok, len(companies), jobs_new, jobs_closed, len(failures),
    )
    return run
