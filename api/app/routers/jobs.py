import logging
from datetime import date, datetime, timedelta, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select, text, true
from sqlalchemy.orm import Session, defer

from app.db import get_session
from app.models import Company, IngestRun, Job, JOB_SEARCH_FTS_EXPR
from app.industries import canonical_industry, fold_counts, raw_labels
from app.ingest.description import description_blocks, description_plain, description_summary
from app.job_items import job_list_item
from app.schemas import (
    CompanyDetail,
    CompanyItem,
    CompanyVelocity,
    Freshness,
    IndustryCount,
    JobDetail,
    JobListItem,
    JobListResponse,
    LastRunSummary,
    MetaResponse,
    SitemapJob,
    SitemapJobsResponse,
    VelocityPoint,
)

# Title keywords used to bucket senior-level roles when experience_level is blank.
_SENIOR_REGEX = r"\m(senior|sr|staff|principal|lead|distinguished|architect)\M"

router = APIRouter()

logger = logging.getLogger(__name__)


# Full-text match/rank built from the SAME expression as the functional GIN index
# (JOB_SEARCH_FTS_EXPR), so the planner uses ix_jobs_search_fts. Column refs are
# unqualified — unambiguous against the jobs⋈companies join (these columns are jobs-only).
# Distinct bindparam names let match (WHERE) and rank (ORDER BY) coexist in one statement.
def _fts_match(q: str):
    return text(
        f"({JOB_SEARCH_FTS_EXPR}) @@ websearch_to_tsquery('english', :fts_match_q)"
    ).bindparams(fts_match_q=q)


def _fts_rank_desc(q: str):
    return text(
        f"ts_rank_cd(({JOB_SEARCH_FTS_EXPR}), websearch_to_tsquery('english', :fts_rank_q)) DESC"
    ).bindparams(fts_rank_q=q)


def _db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


# Quick-filter "level" pills map experience_level OR a title keyword, because
# experience_level is sparsely populated (most jobs leave it blank).
# `title_regex` uses Postgres word boundaries (\m \M) so "Intern"/"Internship"
# match but "International"/"Internal" do not.
_LEVEL_FILTERS: dict[str, dict] = {
    "intern": {
        "experience_level": "Internship",
        "title_regex": r"\mintern(ship)?s?\M",
    },
    "new_grad": {
        "experience_level": "Entry Level",
        "title_patterns": ["%new grad%", "%new graduate%", "%university grad%", "%entry level%"],
    },
}


# A role's age: its first-published date, but never later than the day Chronicle first
# saw it live (a role can't be posted after we saw it — this also neutralizes re-publish
# dates). LEAST skips NULLs, so an unknown publish date falls back to first_seen_at.
# Used everywhere age matters: feed order, posted_after, recommendations.
JOB_AGE = func.least(Job.posted_at, Job.first_seen_at)


