from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Application, ApplicationEvent, AppStatus, Company, Job, User
from app.routers.users import get_current_user
from app.schemas import (
    ApplicationCreateIn, ApplicationOut, ApplicationUpdateIn,
    FunnelStats, JobListItem,
)
from app.util import root_domain

router = APIRouter(prefix="/users/me/applications", tags=["applications"])

ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "saved":        ["applied", "archived"],
    "applied":      ["interviewing", "rejected", "archived"],
    "interviewing": ["offer", "rejected", "archived"],
    "offer":        ["archived"],
    "rejected":     ["applied", "archived"],
    "archived":     ["saved"],
}


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def _build_app_out(app: Application, job_item: JobListItem) -> ApplicationOut:
    return ApplicationOut(
        id=app.id,
        job_id=app.job_id,
        status=app.status.value if hasattr(app.status, "value") else app.status,
        applied_at=app.applied_at,
        notes=app.notes,
        next_action=app.next_action,
        next_action_date=app.next_action_date,
        created_at=app.created_at,
        updated_at=app.updated_at,
        job=job_item,
        events=[
            {"id": e.id, "from_status": e.from_status, "to_status": e.to_status, "at": e.at}
            for e in (app.events or [])
        ],
    )


@router.get("", response_model=list[ApplicationOut])
def list_applications(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(Application, Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
    ).all()

    # Eager-load events for each application
    app_ids = [r.Application.id for r in rows]
    events_map: dict[int, list] = {a_id: [] for a_id in app_ids}
    if app_ids:
        event_rows = session.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id.in_(app_ids))
            .order_by(ApplicationEvent.at)
        ).scalars().all()
        for ev in event_rows:
            events_map[ev.application_id].append(ev)

    results = []
    for row in rows:
        job_item = _row_to_job_item(row)
        app = row.Application
        app.events = events_map.get(app.id, [])
        results.append(_build_app_out(app, job_item))
    return results


@router.get("/funnel", response_model=FunnelStats)
def funnel_stats(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(Application.status, func.count().label("cnt"))
        .where(Application.user_id == user.id)
        .group_by(Application.status)
    ).all()
    counts = {r.status if isinstance(r.status, str) else r.status.value: r.cnt for r in rows}
    applied = counts.get("applied", 0)
    interviews = counts.get("interviewing", 0)
    offers = counts.get("offer", 0)
    total_response = applied + interviews + offers + counts.get("rejected", 0)
    response_rate = (interviews + offers) / total_response if total_response else 0.0
    return FunnelStats(
        saved=counts.get("saved", 0),
        applied=applied,
        interviewing=interviews,
        offer=offers,
        rejected=counts.get("rejected", 0),
        archived=counts.get("archived", 0),
        response_rate=round(response_rate, 3),
    )


@router.post("", response_model=ApplicationOut, status_code=201)
def create_application(body: ApplicationCreateIn, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    job = session.get(Job, body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = session.execute(
        select(Application).where(Application.user_id == user.id, Application.job_id == body.job_id)
    ).scalar_one_or_none()
    if existing:
        return _get_app_with_job(existing, session)

    status = body.status if body.status in ALLOWED_TRANSITIONS else "saved"
    now = datetime.now(timezone.utc)
    app = Application(
        user_id=user.id,
        job_id=body.job_id,
        status=AppStatus(status),
        created_at=now,
        updated_at=now,
    )
    session.add(app)
    session.flush()
    ev = ApplicationEvent(application_id=app.id, from_status=None, to_status=status, at=now)
    session.add(ev)
    session.commit()
    session.refresh(app)
    return _get_app_with_job(app, session)


@router.put("/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdateIn, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    app = session.execute(
        select(Application).where(Application.id == app_id, Application.user_id == user.id)
    ).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    now = datetime.now(timezone.utc)
    if body.status is not None:
        current = app.status.value if hasattr(app.status, "value") else app.status
        if body.status not in ALLOWED_TRANSITIONS.get(current, []):
            raise HTTPException(status_code=422, detail=f"Cannot transition from {current} to {body.status}")
        ev = ApplicationEvent(application_id=app.id, from_status=current, to_status=body.status, at=now)
        session.add(ev)
        app.status = AppStatus(body.status)
        if body.status == "applied" and app.applied_at is None:
            app.applied_at = now
    if body.notes is not None:
        app.notes = body.notes
    if body.next_action is not None:
        app.next_action = body.next_action
    if body.next_action_date is not None:
        app.next_action_date = body.next_action_date
    app.updated_at = now
    session.commit()
    session.refresh(app)
    return _get_app_with_job(app, session)


@router.delete("/{app_id}", status_code=200)
def delete_application(app_id: int, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    app = session.execute(
        select(Application).where(Application.id == app_id, Application.user_id == user.id)
    ).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    session.delete(app)
    session.commit()
    return {"deleted": True}


def _row_to_job_item(row) -> JobListItem:
    return JobListItem(
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


def _get_app_with_job(app: Application, session: Session) -> ApplicationOut:
    row = session.execute(
        select(Application, Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .where(Application.id == app.id)
    ).first()
    events = session.execute(
        select(ApplicationEvent).where(ApplicationEvent.application_id == app.id).order_by(ApplicationEvent.at)
    ).scalars().all()
    row.Application.events = events
    return _build_app_out(row.Application, _row_to_job_item(row))
