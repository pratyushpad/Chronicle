from datetime import date, datetime, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Company, IngestRun, Job
from app.util import root_domain
from app.schemas import (
    CompanyDetail,
    CompanyItem,
    IndustryCount,
    JobDetail,
    JobListItem,
    JobListResponse,
    LastRunSummary,
    MetaResponse,
)

# Title keywords used to bucket senior-level roles when experience_level is blank.
_SENIOR_REGEX = r"\m(senior|sr|staff|principal|lead|distinguished|architect)\M"

router = APIRouter()


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


# Quick-filter "level" pills map experience_level OR a title keyword, because
# experience_level is sparsely populated (most jobs leave it blank).
# `title_regex` uses Postgres word boundaries (\m \M) so "Intern"/"Internship"
# match but "International"/"Internal" do not.
_LEVEL_FILTERS: dict[str, dict] = {
    "intern": {
        "experience_level": "Internship",
        "title_regex": r"\mintern(ship)?s?\M",
    },
    "new_grad": {
        "experience_level": "Entry Level",
        "title_patterns": ["%new grad%", "%new graduate%", "%university grad%", "%entry level%"],
    },
}


def _last_run_start(session: Session) -> datetime | None:
    return session.execute(
        select(IngestRun.started_at).order_by(IngestRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    q: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    company_id: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    remote: Optional[bool] = Query(None),
    employment_type: Optional[str] = Query(None),
    experience_level: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    posted_after: Optional[date] = Query(None),
    since_last_run: bool = Query(False),
    sort: str = Query("posted_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(_db),
):
    last_start = _last_run_start(session)
    order_col = Job.posted_at if sort == "posted_at" else Job.first_seen_at

    # All filter statements join Company because several filters reference it.
    def _apply_filters(s):
        if q:
            s = s.where(Job.title.ilike(f"%{q}%"))
        if company:
            s = s.where(Company.name.ilike(f"%{company}%"))
        if company_id:
            s = s.where(Job.company_id == company_id)
        if department:
            s = s.where(Job.department.ilike(f"%{department}%"))
        if location:
            s = s.where(Job.location_normalized.ilike(f"%{location}%"))
        if remote is not None:
            s = s.where(Job.remote == remote)
        if employment_type:
            s = s.where(Job.employment_type.ilike(f"%{employment_type}%"))
        if experience_level:
            s = s.where(Job.experience_level.ilike(f"%{experience_level}%"))
        if level and level in _LEVEL_FILTERS:
            cfg = _LEVEL_FILTERS[level]
            conds = [Job.experience_level == cfg["experience_level"]]
            if cfg.get("title_regex"):
                conds.append(Job.title.op("~*")(cfg["title_regex"]))
            conds += [Job.title.ilike(pat) for pat in cfg.get("title_patterns", [])]
            s = s.where(or_(*conds))
        if industry:
            s = s.where(Company.industry.ilike(f"%{industry}%"))
        if posted_after:
            s = s.where(Job.posted_at >= datetime(posted_after.year, posted_after.month, posted_after.day, tzinfo=timezone.utc))
        if since_last_run and last_start:
            s = s.where(Job.first_seen_at >= last_start)
        return s

    base = lambda *cols: _apply_filters(select(*cols).join(Company).where(Job.is_active == True))

    # Total = distinct roles, collapsing cross-posted city duplicates.
    keys_sub = base(Job.dedup_key).subquery()
    total = session.execute(
        select(func.count(func.distinct(keys_sub.c.dedup_key)))
    ).scalar_one()

    # One representative row per dedup_key (the most recent posting), then page
    # those representatives ordered by recency.
    rep_ids = (
        base(Job.id, Job.dedup_key)
        .distinct(Job.dedup_key)
        .order_by(Job.dedup_key, order_col.desc().nullslast())
    ).subquery()
    page_stmt = (
        select(Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Company)
        .where(Job.id.in_(select(rep_ids.c.id)))
        .order_by(order_col.desc().nullslast(), Job.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = session.execute(page_stmt).all()

    # Aggregate the sibling locations for each role on this page.
    keys = [row.Job.dedup_key for row in rows]
    loc_map: dict[str, list[str]] = {}
    if keys:
        for k, locs in session.execute(
            select(Job.dedup_key, func.array_agg(func.distinct(Job.location_normalized)))
            .where(Job.dedup_key.in_(keys), Job.is_active == True, Job.location_normalized != None)
            .group_by(Job.dedup_key)
        ).all():
            loc_map[k] = sorted(l for l in (locs or []) if l)

    items = []
    for row in rows:
        job = row.Job
        is_new = bool(last_start and job.first_seen_at >= last_start)
        locs = loc_map.get(job.dedup_key, [])
        items.append(
            JobListItem(
                id=job.id,
                title=job.title,
                company_name=row.company_name,
                company_id=job.company_id,
                company_domain=root_domain(row.company_careers_url),
                location_normalized=job.location_normalized,
                locations=locs or None,
                location_count=len(locs) or None,
                remote=job.remote,
                department=job.department,
                employment_type=job.employment_type,
                experience_level=job.experience_level,
                tech_tags=job.tech_tags,
                sponsorship_flag=job.sponsorship_flag,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                posted_at=job.posted_at,
                first_seen_at=job.first_seen_at,
                apply_url=job.apply_url,
                is_new=is_new,
            )
        )

    return JobListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, ceil(total / page_size)),
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: int, session: Session = Depends(_db)):
    row = session.execute(
        select(Job, Company.name.label("company_name"), Company.industry.label("company_industry"))
        .join(Company)
        .where(Job.id == job_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    job = row.Job
    return JobDetail(
        id=job.id,
        title=job.title,
        company_name=row.company_name,
        company_id=job.company_id,
        company_industry=row.company_industry,
        location_raw=job.location_raw,
        location_normalized=job.location_normalized,
        remote=job.remote,
        department=job.department,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        description_text=job.description_text,
        apply_url=job.apply_url,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
    )


@router.get("/companies", response_model=list[CompanyItem])
def list_companies(
    industry: Optional[str] = Query(None),
    session: Session = Depends(_db),
):
    stmt = (
        select(Company, func.count(func.distinct(Job.dedup_key)).label("active_job_count"))
        .outerjoin(Job, (Job.company_id == Company.id) & (Job.is_active == True))
        .where(Company.active == True)
        .group_by(Company.id)
        .order_by(Company.name)
    )
    if industry:
        stmt = stmt.where(Company.industry.ilike(f"%{industry}%"))
    rows = session.execute(stmt).all()
    return [
        CompanyItem(
            id=row.Company.id,
            name=row.Company.name,
            ats=row.Company.ats.value,
            careers_url=row.Company.careers_url,
            industry=row.Company.industry,
            active_job_count=row.active_job_count,
        )
        for row in rows
    ]


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, session: Session = Depends(_db)):
    row = session.execute(
        select(Company, func.count(func.distinct(Job.dedup_key)).label("active_job_count"))
        .outerjoin(Job, (Job.company_id == Company.id) & (Job.is_active == True))
        .where(Company.id == company_id, Company.active == True)
        .group_by(Company.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyDetail(
        id=row.Company.id,
        name=row.Company.name,
        ats=row.Company.ats.value,
        careers_url=row.Company.careers_url,
        industry=row.Company.industry,
        active_job_count=row.active_job_count,
        last_ingested_at=row.Company.last_ingested_at,
    )


@router.get("/meta", response_model=MetaResponse)
def get_meta(session: Session = Depends(_db)):
    def distinct_col(col):
        return [
            r[0]
            for r in session.execute(
                select(col).where(Job.is_active == True, col != None).distinct().order_by(col)
            ).all()
        ]

    industries = [
        r[0]
        for r in session.execute(
            select(Company.industry).where(Company.active == True, Company.industry != None).distinct().order_by(Company.industry)
        ).all()
    ]

    total_active = session.execute(
        select(func.count(func.distinct(Job.dedup_key))).select_from(Job).where(Job.is_active == True)
    ).scalar_one()
    total_companies = session.execute(
        select(func.count()).select_from(Company).where(Company.active == True)
    ).scalar_one()

    last_run_row = session.execute(
        select(IngestRun).order_by(IngestRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()

    last_run = None
    if last_run_row:
        last_run = LastRunSummary(
            started_at=last_run_row.started_at,
            jobs_seen=last_run_row.jobs_seen,
            jobs_new=last_run_row.jobs_new,
            companies_ok=last_run_row.companies_ok,
            companies_failed=last_run_row.companies_failed,
        )

    # ── Landing-page aggregates ──────────────────────────────────────────────
    def _count(*conds) -> int:
        return session.execute(
            select(func.count(func.distinct(Job.dedup_key))).select_from(Job).where(Job.is_active == True, *conds)
        ).scalar_one()

    last_start = _last_run_start(session)
    fresh_since_last_run = _count(Job.first_seen_at >= last_start) if last_start else 0
    remote_count = _count(Job.remote == True)

    def _level_count(level: str) -> int:
        cfg = _LEVEL_FILTERS[level]
        conds = [Job.experience_level == cfg["experience_level"]]
        if cfg.get("title_regex"):
            conds.append(Job.title.op("~*")(cfg["title_regex"]))
        conds += [Job.title.ilike(pat) for pat in cfg.get("title_patterns", [])]
        return _count(or_(*conds))

    experience_counts = {
        "intern": _level_count("intern"),
        "new_grad": _level_count("new_grad"),
        "senior": _count(
            or_(Job.experience_level == "Senior", Job.title.op("~*")(_SENIOR_REGEX))
        ),
    }

    top_industry_rows = session.execute(
        select(Company.industry, func.count(func.distinct(Job.dedup_key)))
        .join(Job, (Job.company_id == Company.id) & (Job.is_active == True))
        .where(Company.active == True, Company.industry != None)
        .group_by(Company.industry)
        .order_by(func.count(func.distinct(Job.dedup_key)).desc())
        .limit(8)
    ).all()
    top_industries = [IndustryCount(industry=r[0], count=r[1]) for r in top_industry_rows]

    return MetaResponse(
        departments=distinct_col(Job.department),
        locations=distinct_col(Job.location_normalized),
        employment_types=distinct_col(Job.employment_type),
        experience_levels=distinct_col(Job.experience_level),
        industries=industries,
        last_run=last_run,
        total_active_jobs=total_active,
        total_companies=total_companies,
        fresh_since_last_run=fresh_since_last_run,
        remote_count=remote_count,
        experience_counts=experience_counts,
        top_industries=top_industries,
    )
