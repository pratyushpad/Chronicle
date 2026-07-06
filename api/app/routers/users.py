import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.internal_auth import verify_internal_token
from app.models import Profile, User
from app.schemas import ProfileIn, ProfileOut, UserOut, UserSyncIn

router = APIRouter(prefix="/users", tags=["users"])


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def require_internal_email(x_internal_auth: str | None = Header(None)) -> str:
    """Verify the signed internal token and return the asserted email."""
    secret = os.environ.get("INTERNAL_API_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="INTERNAL_API_SECRET not configured")
    if not x_internal_auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return verify_internal_token(x_internal_auth, secret)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(
    email: str = Depends(require_internal_email), session: Session = Depends(_db)
) -> User:
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found — call /users/sync first")
    return user


@router.post("/sync", response_model=UserOut)
def sync_user(
    body: UserSyncIn,
    email: str = Depends(require_internal_email),
    session: Session = Depends(_db),
):
    """Create or update a user from NextAuth sign-in data."""
    if body.email != email:
        raise HTTPException(status_code=403, detail="Token email does not match body email")
    user = session.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user:
        user.name = body.name or user.name
        user.avatar_url = body.avatar_url or user.avatar_url
        user.auth_provider = body.provider
        user.auth_provider_id = body.provider_id
    else:
        user = User(
            auth_provider=body.provider,
            auth_provider_id=body.provider_id,
            email=body.email,
            name=body.name,
            avatar_url=body.avatar_url,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)

    session.commit()
    session.refresh(user)
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        has_profile=user.profile is not None,
    )


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        has_profile=user.profile is not None,
    )


@router.get("/me/profile", response_model=ProfileOut | None)
def get_profile(user: User = Depends(get_current_user)):
    return user.profile


@router.put("/me/profile", response_model=ProfileOut)
def upsert_profile(body: ProfileIn, user: User = Depends(get_current_user), session: Session = Depends(_db)):
    profile = session.execute(select(Profile).where(Profile.user_id == user.id)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if profile:
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        profile.updated_at = now
    else:
        profile = Profile(
            user_id=user.id,
            updated_at=now,
            **body.model_dump(exclude_unset=True),
        )
        session.add(profile)
    session.commit()
    session.refresh(profile)

    _refresh_embedding_best_effort(session, user.id)
    return profile


def _refresh_embedding_best_effort(session: Session, user_id: int) -> None:
    """Refresh the profile's semantic vector; never fail the request over it."""
    try:
        from app.ml.profile_embedding import refresh_profile_embedding

        refresh_profile_embedding(session, user_id)
    except Exception:
        logging.getLogger(__name__).exception("profile embedding refresh failed for user %d", user_id)


def _get_or_create_profile(session: Session, user_id: int) -> Profile:
    profile = session.execute(select(Profile).where(Profile.user_id == user_id)).scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user_id, updated_at=datetime.now(timezone.utc))
        session.add(profile)
    return profile


@router.post("/me/resume", response_model=ProfileOut)
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(_db),
):
    """Extract text from an uploaded resume (.pdf/.txt) and store it.

    Only the extracted text is kept — the file itself is discarded.
    """
    from app.resume import extract_resume_text

    data = await file.read()
    try:
        text = extract_resume_text(data, file.filename or "", file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    profile = _get_or_create_profile(session, user.id)
    profile.resume_text = text
    profile.resume_updated_at = datetime.now(timezone.utc)
    profile.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(profile)
    _refresh_embedding_best_effort(session, user.id)
    return profile


@router.delete("/me/resume", response_model=ProfileOut)
def delete_resume(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    profile = user.profile
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile")
    profile.resume_text = None
    profile.resume_updated_at = None
    profile.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(profile)
    _refresh_embedding_best_effort(session, user.id)
    return profile
