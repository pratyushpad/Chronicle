"""Interaction event capture — raw engagement signals for future learned ranking.

Fire-and-forget from the web client (batched). No reads, no ML here; the
table is append-only training data.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Interaction, InteractionEvent, InteractionSurface, User
from app.routers.users import get_current_user
from app.schemas import InteractionBatchIn

router = APIRouter(prefix="/interactions", tags=["interactions"])


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


@router.post("/batch", status_code=204)
def log_interactions(
    body: InteractionBatchIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(_db),
):
    session.add_all(
        Interaction(
            user_id=user.id,
            job_id=e.job_id,
            event=InteractionEvent(e.event),
            surface=InteractionSurface(e.surface),
        )
        for e in body.events
    )
    try:
        session.commit()
    except IntegrityError:
        # Fire-and-forget telemetry must never 500: a stale tab can batch an event
        # for a job that pruning just hard-deleted (FK violation). Drop the batch.
        session.rollback()
    return Response(status_code=204)
