"""
"For You" recommendations.

Rule score = w1*track_match + w2*tech_jaccard + w3*seniority_match + w4*remote_fit + w5*recency - penalties
Fully deterministic, fully explainable — every match ships a human-readable "why" string.

When the profile has an embedding (app/ml/profile_embedding.py), a two-stage
path runs instead: pgvector retrieves the top candidates by cosine, then each
is reranked by ALPHA_COSINE * cosine + BETA_RULE * normalized rule score.
Falls back to the pure rule scan when no embedding exists.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Application, Company, Interaction, InteractionEvent, Job, User
from app.routers.users import get_current_user
from app.schemas import JobListItem, RecommendedJob
from app.util import root_domain

router = APIRouter(prefix="/users/me/recommendations", tags=["recommendations"])

W_TRACK = 2.0
W_TECH = 1.5
W_SENIORITY = 1.5
W_LOCATION = 1.0
W_REMOTE = 1.0
W_RECENCY = 0.5
SPONSORSHIP_PENALTY = 3.0
SENIORITY_MISMATCH_PENALTY = 4.0
RECENCY_HALF_LIFE_DAYS = 30.0
# Behavioral signal: boost roles at companies/departments the user already engaged with.
COMPANY_AFFINITY_BOOST = 0.75
DEPARTMENT_AFFINITY_BOOST = 0.5
# Two-stage blend (For-You v2): weight of profile-vector cosine vs normalized rule score.
ALPHA_COSINE = 0.6
BETA_RULE = 0.4
# pgvector candidate pool for stage 1.
CANDIDATE_POOL = 200
SEMANTIC_WHY = "semantically similar to jobs you saved"

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


def _location_fit(job: Job, location_pref: str | None) -> float:
    """1.0 when the user's location matches the job (or job is remote); neutral 0.5 if no pref."""
    if not location_pref:
        return 0.5
    if job.remote:
        return 1.0
    job_loc = (job.location_normalized or "").lower()
    if not job_loc:
        return 0.0
    pref = location_pref.lower()
    # Match on either side as a substring (e.g. "New York" vs "New York, NY").
    primary = pref.split(",")[0].strip()
    if primary and (primary in job_loc or job_loc in pref):
        return 1.0
    return 0.0


def _recency_decay(posted_at: datetime | None) -> float:
    if not posted_at:
        return 0.1
    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    days_old = (now - posted_at).days
    return math.exp(-math.log(2) * days_old / RECENCY_HALF_LIFE_DAYS)


def _build_why(track_s: float, shared_tech: list[str], seniority_s: float, location_s: float,
               recency: float, tracks: list[str], affinity_company: str | None, location_pref: str | None) -> str:
    parts = []
    if track_s > 0:
        parts.append(f"Matches your {'/'.join(t.upper() for t in tracks[:2])} track")
    if shared_tech:
        tag_str = ", ".join(shared_tech[:3])
        parts.append(f"{len(shared_tech)} shared skill{'s' if len(shared_tech) != 1 else ''} ({tag_str})")
    if seniority_s > 0:
        parts.append("fits your seniority")
    if affinity_company:
        parts.append(f"you've looked at {affinity_company}")
    if location_s >= 1.0 and location_pref:
        parts.append(f"in {location_pref.split(',')[0].strip()}")
    decay_days = int(RECENCY_HALF_LIFE_DAYS * math.log(1 / max(recency, 1e-9)) / math.log(2))
    if decay_days < 7:
        parts.append("posted recently")
    elif decay_days < 30:
        parts.append(f"posted ~{decay_days}d ago")
    if not parts:
        parts.append("matches your profile")
    return " · ".join(parts)


@dataclass
class RuleContext:
    """Everything the rule scorer needs, decoupled from ORM/session so the
    eval harness can score fixture jobs with the exact production logic."""

    tracks: list[str] = field(default_factory=list)
    user_tech: list[str] = field(default_factory=list)
    seniority_pref: list[str] = field(default_factory=list)
    remote_pref: str = "any"
    location_pref: str | None = None
    needs_sponsorship: bool = False
    salary_floor: int | None = None
    affinity_companies: dict[int, str] = field(default_factory=dict)
    affinity_departments: set[str] = field(default_factory=set)


def rule_score(job, ctx: RuleContext) -> tuple[float, str] | None:
    """Rule-based score + why string for one job; None = hard-filtered out.

    `job` is any object with the Job columns used below (ORM row or fixture).
    """
    if ctx.salary_floor and job.salary_max and job.salary_max < ctx.salary_floor:
        return None

    track_s = _track_match(job, ctx.tracks)
    tech_s, shared_tech = _tech_jaccard(job.tech_tags, ctx.user_tech)
    seniority_s = _seniority_match(job, ctx.seniority_pref)
    location_s = _location_fit(job, ctx.location_pref)
    remote_s = _remote_fit(job, ctx.remote_pref)
    recency = _recency_decay(job.posted_at)

    affinity = 0.0
    affinity_company = ctx.affinity_companies.get(job.company_id)
    if affinity_company:
        affinity += COMPANY_AFFINITY_BOOST
    if job.department and job.department.lower() in ctx.affinity_departments:
        affinity += DEPARTMENT_AFFINITY_BOOST

    penalty = 0.0
    if ctx.needs_sponsorship and job.sponsorship_flag == "likely_no":
        penalty += SPONSORSHIP_PENALTY
    # Heavy penalty for seniority mismatch — don't show Senior roles to interns
    if ctx.seniority_pref and job.experience_level and seniority_s == 0.0:
        penalty += SENIORITY_MISMATCH_PENALTY

    total = (
        W_TRACK * track_s
        + W_TECH * tech_s
        + W_SENIORITY * seniority_s
        + W_LOCATION * location_s
        + W_REMOTE * remote_s
        + W_RECENCY * recency
        + affinity
        - penalty
    )
    why = _build_why(track_s, shared_tech, seniority_s, location_s, recency, ctx.tracks, affinity_company, ctx.location_pref)
    return total, why


