"""
Rule-based "For You" recommendations.
Score = w1*track_match + w2*tech_jaccard + w3*seniority_match + w4*remote_fit + w5*recency - sponsorship_penalty
Fully deterministic, fully explainable — every match ships a human-readable "why" string.
"""
import math
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Company, Job, User
from app.routers.users import get_current_user
from app.schemas import JobListItem, RecommendedJob

router = APIRouter(prefix="/users/me/recommendations", tags=["recommendations"])

W_TRACK = 2.0
W_TECH = 1.5
W_SENIORITY = 1.5
W_REMOTE = 1.0
W_RECENCY = 0.5
SPONSORSHIP_PENALTY = 3.0
RECENCY_HALF_LIFE_DAYS = 30.0

TRACK_KEYWORDS: dict[str, list[str]] = {
    "swe":       ["software", "engineer", "developer", "backend", "frontend", "fullstack", "platform", "infrastructure", "web"],
    "ml":        ["machine learning", "ml", "ai ", "artificial intelligence", "deep learning", "nlp", "computer vision", "model", "research scientist"],
    "data":      ["data", "analytics", "analyst", "scientist", "etl", "pipeline", "warehouse", "bi "],
    "robotics":  ["robotics", "robot", "ros", "embedded", "firmware", "hardware", "autonomy"],
    "security":  ["security", "appsec", "infosec", "penetration", "compliance", "trust"],
    "devops":    ["devops", "sre", "reliability", "kubernetes", "infrastructure", "cloud", "platform engineer"],
    "design":    ["design", "ux ", "ui ", "product design", "designer"],
    "product":   ["product manager", " pm ", "product lead", "program manager"],
    "research":  ["research", "scientist", "phd", "principal researcher"],
}

SENIORITY_MAP: dict[str, list[str]] = {
    "intern":      ["Internship"],
    "new_grad":    ["Entry Level"],
    "mid":         ["Mid Level"],
    "senior":      ["Senior"],
    "management":  ["Management"],
}


def _track_match(job: Job, tracks: list[str]) -> float:
    haystack = f"{job.title} {job.department or ''}".lower()
    for track in tracks:
        keywords = TRACK_KEYWORDS.get(track, [])
        if any(kw in haystack for kw in keywords):
            return 1.0
    return 0.0


def _tech_jaccard(job_tags: list[str] | None, user_tags: list[str] | None) -> tuple[float, list[str]]:
    if not job_tags or not user_tags:
        return 0.0, []
    a = {t.lower() for t in job_tags}
    b = {t.lower() for t in user_tags}
    intersection = a & b
    union = a | b
    score = len(intersection) / len(union) if union else 0.0
    return score, sorted(intersection)


def _seniority_match(job: Job, seniority_pref: list[str]) -> float:
    if not seniority_pref or not job.experience_level:
        return 0.0
    allowed = []
    for s in seniority_pref:
        allowed.extend(SENIORITY_MAP.get(s, []))
    return 1.0 if job.experience_level in allowed else 0.0


def _remote_fit(job: Job, remote_pref: str | None) -> float:
    if not remote_pref or remote_pref == "any":
        return 1.0
    if remote_pref == "remote" and job.remote:
        return 1.0
    if remote_pref == "onsite" and job.remote is False:
        return 1.0
    if remote_pref in ("hybrid", "onsite") and job.remote is None:
        return 0.5
    return 0.0


def _recency_decay(posted_at: datetime | None) -> float:
    if not posted_at:
        return 0.1
    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    days_old = (now - posted_at).days
    return math.exp(-math.log(2) * days_old / RECENCY_HALF_LIFE_DAYS)


def _build_why(track_s: float, shared_tech: list[str], seniority_s: float, remote_s: float, recency: float, tracks: list[str]) -> str:
    parts = []
    if track_s > 0:
        parts.append(f"Matches your {'/'.join(t.upper() for t in tracks[:2])} track")
    if shared_tech:
        tag_str = ", ".join(shared_tech[:3])
        parts.append(f"{len(shared_tech)} shared skill{'s' if len(shared_tech) != 1 else ''} ({tag_str})")
    if seniority_s > 0:
        parts.append("fits your seniority")
    decay_days = int(RECENCY_HALF_LIFE_DAYS * math.log(1 / max(recency, 1e-9)) / math.log(2))
    if decay_days < 7:
        parts.append("posted recently")
    elif decay_days < 30:
        parts.append(f"posted ~{decay_days}d ago")
    if not parts:
        parts.append("matches your profile")
    return " · ".join(parts)


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


@router.get("", response_model=list[RecommendedJob])
def get_recommendations(
    limit: int = 30,
    user: User = Depends(get_current_user),
    session: Session = Depends(_db),
):
    profile = user.profile
    if not profile:
        return []

    tracks = profile.tracks or []
    user_tech = profile.tech_tags or []
    seniority_pref = profile.seniority_pref or []
    remote_pref = profile.remote_pref.value if profile.remote_pref else "any"
    needs_sponsorship = profile.needs_sponsorship or False
    salary_floor = profile.salary_floor

    rows = session.execute(
        select(Job, Company.name.label("company_name"), Company.industry.label("company_industry"))
        .join(Company, Job.company_id == Company.id)
        .where(Job.is_active == True)
        .order_by(Job.posted_at.desc().nullslast())
        .limit(500)
    ).all()

    scored: list[tuple[float, str, Job, str]] = []
    for row in rows:
        job = row.Job
        company_name = row.company_name

        # Filter: salary floor
        if salary_floor and job.salary_max and job.salary_max < salary_floor:
            continue

        track_s = _track_match(job, tracks)
        tech_s, shared_tech = _tech_jaccard(job.tech_tags, user_tech)
        seniority_s = _seniority_match(job, seniority_pref)
        remote_s = _remote_fit(job, remote_pref)
        recency = _recency_decay(job.posted_at)

        penalty = 0.0
        if needs_sponsorship and job.sponsorship_flag == "likely_no":
            penalty = SPONSORSHIP_PENALTY

        total = (
            W_TRACK * track_s
            + W_TECH * tech_s
            + W_SENIORITY * seniority_s
            + W_REMOTE * remote_s
            + W_RECENCY * recency
            - penalty
        )
        if total <= 0:
            continue

        why = _build_why(track_s, shared_tech, seniority_s, remote_s, recency, tracks)
        scored.append((total, why, job, company_name))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, why, job, company_name in scored[:limit]:
        job_item = JobListItem(
            id=job.id,
            title=job.title,
            company_name=company_name,
            company_id=job.company_id,
            location_normalized=job.location_normalized,
            remote=job.remote,
            department=job.department,
            employment_type=job.employment_type,
            experience_level=job.experience_level,
            tech_tags=job.tech_tags,
            sponsorship_flag=job.sponsorship_flag,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            posted_at=job.posted_at,
            first_seen_at=job.first_seen_at,
            apply_url=job.apply_url,
            is_new=False,
        )
        results.append(RecommendedJob(job=job_item, score=round(score, 3), why=why))
    return results
