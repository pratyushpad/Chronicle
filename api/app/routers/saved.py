from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Application, ApplicationEvent, AppStatus, Company, Job, User
from app.routers.users import get_current_user
from app.schemas import JobListItem, SavedJobOut
from app.util import root_domain

# "Saved" is the entry stage of the tracker: a bookmark is an Application with
# status='saved'. These routes are a view over that single store (no separate
# saved_jobs table).
router = APIRouter(prefix="/users/me/saved", tags=["saved"])


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


@router.get("", response_model=list[SavedJobOut])
def list_saved(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(Application, Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .where(Application.user_id == user.id, Application.status == AppStatus.saved)
        .order_by(Application.created_at.desc())
    ).all()

    results = []
    for row in rows:
        job_item = JobListItem(
            id=row.Job.id,
            title=row.Job.title,
            company_name=row.company_name,
            company_id=row.Job.company_id,
            company_domain=root_domain(row.company_careers_url),
            location_normalized=row.Job.location_normalized,
            remote=row.Job.remote,
            department=row.Job.department,
            employment_type=row.Job.employment_type,
            experience_level=row.Job.experience_level,
            tech_tags=row.Job.tech_tags,
            sponsorship_flag=row.Job.sponsorship_flag,
            salary_min=row.Job.salary_min,
            salary_max=row.Job.salary_max,
            posted_at=row.Job.posted_at,
            first_seen_at=row.Job.first_seen_at,
            apply_url=row.Job.apply_url,
            is_new=False,
        )
        results.append(SavedJobOut(id=row.Application.id, job_id=row.Application.job_id, saved_at=row.Application.created_at, job=job_item))
    return results


@router.post("/{job_id}", status_code=201)
def save_job(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = session.execute(
        select(Application).where(Application.user_id == user.id, Application.job_id == job_id)
    ).scalar_one_or_none()
    # Already tracked at any stage → nothing to do (don't downgrade an advanced app).
    if existing:
        return {"saved": True}
    now = datetime.now(timezone.utc)
    app = Application(user_id=user.id, job_id=job_id, status=AppStatus.saved, created_at=now, updated_at=now)
    session.add(app)
    session.flush()
    session.add(ApplicationEvent(application_id=app.id, from_status=None, to_status="saved", at=now))
    session.commit()
    return {"saved": True}


@router.delete("/{job_id}", status_code=200)
def unsave_job(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    existing = session.execute(
        select(Application).where(Application.user_id == user.id, Application.job_id == job_id)
    ).scalar_one_or_none()
    # Un-bookmarking only removes a still-saved app; an advanced application
    # (applied/interviewing/…) stays in the tracker.
    if existing and existing.status == AppStatus.saved:
        session.delete(existing)
        session.commit()
    return {"saved": False}


@router.get("/ids", response_model=list[int])
def saved_ids(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(Application.job_id).where(Application.user_id == user.id, Application.status == AppStatus.saved)
    ).all()
    return [r[0] for r in rows]