def _last_run_start(session: Session) -> datetime | None:
    return session.execute(
        select(IngestRun.started_at).order_by(IngestRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    q: Optional[str] = Query(None),
    mode: str = Query("keyword", pattern="^(keyword|semantic|hybrid)$"),
    company: Optional[str] = Query(None),
    company_id: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    remote: Optional[bool] = Query(None),
    employment_type: Optional[str] = Query(None),
    experience_level: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    posted_after: Optional[date] = Query(None),
    since_last_run: bool = Query(False),
    # newest (alias posted_at, the default) | relevance (default when q is set) | pay |
    # first_seen. Anything unrecognized keeps the old behaviour (first_seen).
    sort: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(_db),
):
    last_start = _last_run_start(session)
    sort_key = (sort or ("relevance" if q else "newest")).lower()
    if sort_key in ("newest", "posted_at", "relevance"):
        order_col = JOB_AGE
    elif sort_key == "pay":
        # Annualized pay (sort-only column); roles that don't state pay go last.
        order_col = func.coalesce(Job.salary_max, Job.salary_min)
    else:
        order_col = Job.first_seen_at

    # All filter statements join Company because several filters reference it.
    # include_q=False leaves out the free-text match — the semantic arm ranks by
    # vector similarity instead. use_fts picks the free-text matcher: True = Postgres
    # full-text (`search_tsv @@ websearch_to_tsquery`), False = the legacy ILIKE title
    # substring used only as a defensive fallback when FTS is unavailable.
    def _apply_filters(s, include_q: bool = True, use_fts: bool = True):
        if q and include_q:
            if use_fts:
                s = s.where(_fts_match(q))
            else:
                s = s.where(Job.title.ilike(f"%{q}%"))
        if company:
            s = s.where(Company.name.ilike(f"%{company}%"))
        if company_id:
            s = s.where(Job.company_id == company_id)
        if department:
            # Exact (case-insensitive): the vocabulary is closed, and a substring match made
            # department=IT also return Quality and Security.
            s = s.where(func.lower(Job.department) == department.strip().lower())
        if location:
            # The filter sends a canonical value ("chicago, il" / "remote"). Match on the
            # city token so every raw variant of that place is caught ("chicago",
            # "chicago, il, usa", "chicago; nyc; sf"); "remote" matches the remote flag/word.
            loc = location.strip().lower()
            if loc == "remote":
                s = s.where(or_(Job.remote == True, Job.location_normalized.ilike("%remote%")))  # noqa: E712
            else:
                city = loc.split(",")[0].strip()
                s = s.where(Job.location_normalized.ilike(f"%{city}%"))
        if remote is not None:
            s = s.where(Job.remote == remote)
        if employment_type:
            s = s.where(Job.employment_type.ilike(f"%{employment_type}%"))
        if experience_level:
            s = s.where(Job.experience_level.ilike(f"%{experience_level}%"))
        if level and level in _LEVEL_FILTERS:
            cfg = _LEVEL_FILTERS[level]
            conds = [Job.experience_level == cfg["experience_level"]]
            if cfg.get("title_regex"):
                conds.append(Job.title.op("~*")(cfg["title_regex"]))
            conds += [Job.title.ilike(pat) for pat in cfg.get("title_patterns", [])]
            s = s.where(or_(*conds))
        if industry:
            s = s.where(_industry_filter(industry))
        if posted_after:
            # JOB_AGE, not posted_at: an unknown publish date must not silently drop the role.
            s = s.where(JOB_AGE >= datetime(posted_after.year, posted_after.month, posted_after.day, tzinfo=timezone.utc))
        if since_last_run and last_start:
            s = s.where(Job.first_seen_at >= last_start)
        return s

    base = lambda *cols, **kw: _apply_filters(
        select(*cols).join(Company).where(Job.is_active == True), **kw
    )

    if mode in ("semantic", "hybrid") and q:
        try:
            return _fused_search(
                session=session,
                base=base,
                mode=mode,
                q=q,
                order_col=order_col,
                last_start=last_start,
                page=page,
                page_size=page_size,
            )
        except Exception:
            # Never let a missing/broken embedding model 500 the feed: degrade
            # semantic/hybrid to keyword ranking so the live app keeps working.
            session.rollback()
            logger.warning(
                "semantic search failed for mode=%s; falling back to keyword", mode,
                exc_info=True,
            )

    # Keyword mode with a query → relevance-ranked full-text search, with a defensive
    # fall-through to the legacy ILIKE recency feed if FTS is unavailable (e.g. the
    # migration has not been applied yet).
    if q:
        try:
            if sort_key == "relevance":
                return _fts_keyword_search(session, base, q, last_start, page, page_size)
            # Full-text match, ordered by the chosen sort (newest, pay …) instead of rank.
            return _keyword_search(session, base, order_col, last_start, page, page_size, use_fts=True)
        except Exception:
            session.rollback()
            logger.warning("FTS keyword search failed; falling back to ILIKE", exc_info=True)

    # Reached with no query (plain recency feed) or as the ILIKE fallback above; either
    # way the free-text matcher here is the legacy ILIKE path.
    return _keyword_search(
        session, base, order_col, last_start, page, page_size, use_fts=False
    )


def _keyword_search(
    session: Session,
    base,
    order_col,
    last_start: datetime | None,
    page: int,
    page_size: int,
    use_fts: bool = False,
) -> JobListResponse:
    """Recency-ordered keyword feed: one representative posting per dedup_key."""
    # Total = distinct roles, collapsing cross-posted city duplicates.
    keys_sub = base(Job.dedup_key, use_fts=use_fts).subquery()
    total = session.execute(
        select(func.count(func.distinct(keys_sub.c.dedup_key)))
    ).scalar_one()

    # One representative row per dedup_key (the most recent posting), then page
    # those representatives ordered by recency.
    rep_ids = (
        base(Job.id, Job.dedup_key, use_fts=use_fts)
        .distinct(Job.dedup_key)
        .order_by(Job.dedup_key, order_col.desc().nullslast(), JOB_AGE.desc().nullslast())
    ).subquery()
    page_stmt = (
        select(Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Company)
        .where(Job.id.in_(select(rep_ids.c.id)))
        # Ties (e.g. equal pay) fall back to newest first.
        .order_by(order_col.desc().nullslast(), JOB_AGE.desc().nullslast(), Job.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = session.execute(page_stmt).all()
    return _build_response(session, rows, last_start, total, page, page_size)


def _fts_keyword_search(
    session: Session,
    base,
    q: str,
    last_start: datetime | None,
    page: int,
    page_size: int,
) -> JobListResponse:
    """Relevance-ranked keyword feed: Postgres full-text, ordered by ts_rank_cd.

    Unlike the recency feed, the representative per dedup_key is the best-ranked
    posting (not the most recent). Any execution error (e.g. the migration not yet
    applied) propagates to the caller, which falls back to the ILIKE recency path.
    """
    rank_desc = _fts_rank_desc(q)

    keys_sub = base(Job.dedup_key).subquery()
    total = session.execute(
        select(func.count(func.distinct(keys_sub.c.dedup_key)))
    ).scalar_one()

    # Best-ranked representative per dedup_key.
    rep_ids = (
        base(Job.id, Job.dedup_key)
        .distinct(Job.dedup_key)
        .order_by(Job.dedup_key, rank_desc)
    ).subquery()
    page_stmt = (
        select(Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Company)
        .where(Job.id.in_(select(rep_ids.c.id)))
        .order_by(_fts_rank_desc(q), Job.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = session.execute(page_stmt).all()
    return _build_response(session, rows, last_start, total, page, page_size)


def _build_response(
    session: Session,
    rows,
    last_start: datetime | None,
    total: int,
    page: int,
    page_size: int,
    search_mode: str | None = None,
) -> JobListResponse:
    """Assemble JobListItems (+ sibling-location aggregation) for one page of rows."""
    keys = [row.Job.dedup_key for row in rows]
    loc_map: dict[str, list[str]] = {}
    if keys:
        for k, locs in session.execute(
            select(Job.dedup_key, func.array_agg(func.distinct(Job.location_normalized)))
            .where(Job.dedup_key.in_(keys), Job.is_active == True, Job.location_normalized != None)
            .group_by(Job.dedup_key)
        ).all():
            loc_map[k] = sorted(l for l in (locs or []) if l)

    items = []
    for row in rows:
        job = row.Job
        is_new = bool(last_start and job.first_seen_at >= last_start)
        locs = loc_map.get(job.dedup_key, [])
        items.append(
            job_list_item(
                job, row.company_name, row.company_careers_url,
                locations=locs or None, location_count=len(locs) or None, is_new=is_new,
            )
        )

    return JobListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, ceil(total / page_size)),
        search_mode=search_mode,
    )


# Per-arm candidate depth for semantic/hybrid search. Relevance-ranked modes
# intentionally top out around this many distinct roles per query.
_FUSION_ARM_LIMIT = 200


def _fused_search(
    session: Session,
    base,
    mode: str,
    q: str,
    order_col,
    last_start: datetime | None,
    page: int,
    page_size: int,
) -> JobListResponse:
    """Semantic / hybrid ranking: pgvector cosine arm (+ keyword arm), RRF-fused.

    Unlike the keyword path (representative = most recent posting), the
    representative per dedup_key here is the best-matching posting.
    """
    from app.ml.embedder import get_embedder
    from app.search.rrf import rrf_fuse

    qvec = get_embedder().encode([q])[0]

    semantic_rows = session.execute(
        base(Job.id, Job.dedup_key, include_q=False)
        .where(Job.embedding.isnot(None))
        .order_by(Job.embedding.cosine_distance(qvec))
        .limit(_FUSION_ARM_LIMIT)
    ).all()

    rankings = [[row.id for row in semantic_rows]]
    dedup_of = {row.id: row.dedup_key for row in semantic_rows}

    if mode == "hybrid":
        # Lexical arm: real full-text relevance (ts_rank_cd), so RRF fuses genuine
        # keyword ranks with the vector ranks — not substring-then-recency.
        keyword_rows = session.execute(
            base(Job.id, Job.dedup_key)
            .order_by(_fts_rank_desc(q), Job.id.desc())
            .limit(_FUSION_ARM_LIMIT)
        ).all()
        rankings.append([row.id for row in keyword_rows])
        dedup_of.update({row.id: row.dedup_key for row in keyword_rows})

    fused_ids = rrf_fuse(rankings)

    # First occurrence per dedup_key wins (best match, not most recent).
    seen_keys: set[str] = set()
    deduped_ids: list[int] = []
    for job_id in fused_ids:
        key = dedup_of[job_id]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_ids.append(job_id)

    total = len(deduped_ids)
    page_ids = deduped_ids[(page - 1) * page_size : page * page_size]

    rows = []
    if page_ids:
        fetched = session.execute(
            select(Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
            .join(Company)
            .where(Job.id.in_(page_ids))
        ).all()
        by_id = {row.Job.id: row for row in fetched}
        rows = [by_id[i] for i in page_ids if i in by_id]

    return _build_response(session, rows, last_start, total, page, page_size, search_mode=mode)


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: int, session: Session = Depends(_db)):
    row = session.execute(
        select(Job, Company.name.label("company_name"), Company.industry.label("company_industry"))
        .join(Company)
        .where(Job.id == job_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    job = row.Job
    return JobDetail(
        id=job.id,
        title=job.title,
        company_name=row.company_name,
        company_id=job.company_id,
        company_industry=canonical_industry(row.company_industry),
        location_raw=job.location_raw,
        location_normalized=job.location_normalized,
        remote=job.remote,
        department=job.department,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        # These were declared on JobDetail but never passed, so the detail page always
        # received None for pay, tags and sponsorship.
        tech_tags=job.tech_tags,
        sponsorship_flag=job.sponsorship_flag,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        pay_min=float(job.pay_min) if job.pay_min is not None else None,
        pay_max=float(job.pay_max) if job.pay_max is not None else None,
        pay_currency=job.pay_currency,
        pay_period=job.pay_period,
        pay_source=job.pay_source,
        description_text=description_plain(job.description_text),
        description_blocks=description_blocks(job.description_text),
        description_summary=description_summary(job.description_text),
        apply_url=job.apply_url,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        is_active=bool(job.is_active),
    )


def _industry_filter(industry: str):
    """A canonical name, or any raw label that folds into one (older links send "AI/ML"),
    matches every raw label in that group. Anything else keeps the old substring match."""
    canon = canonical_industry(industry)
    labels = raw_labels(canon) if canon else None
    if labels is not None:
        return func.lower(func.trim(Company.industry)).in_([label.lower() for label in labels])
    return Company.industry.ilike(f"%{industry}%")


# Similar roles: nearest active neighbours of the job's embedding. A few extra rows are
# fetched so that duplicates of one role (same dedup_key, e.g. a posting per city) and the
# job's own duplicates can be dropped and still leave `limit` distinct roles.
_SIMILAR_OVERFETCH = 4


@router.get("/jobs/{job_id}/similar", response_model=list[JobListItem])
def similar_jobs(
    job_id: int,
    limit: int = Query(4, ge=1, le=12),
    session: Session = Depends(_db),
):
    source = session.execute(
        select(Job.embedding, Job.dedup_key).where(Job.id == job_id)
    ).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if source.embedding is None:
        return []  # not embedded yet: no honest notion of "similar"
    distance = Job.embedding.cosine_distance(source.embedding)
    rows = session.execute(
        select(Job, Company.name.label("company_name"), Company.careers_url.label("company_careers_url"))
        .join(Company)
        .where(
            Job.is_active == True,  # noqa: E712
            Job.embedding.isnot(None),
            Job.id != job_id,
            Job.dedup_key != source.dedup_key,
        )
        .order_by(distance)
        .limit(limit * _SIMILAR_OVERFETCH)
        # List cards never read these; skip loading 20 KB descriptions and vectors.
        .options(defer(Job.description_text), defer(Job.embedding))
    ).all()
    seen: set[str] = set()
    items = []
    for row in rows:
        if row.Job.dedup_key in seen:
            continue
        seen.add(row.Job.dedup_key)
        items.append(job_list_item(row.Job, row.company_name, row.company_careers_url))
        if len(items) == limit:
            break
    return items


# Sitemap source: one URL per distinct active role, paged by id. The lowest id of each
# dedup_key is used because it is stable across runs (the feed's representative is the
# most recent posting, which can change), so search engines see a steady URL set.
@router.get("/sitemap/jobs", response_model=SitemapJobsResponse)
def sitemap_jobs(
    offset: int = Query(0, ge=0),
    limit: int = Query(10_000, ge=1, le=20_000),
    session: Session = Depends(_db),
):
    firsts = (
        select(func.min(Job.id).label("id"), func.max(Job.last_seen_at).label("last_seen_at"))
        .where(Job.is_active == True)  # noqa: E712
        .group_by(Job.dedup_key)
        .subquery()
    )
    total = session.execute(select(func.count()).select_from(firsts)).scalar_one()
    rows = session.execute(
        select(firsts.c.id, firsts.c.last_seen_at).order_by(firsts.c.id).offset(offset).limit(limit)
    ).all()
    return SitemapJobsResponse(
        total=total,
        items=[SitemapJob(id=r.id, last_seen_at=r.last_seen_at) for r in rows],
    )


@router.get("/companies", response_model=list[CompanyItem])
def list_companies(
    industry: Optional[str] = Query(None),
    session: Session = Depends(_db),
):
    stmt = (
        select(Company, func.count(func.distinct(Job.dedup_key)).label("active_job_count"))
        .outerjoin(Job, (Job.company_id == Company.id) & (Job.is_active == True))
        .where(Company.active == True)
        .group_by(Company.id)
        .order_by(Company.name)
    )
    if industry:
        stmt = stmt.where(_industry_filter(industry))
    rows = session.execute(stmt).all()
    return [
        CompanyItem(
            id=row.Company.id,
            name=row.Company.name,
            ats=row.Company.ats.value,
            careers_url=row.Company.careers_url,
            industry=canonical_industry(row.Company.industry),
            active_job_count=row.active_job_count,
        )
        for row in rows
    ]


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, session: Session = Depends(_db)):
    row = session.execute(
        select(Company, func.count(func.distinct(Job.dedup_key)).label("active_job_count"))
        .outerjoin(Job, (Job.company_id == Company.id) & (Job.is_active == True))
        .where(Company.id == company_id, Company.active == True)
        .group_by(Company.id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyDetail(
        id=row.Company.id,
        name=row.Company.name,
        ats=row.Company.ats.value,
        careers_url=row.Company.careers_url,
        industry=canonical_industry(row.Company.industry),
        active_job_count=row.active_job_count,
        last_ingested_at=row.Company.last_ingested_at,
    )


@router.get("/companies/{company_id}/velocity", response_model=CompanyVelocity)
def company_velocity(company_id: int, weeks: int = 8, session: Session = Depends(_db)):
    """Hiring velocity: roles opened and closed per recent ISO week.

    "Opened" dates a role by its age (LEAST(posted_at, first_seen_at)): the board's own
    publish date when it gives one, else when Chronicle first saw it. A role with no
    publish date that was first seen in the week Chronicle first read this board is left
    out: it was already open then, and counting it made the first ingest look like a
    hiring spike (Anduril: 853 "opened" in its first week). "Closed" is the week a role
    was last seen live before it left the board. No new data is stored."""
    weeks = max(1, min(weeks, 26))
    company = session.get(Company, company_id)
    if not company or not company.active:
        raise HTTPException(status_code=404, detail="Company not found")

    now = datetime.now(timezone.utc)
    # Monday 00:00 UTC of the current ISO week, then walk back `weeks-1` weeks.
    this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    window = [(this_monday - timedelta(weeks=i)).date() for i in range(weeks - 1, -1, -1)]
    since = this_monday - timedelta(weeks=weeks - 1)

    first_seen_any = session.execute(
        select(func.min(Job.first_seen_at)).where(Job.company_id == company_id)
    ).scalar_one()
    if first_seen_any is not None:
        first_seen_any = first_seen_any.astimezone(timezone.utc)
        first_week_start = first_seen_any - timedelta(days=first_seen_any.weekday())
        first_week_start = first_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        first_ingest_artifact = and_(
            Job.posted_at.is_(None),
            Job.first_seen_at < first_week_start + timedelta(weeks=1),
        )
        counts_as_opened = ~first_ingest_artifact
    else:
        first_ingest_artifact = counts_as_opened = true()

    def _bucket(when_col, count_col, *conds) -> dict[date, int]:
        # Weeks in UTC whatever the session time zone, to match `window` above.
        wk = func.date_trunc("week", func.timezone("UTC", when_col))
        rows = session.execute(
            select(wk.label("wk"), count_col)
            .where(Job.company_id == company_id, when_col >= since, *conds)
            .group_by("wk")
        ).all()
        return {r[0].date(): r[1] for r in rows}

    opened = _bucket(JOB_AGE, func.count(func.distinct(Job.dedup_key)), counts_as_opened)
    closed = _bucket(Job.last_seen_at, func.count(Job.id), Job.is_active == False)

    points = [VelocityPoint(week=w, opened=opened.get(w, 0), closed=closed.get(w, 0)) for w in window]

    active_now = session.execute(
        select(func.count(func.distinct(Job.dedup_key)))
        .where(Job.company_id == company_id, Job.is_active == True)
    ).scalar_one()
    d30 = now - timedelta(days=30)
    opened_30 = session.execute(
        select(func.count(func.distinct(Job.dedup_key)))
        .where(Job.company_id == company_id, JOB_AGE >= d30, counts_as_opened)
    ).scalar_one()
    closed_30 = session.execute(
        select(func.count(Job.id))
        .where(Job.company_id == company_id, Job.is_active == False, Job.last_seen_at >= d30)
    ).scalar_one()
    excluded = 0
    # Reported only when the first-ingest week is on the chart, where it explains a gap.
    if first_seen_any is not None and first_week_start >= since:
        excluded = session.execute(
            select(func.count(func.distinct(Job.dedup_key)))
            .where(Job.company_id == company_id, first_ingest_artifact)
        ).scalar_one()

    return CompanyVelocity(
        company_id=company_id,
        weeks=points,
        new_this_week=points[-1].opened if points else 0,
        active_now=active_now,
        opened_last_30d=opened_30,
        closed_last_30d=closed_30,
        first_ingest_excluded=excluded,
    )


# /meta is ~15 aggregate queries (full-table DISTINCTs + regex COUNTs) whose inputs only
# change after an ingest run, so it's cached in-process with a short TTL. This keeps it off
# the critical path of every page load (it gates the jobs feed's server-side Promise.all).
_META_CACHE: dict[str, tuple[float, MetaResponse]] = {}
_META_TTL_SECONDS = 300


def invalidate_meta_cache() -> None:
    """Drop the cached /meta payload. Called at the end of an ingest run so the freshness
    label and "NEW SINCE LAST RUN" counts reflect the new run immediately instead of
    waiting out the TTL."""
    _META_CACHE.pop("meta", None)


@router.get("/meta", response_model=MetaResponse)
def get_meta(session: Session = Depends(_db)):
    import time

    cached = _META_CACHE.get("meta")
    if cached is not None and (time.monotonic() - cached[0]) < _META_TTL_SECONDS:
        return cached[1]
    result = _compute_meta(session)
    _META_CACHE["meta"] = (time.monotonic(), result)
    return result


# A metro must have at least this many active roles to appear in the filter.
_LOCATION_MIN_COUNT = 5

# Curated major job metros: (canonical display, city match-token). The location filter
# shows only these + Remote — a clean, scannable list of the main places instead of the
# thousands of raw ATS location variants ("Chicago", "Chicago, IL", "Chicago, IL, USA",
# "Chicago; NYC; SF", …). Matching is on the city token, so one option catches every variant.
_MAJOR_METROS: list[tuple[str, str]] = [
    ("san francisco, ca", "san francisco"), ("new york, ny", "new york"),
    ("seattle, wa", "seattle"), ("austin, tx", "austin"), ("los angeles, ca", "los angeles"),
    ("chicago, il", "chicago"), ("boston, ma", "boston"), ("denver, co", "denver"),
    ("atlanta, ga", "atlanta"), ("washington, dc", "washington"), ("san jose, ca", "san jose"),
    ("palo alto, ca", "palo alto"), ("mountain view, ca", "mountain view"),
    ("san diego, ca", "san diego"), ("dallas, tx", "dallas"), ("houston, tx", "houston"),
    ("portland, or", "portland"), ("philadelphia, pa", "philadelphia"), ("miami, fl", "miami"),
    ("phoenix, az", "phoenix"), ("minneapolis, mn", "minneapolis"), ("detroit, mi", "detroit"),
    ("salt lake city, ut", "salt lake city"), ("nashville, tn", "nashville"),
    ("raleigh, nc", "raleigh"), ("pittsburgh, pa", "pittsburgh"), ("boulder, co", "boulder"),
    ("toronto", "toronto"), ("vancouver", "vancouver"), ("london", "london"),
    ("dublin", "dublin"), ("berlin", "berlin"), ("amsterdam", "amsterdam"), ("paris", "paris"),
    ("munich", "munich"), ("bangalore", "bangalore"), ("hyderabad", "hyderabad"),
    ("singapore", "singapore"), ("sydney", "sydney"), ("tel aviv", "tel aviv"), ("tokyo", "tokyo"),
]


def _canonical_locations(session: Session) -> list[str]:
    """Location filter list: Remote (pinned first) + the curated major metros that actually
    have roles in the corpus, sorted alphabetically. The main places users search for,
    without the thousands of raw ATS variants."""
    rows = session.execute(
        select(Job.location_normalized, func.count())
        .where(Job.is_active == True, Job.location_normalized != None)  # noqa: E712
        .group_by(Job.location_normalized)
    ).all()
    remote = sum(cnt for loc, cnt in rows if "remote" in loc)
    present = [
        display
        for display, token in _MAJOR_METROS
        if sum(cnt for loc, cnt in rows if token in loc) >= _LOCATION_MIN_COUNT
    ]
    present.sort()  # alphabetical
    return (["remote"] + present) if remote else present


def _freshness(session: Session) -> Freshness:
    """How recently active boards were re-checked. `last_ingested_at` is stamped only
    after a board's jobs are committed, so a failing board keeps its last good time."""
    now = datetime.now(timezone.utc)
    stamps = session.execute(
        select(Company.last_ingested_at).where(Company.active == True)  # noqa: E712
    ).scalars().all()
    checked = [t for t in stamps if t is not None]
    ages = sorted((now - t).total_seconds() / 3600 for t in checked)
    median = None
    if ages:
        mid = len(ages) // 2
        median = ages[mid] if len(ages) % 2 else (ages[mid - 1] + ages[mid]) / 2
    return Freshness(
        boards_active=len(stamps),
        boards_checked_24h=sum(1 for a in ages if a <= 24),
        boards_checked_7d=sum(1 for a in ages if a <= 24 * 7),
        median_check_age_hours=round(median, 1) if median is not None else None,
        oldest_check_at=min(checked) if checked else None,
    )


def _compute_meta(session: Session) -> MetaResponse:
    def distinct_col(col):
        return [
            r[0]
            for r in session.execute(
                select(col).where(Job.is_active == True, col != None).distinct().order_by(col)
            ).all()
        ]

    industries = sorted({
        name
        for (raw,) in session.execute(
            select(Company.industry).where(Company.active == True, Company.industry != None).distinct()
        ).all()
        if (name := canonical_industry(raw))
    })

    total_active = session.execute(
        select(func.count(func.distinct(Job.dedup_key))).select_from(Job).where(Job.is_active == True)
    ).scalar_one()
    total_companies = session.execute(
        select(func.count()).select_from(Company).where(Company.active == True)
    ).scalar_one()

    last_run_row = session.execute(
        select(IngestRun).order_by(IngestRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()

    last_run = None
    if last_run_row:
        last_run = LastRunSummary(
            started_at=last_run_row.started_at,
            jobs_seen=last_run_row.jobs_seen,
            jobs_new=last_run_row.jobs_new,
            companies_ok=last_run_row.companies_ok,
            companies_failed=last_run_row.companies_failed,
        )

    # ── Landing-page aggregates ──────────────────────────────────────────────
    def _count(*conds) -> int:
        return session.execute(
            select(func.count(func.distinct(Job.dedup_key))).select_from(Job).where(Job.is_active == True, *conds)
        ).scalar_one()

    last_start = _last_run_start(session)
    fresh_since_last_run = _count(Job.first_seen_at >= last_start) if last_start else 0
    remote_count = _count(Job.remote == True)

    def _level_count(level: str) -> int:
        cfg = _LEVEL_FILTERS[level]
        conds = [Job.experience_level == cfg["experience_level"]]
        if cfg.get("title_regex"):
            conds.append(Job.title.op("~*")(cfg["title_regex"]))
        conds += [Job.title.ilike(pat) for pat in cfg.get("title_patterns", [])]
        return _count(or_(*conds))

    experience_counts = {
        "intern": _level_count("intern"),
        "new_grad": _level_count("new_grad"),
        "senior": _count(
            or_(Job.experience_level == "Senior", Job.title.op("~*")(_SENIOR_REGEX))
        ),
    }

    # Counted per raw label, then folded into canonical names (a role belongs to one
    # company, so the per-label distinct counts add up exactly).
    top_industry_rows = session.execute(
        select(Company.industry, func.count(func.distinct(Job.dedup_key)))
        .join(Job, (Job.company_id == Company.id) & (Job.is_active == True))
        .where(Company.active == True, Company.industry != None)
        .group_by(Company.industry)
    ).all()
    top_industries = [IndustryCount(industry=n, count=c) for n, c in fold_counts(top_industry_rows)[:8]]

    return MetaResponse(
        departments=distinct_col(Job.department),
        locations=_canonical_locations(session),
        employment_types=distinct_col(Job.employment_type),
        experience_levels=distinct_col(Job.experience_level),
        industries=industries,
        last_run=last_run,
        total_active_jobs=total_active,
        total_companies=total_companies,
        fresh_since_last_run=fresh_since_last_run,
        remote_count=remote_count,
        experience_counts=experience_counts,
        top_industries=top_industries,
        freshness=_freshness(session),
    )
