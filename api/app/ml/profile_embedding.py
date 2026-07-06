"""Profile embeddings for For-You v2.

profile vector = normalize(
    TEXT_WEIGHT     * mean(field-text vec, about vec, resume chunk vecs)
  + CENTROID_WEIGHT * weighted centroid of engaged-job vectors (applied 2x, saved 1x)
  - DISMISS_WEIGHT  * centroid of dismissed-job vectors
)

The model truncates each encode at ~256 tokens, so long documents (resumes)
are embedded as several chunks and averaged rather than as one truncated
blob. Falls back gracefully: any absent component simply drops out; if
nothing is available the vector is None.
"""
import logging

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, AppStatus, Interaction, InteractionEvent, Job, Profile

log = logging.getLogger(__name__)

TEXT_WEIGHT = 0.5
CENTROID_WEIGHT = 0.5
DISMISS_WEIGHT = 0.25
APPLIED_WEIGHT = 2.0
SAVED_WEIGHT = 1.0
# Resume chunking: ~1000 chars ≈ the model's 256-token window.
CHUNK_CHARS = 1000
MAX_CHUNKS = 4
ABOUT_MAX_CHARS = 2000


def build_profile_text(
    tracks: list[str] | None,
    tech_tags: list[str] | None,
    seniority_pref: list[str] | None,
    location: str | None,
    headline: str | None,
) -> str:
    """Render structured profile fields into embedding input. Empty string when nothing is set."""
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


def chunk_text(text: str, size: int = CHUNK_CHARS, max_chunks: int = MAX_CHUNKS) -> list[str]:
    """Split text into up to max_chunks pieces of ~size chars, breaking on whitespace."""
    text = " ".join(text.split())  # collapse whitespace/newlines
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = start + size
        if end < len(text):
            space = text.rfind(" ", start, end)
            if space > start:
                end = space
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def profile_text_inputs(profile) -> list[str]:
    """All text snippets to embed for a profile: fields, about, resume chunks."""
    inputs = []
    fields = build_profile_text(
        tracks=profile.tracks,
        tech_tags=profile.tech_tags,
        seniority_pref=profile.seniority_pref,
        location=profile.location,
        headline=profile.headline,
    )
    if fields:
        inputs.append(fields)
    if profile.about:
        inputs.append(profile.about[:ABOUT_MAX_CHARS])
    if profile.resume_text:
        inputs.extend(chunk_text(profile.resume_text))
    return inputs


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


def combine(
    text_vec: np.ndarray | None,
    centroid_vec: np.ndarray | None,
    dismissed_vec: np.ndarray | None = None,
) -> list[float] | None:
    """Blend components, tolerating any being absent; dismissed pushes away."""
    if text_vec is None and centroid_vec is None:
        return None
    if text_vec is None:
        combined = CENTROID_WEIGHT * centroid_vec
    elif centroid_vec is None:
        combined = TEXT_WEIGHT * text_vec
    else:
        combined = TEXT_WEIGHT * text_vec + CENTROID_WEIGHT * centroid_vec
    if dismissed_vec is not None:
        combined = combined - DISMISS_WEIGHT * dismissed_vec
    norm = np.linalg.norm(combined)
    if norm < 1e-9:
        return None
    return (combined / norm).astype(np.float32).tolist()


def compute_profile_embedding(session: Session, user_id: int) -> list[float] | None:
    """Compute (not store) the profile vector for a user."""
    profile = session.get(Profile, user_id)
    if profile is None:
        return None

    inputs = profile_text_inputs(profile)
    text_vec = None
    if inputs:
        from app.ml.embedder import get_embedder

        vectors = np.asarray(get_embedder().encode(inputs), dtype=np.float32)
        text_vec = vectors.mean(axis=0)
        norm = np.linalg.norm(text_vec)
        text_vec = text_vec / norm if norm > 1e-9 else None

    rows = session.execute(
        select(Job.embedding, Application.status)
        .join(Application, Application.job_id == Job.id)
        .where(Application.user_id == user_id, Job.embedding.isnot(None))
    ).all()
    vectors = [list(r[0]) for r in rows]
    weights = [SAVED_WEIGHT if r[1] == AppStatus.saved else APPLIED_WEIGHT for r in rows]
    centroid_vec = weighted_centroid(vectors, weights)

    dismissed_rows = session.execute(
        select(Job.embedding)
        .join(Interaction, Interaction.job_id == Job.id)
        .where(
            Interaction.user_id == user_id,
            Interaction.event == InteractionEvent.dismiss,
            Job.embedding.isnot(None),
        )
        .distinct()
    ).all()
    dismissed_vec = weighted_centroid(
        [list(r[0]) for r in dismissed_rows], [1.0] * len(dismissed_rows)
    )

    return combine(text_vec, centroid_vec, dismissed_vec)


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
