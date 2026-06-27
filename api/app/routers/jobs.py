from datetime import date, datetime, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Company, IngestRun, Job
from app.schemas import (
    CompanyDetail,
    CompanyItem,
    JobDetail,
    JobListItem,
    JobListResponse,
    LastRunSummary,
    MetaResponse,
)

router = APIRouter()


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


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
    industry: Optional[str] = Query(None),
    posted_after: Optional[date] = Query(None),
    since_last_run: bool = Query(False),
    sort: str = Query("posted_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(_db),
):
    stmt = select(Job, Company.name.label("company_name"), Company.industry.label("company_industry")).join(Company).where(Job.is_active == True)

    if q:
        stmt = stmt.where(Job.title.ilike(f"%{q}%"))
    if company:
        stmt = stmt.where(Company.name.ilike(f"%{company}%"))
    if company_id:
        stmt = stmt.where(Job.company_id == company_id)
    if department:
        stmt = stmt.where(Job.department.ilike(f"%{department}%"))
    if location:
        stmt = stmt.where(Job.location_normalized.ilike(f"%{location}%"))
    if remote is not None:
        stmt = stmt.where(Job.remote == remote)
    if employment_type:
        stmt = stmt.where(Job.employment_type.ilike(f"%{employment_type}%"))
    if experience_level:
        stmt = stmt.where(Job.experience_level.ilike(f"%{experience_level}%"))
    if industry:
        stmt = stmt.where(Company.industry.ilike(f"%{industry}%"))
    if posted_after:
        stmt = stmt.where(Job.posted_at >= datetime(posted_after.year, posted_after.month, posted_after.day, tzinfo=timezone.utc))
    if since_last_run:
        last_start = _last_run_start(session)
        if last_start:
            stmt = stmt.where(Job.first_seen_at >= last_start)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.execute(total_stmt).scalar_one()

    order_col = Job.posted_at if sort == "posted_at" else Job.first_seen_at
    stmt = stmt.order_by(order_col.desc().nullslast()).offset((page - 1) * page_size).limit(page_size)

    rows = session.execute(stmt).all()
    last_start = _last_run_start(session)

    items = []
    for row in rows:
        job = row.Job
        is_new = bool(last_start and job.first_seen_at >= last_start)
        items.append(
            JobListItem(
                id=job.id,
                title=job.title,
                company_name=row.company_name,
                company_id=job.company_id,
                location_normalized=job.location_normalized,
                remote=job.remote,
                department=job.department,
                employment_type=job.employment_type,
                experience_level=job.experience_level,
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
        select(Company, func.count(Job.id).label("active_job_count"))
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
        select(Company, func.count(Job.id).label("active_job_count"))
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
        select(func.count()).select_from(Job).where(Job.is_active == True)
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

    return MetaResponse(
        departments=distinct_col(Job.department),
        locations=distinct_col(Job.location_normalized),
        employment_types=distinct_col(Job.employment_type),
        experience_levels=distinct_col(Job.experience_level),
        industries=industries,
        last_run=last_run,
        total_active_jobs=total_active,
        total_companies=total_companies,
    )
