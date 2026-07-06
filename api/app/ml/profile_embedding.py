"""Profile embeddings for For-You v2.

profile vector = normalize(TEXT_WEIGHT * embed(profile text)
                           + CENTROID_WEIGHT * weighted centroid of engaged-job embeddings)

Engagement weights: applied (any tracked status beyond a bookmark) counts
APPLIED_WEIGHT, saved counts SAVED_WEIGHT. Falls back gracefully: no
engagements -> profile text only; no profile text either -> None.
"""
import logging

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, AppStatus, Job, Profile

log = logging.getLogger(__name__)

TEXT_WEIGHT = 0.5
CENTROID_WEIGHT = 0.5
APPLIED_WEIGHT = 2.0
SAVED_WEIGHT = 1.0


def build_profile_text(
    tracks: list[str] | None,
    tech_tags: list[str] | None,
    seniority_pref: list[str] | None,
    location: str | None,
    headline: str | None,
) -> str:
    """Render profile fields into embedding input. Empty string when nothing is set."""
    parts = []
    if headline:
        parts.append(f"{headline}.")
    if tracks:
        parts.append(f"Interested in {', '.join(tracks)} roles.")
    if seniority_pref:
        parts.append(f"Seniority: {', '.join(seniority_pref)}.")
    if tech_tags:
        parts.append(f"Skills: {', '.join(tech_tags)}.")
    if location:
        parts.append(f"Based in {location}.")
    return " ".join(parts)


def weighted_centroid(vectors: list[list[float]], weights: list[float]) -> np.ndarray | None:
    """Weighted mean of vectors, L2-normalized. None when inputs are empty."""
    if not vectors or not weights or len(vectors) != len(weights):
        return None
    stacked = np.asarray(vectors, dtype=np.float32)
    w = np.asarray(weights, dtype=np.float32)[:, None]
    centroid = (stacked * w).sum(axis=0) / max(w.sum(), 1e-9)
    norm = np.linalg.norm(centroid)
    if norm < 1e-9:
        return None
    return centroid / norm


def combine(text_vec: np.ndarray | None, centroid_vec: np.ndarray | None) -> list[float] | None:
    """Blend the two components, tolerating either being absent."""
    if text_vec is None and centroid_vec is None:
        return None
    if text_vec is None:
        combined = centroid_vec
    elif centroid_vec is None:
        combined = text_vec
    else:
        combined = TEXT_WEIGHT * text_vec + CENTROID_WEIGHT * centroid_vec
    norm = np.linalg.norm(combined)
    if norm < 1e-9:
        return None
    return (combined / norm).astype(np.float32).tolist()


def compute_profile_embedding(session: Session, user_id: int) -> list[float] | None:
    """Compute (not store) the profile vector for a user."""
    profile = session.get(Profile, user_id)
    if profile is None:
        return None

    text = build_profile_text(
        tracks=profile.tracks,
        tech_tags=profile.tech_tags,
        seniority_pref=profile.seniority_pref,
        location=profile.location,
        headline=profile.headline,
    )
    text_vec = None
    if text:
        from app.ml.embedder import get_embedder

        text_vec = np.asarray(get_embedder().encode([text])[0], dtype=np.float32)

    rows = session.execute(
        select(Job.embedding, Application.status)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == user_id, Job.embedding.isnot(None))
    ).all()
    vectors = [list(r[0]) for r in rows]
    weights = [SAVED_WEIGHT if r[1] == AppStatus.saved else APPLIED_WEIGHT for r in rows]
    centroid_vec = weighted_centroid(vectors, weights)

    return combine(text_vec, centroid_vec)


def refresh_profile_embedding(session: Session, user_id: int) -> bool:
    """Compute and persist; returns True when a vector was stored."""
    vector = compute_profile_embedding(session, user_id)
    profile = session.get(Profile, user_id)
    if profile is None:
        return False
    profile.embedding = vector
    session.commit()
    return vector is not None


def refresh_all_profile_embeddings(session: Session) -> int:
    """Nightly sweep over every profile; returns count refreshed."""
    user_ids = session.execute(select(Profile.user_id)).scalars().all()
    refreshed = 0
    for user_id in user_ids:
        try:
            if refresh_profile_embedding(session, user_id):
                refreshed += 1
        except Exception:
            session.rollback()
            log.exception("profile embedding refresh failed for user %d", user_id)
    return refreshed
