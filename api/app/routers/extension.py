"""Browser-extension API.

Two auth surfaces:
  - Token management (`/users/me/extension-token`) is reached *through the web app*
    and uses the existing `X-User-Email` auth (`get_current_user`).
  - The extension's own data endpoints (`/extension/*`) authenticate with the
    per-user bearer token via `get_user_by_extension_token`.

`POST /extension/saved` find-or-creates the Company and Job so a role from any ATS
page can be tracked even if Chronicle hasn't ingested it. Brand-new companies are
created `active=False` so they never bypass the verify_and_add quarantine gate — the
ingest runner only iterates active companies.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.ingest.dedupe import make_dedup_key
from app.ingest.normalize import dedup_title, keying_title, normalize_location, normalize_title
from app.models import Application, ApplicationEvent, AppStatus, ATSSource, Company, Job, User
from app.routers.applications import _get_app_with_job
from app.routers.users import get_current_user
from app.schemas import (
    ApplicationOut,
    ExtensionMeOut,
    ExtensionProfileOut,
    ExtensionSaveIn,
    ExtensionTokenOut,
    ExtensionTokenStatusOut,
)
from app.security import generate_extension_token, hash_token, verify_token

router = APIRouter(tags=["extension"])


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


# ── Token management (web-app auth) ───────────────────────────────────────────

@router.get("/users/me/extension-token", response_model=ExtensionTokenStatusOut)
def extension_token_status(user: User = Depends(get_current_user)):
    return ExtensionTokenStatusOut(connected=user.extension_token_hash is not None)


@router.post("/users/me/extension-token", response_model=ExtensionTokenOut)
def issue_extension_token(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    """(Re)generate the token — invalidates any previous one. Plaintext returned once."""
    token = generate_extension_token()
    db_user = session.get(User, user.id)
    db_user.extension_token_hash = hash_token(token)
    session.commit()
    return ExtensionTokenOut(token=token)


@router.delete("/users/me/extension-token", status_code=200)
def revoke_extension_token(user: User = Depends(get_current_user), session: Session = Depends(_db)):
    db_user = session.get(User, user.id)
    db_user.extension_token_hash = None
    session.commit()
    return {"revoked": True}


# ── Bearer-token auth for the extension itself ────────────────────────────────

def get_user_by_extension_token(
    authorization: str | None = Header(None),
    session: Session = Depends(_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:].strip()
    token_hash = hash_token(token)
    user = session.execute(
        select(User).where(User.extension_token_hash == token_hash)
    ).scalar_one_or_none()
    # Defense-in-depth constant-time recheck (the indexed lookup already matched the hash).
    if not user or not verify_token(token, user.extension_token_hash):
        raise HTTPException(status_code=401, detail="Invalid extension token")
    return user


# ── Extension data endpoints (bearer auth) ────────────────────────────────────

@router.get("/extension/me", response_model=ExtensionMeOut)
def extension_me(user: User = Depends(get_user_by_extension_token)):
    return ExtensionMeOut(email=user.email, name=user.name)


@router.get("/extension/profile", response_model=ExtensionProfileOut)
def extension_profile(user: User = Depends(get_user_by_extension_token)):
    p = user.profile
    work_auth = None
    if p is not None:
        work_auth = p.work_authorization
        if not work_auth and p.needs_sponsorship is not None:
            work_auth = (
                "Requires visa sponsorship"
                if p.needs_sponsorship
                else "Authorized to work (no sponsorship needed)"
            )
    return ExtensionProfileOut(
        full_name=(p.full_name if p else None) or user.name,
        email=user.email,
        phone=p.phone if p else None,
        location=p.location if p else None,
        work_authorization=work_auth,
        links=p.links if p else None,
    )


@router.post("/extension/saved", response_model=ApplicationOut, status_code=201)
def extension_save(
    body: ExtensionSaveIn,
    user: User = Depends(get_user_by_extension_token),
    session: Session = Depends(_db),
):
    try:
        ats = ATSSource(body.ats)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown ats '{body.ats}'")

    # 1. Find-or-create Company. New ones are UNVERIFIED (active=False) so they never
    #    bypass the verify_and_add quarantine gate; existing rows are left untouched.
    company = session.execute(
        select(Company).where(Company.ats == ats, Company.slug == body.company_slug)
    ).scalar_one_or_none()
    if company is None:
        company = Company(
            name=body.company_name,
            ats=ats,
            slug=body.company_slug,
            careers_url=None,
            industry=None,
            active=False,
        )
        session.add(company)
        session.flush()

    # 2. Find-or-create Job by (source, source_job_id). Build the dedup key with the SAME
    #    helpers the ingest runner uses so a later ingest upserts this very row.
    job = session.execute(
        select(Job).where(Job.source == ats, Job.source_job_id == body.source_job_id)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if job is None:
        l_norm = normalize_location(body.location)
        job = Job(
            company_id=company.id,
            source=ats,
            source_job_id=body.source_job_id,
            title=body.title,
            title_normalized=normalize_title(body.title),
            location_raw=body.location,
            location_normalized=l_norm,
            apply_url=body.apply_url,
            dedup_key=make_dedup_key(company.id, dedup_title(keying_title(body.title), l_norm)),
            sponsorship_flag="unknown",
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        )
        session.add(job)
        session.flush()

    # 3. Create the saved Application (idempotent on (user_id, job_id)).
    existing = session.execute(
        select(Application).where(Application.user_id == user.id, Application.job_id == job.id)
    ).scalar_one_or_none()
    if existing:
        session.commit()
        return _get_app_with_job(existing, session)

    app = Application(
        user_id=user.id, job_id=job.id, status=AppStatus.saved, created_at=now, updated_at=now,
    )
    session.add(app)
    session.flush()
    session.add(ApplicationEvent(application_id=app.id, from_status=None, to_status="saved", at=now))
    session.commit()
    session.refresh(app)
    return _get_app_with_job(app, session)
