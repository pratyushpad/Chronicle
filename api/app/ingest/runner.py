import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ATSSource, Company, IngestRun, Job
from .adapters.ashby import AshbyAdapter
from .adapters.greenhouse import GreenhouseAdapter
from .adapters.lever import LeverAdapter
from .dedupe import make_content_hash, make_dedup_key
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
# Low concurrency so at most this many boards' responses are in memory at once —
# keeps the ingest within Render's 512MB free tier (10-wide OOM'd the instance).
_CONCURRENCY = 3


async def _ingest_company(
    company: Company,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    run_start: datetime,
    session: Session,
    deadline: datetime | None = None,
) -> dict:
    adapter = _ADAPTERS[company.ats]
    result = {"company_id": company.id, "jobs_seen": 0, "jobs_new": 0, "error": None, "skipped": False}

    # Runtime-budget checkpoint (C3): once the run is over budget, stop fetching new
    # boards. Skipped companies keep their old last_ingested_at, so the staleness
    # ordering picks them first on the next scheduled run — the corpus refreshes in
    # chunks across invocations without ever leaving the DB half-written.
    if deadline is not None and datetime.now(tz=timezone.utc) >= deadline:
        result["skipped"] = True
        return result

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
        dept = normalize_department(raw.department)
        chash = make_content_hash(raw.title, desc_text, l_norm, dept, tags)

        ins = insert(Job).values(
            company_id=company.id,
            source=ATSSource(adapter.source),
            source_job_id=raw.source_job_id,
            title=raw.title,
            title_normalized=t_norm,
            location_raw=raw.location,
            location_normalized=l_norm,
            remote=infer_remote(raw),
            department=dept,
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
            content_hash=chash,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        )
        # On re-ingest, refresh the mutable content fields, and when the content hash
        # changed (title/description/location/dept/tags), null the embedding so
        # embed_missing_jobs re-embeds only that row — delta-only, never the whole corpus.
        content_changed = Job.content_hash.is_distinct_from(ins.excluded.content_hash)
        stmt = ins.on_conflict_do_update(
            constraint="jobs_source_source_job_id_key",
            set_={
                "last_seen_at": now,
                "is_active": True,
                "title": raw.title,
                "title_normalized": t_norm,
                "location_raw": raw.location,
                "location_normalized": l_norm,
                "department": dept,
                "department_raw": raw.department,
                "employment_type": raw.employment_type,
                "description_html": raw.description_html,
                "description_text": desc_text,
                "apply_url": raw.apply_url,
                "posted_at": parse_posted_at(raw.posted_at),
                "experience_level": infer_experience_level(raw.title),
                "tech_tags": tags,
                "salary_min": sal_min,
                "salary_max": sal_max,
                "sponsorship_flag": sponsor,
                "content_hash": chash,
                "embedding": case((content_changed, None), else_=Job.embedding),
            },
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


async def run_ingest(session: Session, budget_seconds: int | None = None) -> IngestRun:
    """Incremental, idempotent ingest of all active boards.

    Idempotent: upsert on (source, source_job_id) means running twice back-to-back
    creates no duplicates and (via content_hash) re-embeds nothing unchanged. Companies
    are processed stalest-first (last_ingested_at ASC), and if budget_seconds is given the
    run stops fetching new boards past that wall-clock budget — the rest refresh on the
    next scheduled run. Per-company commits mean the DB is never left half-written.
    """
    run_start = datetime.now(tz=timezone.utc)
    deadline = run_start + timedelta(seconds=budget_seconds) if budget_seconds else None
    run = IngestRun(started_at=run_start, failures=[])
    session.add(run)
    session.commit()
    session.refresh(run)

    companies = load_active_companies(session, stale_first=True)
    run.companies_total = len(companies)
    session.commit()

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        tasks = [
            _ingest_company(c, client, sem, run_start, session, deadline=deadline)
            for c in companies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    jobs_seen = 0
    jobs_new = 0
    failures = []
    ok = 0
    skipped = 0
    ok_ids: list[int] = []

    for company, result in zip(companies, results):
        if isinstance(result, Exception):
            failures.append({
                "company": company.name,
                "ats": company.ats.value,
                "slug": company.slug,
                "error": str(result),
            })
            run.companies_failed += 1
        elif result.get("skipped"):
            skipped += 1  # over budget — left for the next run, last_ingested_at untouched
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
            ok_ids.append(company.id)
            jobs_seen += result["jobs_seen"]
            jobs_new += result["jobs_new"]
            session.execute(
                update(Company)
                .where(Company.id == company.id)
                .values(last_ingested_at=datetime.now(tz=timezone.utc))
            )

    # Soft-close vanished roles — but ONLY for companies we actually fetched this run.
    # A board that timed out or errored must never deactivate its jobs (they'd flip back
    # active next run, churning the corpus and the "closed" counts). Scoping to ok_ids is
    # what makes soft-close safe at 1000+ boards where transient failures are routine.
    jobs_closed = 0
    if ok_ids:
        closed_result = session.execute(
            update(Job)
            .where(
                Job.company_id.in_(ok_ids),
                Job.last_seen_at < run_start,
                Job.is_active == True,
            )
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

    # Rolling stale-posting prune (B3): keep only active + recently-closed roles hot so
    # the corpus stays within Neon's free storage budget. Best-effort — a prune failure
    # must never fail the ingest run.
    try:
        from .prune import prune_stale_jobs

        prune_stale_jobs(session)
    except Exception:
        log.exception("stale-job prune failed (ingest itself succeeded)")

    # A fresh run changes /meta's inputs; drop its in-process cache so the "Updated …"
    # label and "NEW SINCE LAST RUN" counts reflect this run immediately (C4).
    try:
        from app.routers.jobs import invalidate_meta_cache

        invalidate_meta_cache()
    except Exception:
        log.debug("meta cache invalidation skipped", exc_info=True)

    log.info(
        "Ingest complete: %d/%d companies OK, %d skipped (budget), %d new jobs, %d closed, %d failures",
        ok, len(companies), skipped, jobs_new, jobs_closed, len(failures),
    )
    return run