def _normalized_rule(rule_total: float, max_rule: float) -> float:
    """Rule score clamped at 0 and normalized against the best rule score in the pool."""
    return max(rule_total, 0.0) / max_rule if max_rule > 0 else 0.0


def blend_score(cosine: float, rule_total: float, max_rule: float) -> float:
    """Stage-2 rerank score: cosine blended with the rule score normalized
    against the best rule score in the candidate pool."""
    return ALPHA_COSINE * cosine + BETA_RULE * _normalized_rule(rule_total, max_rule)


def _rule_scored(
    session: Session, ctx: RuleContext, excluded_job_ids: set[int] | None = None
) -> list[tuple]:
    """Original path: scan recent active jobs, keep positive rule scores."""
    rows = session.execute(
        select(Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Company, Job.company_id == Company.id)
        .where(Job.is_active == True)
        .order_by(Job.posted_at.desc().nullslast())
        .limit(500)
    ).all()

    scored: list[tuple] = []
    for row in rows:
        if excluded_job_ids and row.Job.id in excluded_job_ids:
            continue
        result = rule_score(row.Job, ctx)
        if result is None:
            continue
        total, why = result
        if total <= 0:
            continue
        scored.append((total, why, row.Job, row.company_name, row.company_careers_url))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _two_stage_scored(
    session: Session,
    profile_embedding,
    ctx: RuleContext,
    excluded_job_ids: set[int],
    has_engagements: bool,
) -> list[tuple]:
    """For-You v2: pgvector cosine retrieval, then cosine+rule blend rerank."""
    distance = Job.embedding.cosine_distance(profile_embedding)
    rows = session.execute(
        select(
            Job,
            Company.name.label("company_name"),
            Company.careers_url.label("company_careers_url"),
            distance.label("distance"),
        )
        .join(Company, Job.company_id == Company.id)
        .where(Job.is_active == True, Job.embedding.isnot(None))
        .order_by(distance)
        .limit(CANDIDATE_POOL)
    ).all()

    candidates: list[tuple] = []
    for row in rows:
        if row.Job.id in excluded_job_ids:
            continue  # already saved/applied, or explicitly dismissed
        result = rule_score(row.Job, ctx)
        if result is None:
            continue
        cosine = 1.0 - row.distance
        candidates.append((cosine, *result, row))

    max_rule = max((rule_total for _, rule_total, _, _ in candidates), default=0.0)

    scored: list[tuple] = []
    for cosine, rule_total, why, row in candidates:
        rule_norm = _normalized_rule(rule_total, max_rule)
        total = ALPHA_COSINE * cosine + BETA_RULE * rule_norm
        if has_engagements and ALPHA_COSINE * cosine > BETA_RULE * rule_norm:
            why = f"{why} · {SEMANTIC_WHY}"
        scored.append((total, why, row.Job, row.company_name, row.company_careers_url))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


@router.get("", response_model=list[RecommendedJob])
def get_recommendations(
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(_db),
):
    profile = user.profile
    if not profile:
        return []

    # Behavioral signal: companies/departments the user has saved or applied to.
    # Saved + tracked now live in one store (applications, status='saved' = bookmark).
    affinity_companies: dict[int, str] = {}
    affinity_departments: set[str] = set()
    engaged_job_ids: set[int] = set()
    for job_id, company_id, dept, name in session.execute(
        select(Job.id, Job.company_id, Job.department, Company.name)
        .join(Application, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .where(Application.user_id == user.id)
    ).all():
        engaged_job_ids.add(job_id)
        if company_id is not None:
            affinity_companies[company_id] = name
        if dept:
            affinity_departments.add(dept.lower())

    # Jobs the user explicitly dismissed never come back, on either path.
    dismissed_job_ids: set[int] = {
        jid
        for (jid,) in session.execute(
            select(Interaction.job_id).where(
                Interaction.user_id == user.id,
                Interaction.event == InteractionEvent.dismiss,
            )
        ).all()
    }

    ctx = RuleContext(
        tracks=profile.tracks or [],
        user_tech=profile.tech_tags or [],
        seniority_pref=profile.seniority_pref or [],
        remote_pref=profile.remote_pref.value if profile.remote_pref else "any",
        location_pref=profile.location,
        needs_sponsorship=profile.needs_sponsorship or False,
        salary_floor=profile.salary_floor,
        affinity_companies=affinity_companies,
        affinity_departments=affinity_departments,
    )

    if profile.embedding is not None:
        scored = _two_stage_scored(
            session,
            profile.embedding,
            ctx,
            excluded_job_ids=engaged_job_ids | dismissed_job_ids,
            has_engagements=bool(engaged_job_ids),
        )
    else:
        scored = _rule_scored(session, ctx, engaged_job_ids | dismissed_job_ids)

    # Collapse cross-posted duplicates: keep the highest-scored posting per role
    # so the same job across N countries doesn't flood the feed.
    seen_keys: set[str] = set()
    deduped: list[tuple] = []
    for entry in scored:
        key = entry[2].dedup_key
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        deduped.append(entry)

    results = []
    for score, why, job, company_name, company_careers_url in deduped[:limit]:
        job_item = JobListItem(
            id=job.id,
            title=job.title,
            company_name=company_name,
            company_id=job.company_id,
            company_domain=root_domain(company_careers_url),
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
