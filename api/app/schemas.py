from datetime import date, datetime
from typing import Any
from pydantic import BaseModel


class CompanyItem(BaseModel):
    id: int
    name: str
    ats: str
    careers_url: str | None
    industry: str | None
    active_job_count: int
    model_config = {"from_attributes": True}


class CompanyDetail(BaseModel):
    id: int
    name: str
    ats: str
    careers_url: str | None
    industry: str | None
    active_job_count: int
    last_ingested_at: datetime | None
    model_config = {"from_attributes": True}


class JobListItem(BaseModel):
    id: int
    title: str
    company_name: str
    company_id: int
    company_domain: str | None = None
    location_normalized: str | None
    remote: bool | None
    department: str | None
    employment_type: str | None
    experience_level: str | None
    tech_tags: list[str] | None = None
    sponsorship_flag: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    posted_at: datetime | None
    first_seen_at: datetime
    apply_url: str
    is_new: bool = False
    model_config = {"from_attributes": True}


class JobDetail(BaseModel):
    id: int
    title: str
    company_name: str
    company_id: int
    company_industry: str | None
    location_raw: str | None
    location_normalized: str | None
    remote: bool | None
    department: str | None
    employment_type: str | None
    experience_level: str | None
    tech_tags: list[str] | None = None
    sponsorship_flag: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    description_text: str | None
    apply_url: str
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    model_config = {"from_attributes": True}


class LastRunSummary(BaseModel):
    started_at: datetime | None
    jobs_seen: int
    jobs_new: int
    companies_ok: int
    companies_failed: int


class IndustryCount(BaseModel):
    industry: str
    count: int


class MetaResponse(BaseModel):
    departments: list[str]
    locations: list[str]
    employment_types: list[str]
    experience_levels: list[str]
    industries: list[str]
    last_run: LastRunSummary | None
    total_active_jobs: int
    total_companies: int
    # Landing-page aggregates
    fresh_since_last_run: int = 0
    remote_count: int = 0
    experience_counts: dict[str, int] = {}
    top_industries: list[IndustryCount] = []


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── User / Profile ────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    name: str | None
    avatar_url: str | None
    has_profile: bool
    model_config = {"from_attributes": True}


class UserSyncIn(BaseModel):
    email: str
    name: str | None = None
    avatar_url: str | None = None
    provider: str
    provider_id: str


class ProfileIn(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    remote_pref: str | None = None
    seniority_pref: list[str] | None = None
    tracks: list[str] | None = None
    tech_tags: list[str] | None = None
    salary_floor: int | None = None
    needs_sponsorship: bool | None = None
    links: dict[str, str] | None = None


class ProfileOut(ProfileIn):
    user_id: int
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Saved jobs ────────────────────────────────────────────────────────────────

class SavedJobOut(BaseModel):
    id: int
    job_id: int
    saved_at: datetime
    job: JobListItem
    model_config = {"from_attributes": True}


# ── Applications ──────────────────────────────────────────────────────────────

class ApplicationEventOut(BaseModel):
    id: int
    from_status: str | None
    to_status: str
    at: datetime
    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    status: str
    applied_at: datetime | None
    notes: str | None
    next_action: str | None
    next_action_date: date | None
    created_at: datetime
    updated_at: datetime
    job: JobListItem
    events: list[ApplicationEventOut] = []
    model_config = {"from_attributes": True}


class ApplicationCreateIn(BaseModel):
    job_id: int
    status: str = "saved"


class ApplicationUpdateIn(BaseModel):
    status: str | None = None
    notes: str | None = None
    next_action: str | None = None
    next_action_date: date | None = None


class FunnelStats(BaseModel):
    saved: int = 0
    applied: int = 0
    interviewing: int = 0
    offer: int = 0
    rejected: int = 0
    archived: int = 0
    response_rate: float = 0.0


# ── Recommendations ───────────────────────────────────────────────────────────

class RecommendedJob(BaseModel):
    job: JobListItem
    score: float
    why: str


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    type: str
    payload: dict[str, Any]
    read: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Saved searches ────────────────────────────────────────────────────────────

class SavedSearchIn(BaseModel):
    name: str
    query_json: dict[str, Any]
    alert_frequency: str = "off"


class SavedSearchOut(BaseModel):
    id: int
    name: str
    query_json: dict[str, Any]
    alert_frequency: str
    last_alerted_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}
