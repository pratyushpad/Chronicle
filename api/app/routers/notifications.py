from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Notification, SavedSearch, User
from app.routers.users import get_current_user
from app.schemas import NotificationOut, SavedSearchIn, SavedSearchOut

router = APIRouter(prefix="/users/me", tags=["notifications"])


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).scalars().all()
    return rows


@router.put("/notifications/{notif_id}/read", status_code=200)
def mark_read(notif_id: int, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    n = session.execute(
        select(Notification).where(Notification.id == notif_id, Notification.user_id == user.id)
    ).scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read = True
    session.commit()
    return {"read": True}


@router.put("/notifications/read-all", status_code=200)
def mark_all_read(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.read == False)
    ).scalars().all()
    for n in rows:
        n.read = True
    session.commit()
    return {"updated": len(rows)}


@router.get("/searches", response_model=list[SavedSearchOut])
def list_searches(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    rows = session.execute(
        select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/searches", response_model=SavedSearchOut, status_code=201)
def create_search(body: SavedSearchIn, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    search = SavedSearch(
        user_id=user.id,
        name=body.name,
        query_json=body.query_json,
        alert_frequency=body.alert_frequency,
        created_at=datetime.now(timezone.utc),
    )
    session.add(search)
    session.commit()
    session.refresh(search)
    return search


@router.delete("/searches/{search_id}", status_code=200)
def delete_search(search_id: int, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    s = session.execute(
        select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user.id)
    ).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Saved search not found")
    session.delete(s)
    session.commit()
    return {"deleted": True}
