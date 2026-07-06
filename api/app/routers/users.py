import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
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
    return profile
