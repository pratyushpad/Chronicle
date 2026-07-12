import enum
from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


def _now():
    return datetime.now(timezone.utc)


# Weighted full-text expression for Job keyword ranking. Weight A = title (dominant
# relevance), C = department + normalized location. Materialized as a FUNCTIONAL GIN INDEX
# (no column, no table rewrite) rather than a STORED tsvector: a stored column of the
# description body bloats storage and its ADD rewrites the table past Neon's 512 MB free
# tier. Every function here is IMMUTABLE (required for an index expression) — note tech_tags
# is intentionally omitted because array_to_string is only STABLE; the description body is
# omitted for size. Semantic search covers body/skill meaning; company_name lives on Company
# (separate ILIKE filter). Column refs are unqualified so the identical expression works both
# in the CREATE INDEX (mirrored in the Alembic migration) and in the jobs.py queries against
# the jobs⋈companies join.
JOB_SEARCH_FTS_EXPR = (
    "setweight(to_tsvector('english', coalesce(title,'')), 'A') || "
    "setweight(to_tsvector('english', "
    "coalesce(department,'') || ' ' || coalesce(location_normalized,'')), 'C')"
)


class Base(DeclarativeBase):
    pass


class ATSSource(str, enum.Enum):
    greenhouse = "greenhouse"
    lever = "lever"
    ashby = "ashby"


class RemotePref(str, enum.Enum):
    any = "any"
    remote = "remote"
    onsite = "onsite"
    hybrid = "hybrid"


class AppStatus(str, enum.Enum):
    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    archived = "archived"


class AlertFrequency(str, enum.Enum):
    off = "off"
    daily = "daily"
    weekly = "weekly"


class InteractionEvent(str, enum.Enum):
    impression = "impression"
    click = "click"
    save = "save"
    apply = "apply"
    dismiss = "dismiss"


class InteractionSurface(str, enum.Enum):
    feed = "feed"
    search = "search"
    alert = "alert"


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats", "slug"),)

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    ats = Column(Enum(ATSSource), nullable=False)
    slug = Column(String, nullable=False)
    careers_url = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    last_ingested_at = Column(DateTime(timezone=True), nullable=True)

    jobs = relationship("Job", back_populates="company")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id"),
        Index("ix_jobs_dedup_key", "dedup_key"),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_is_active", "is_active"),
        Index("ix_jobs_posted_at", "posted_at"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    source = Column(Enum(ATSSource), nullable=False)
    source_job_id = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    title_normalized = Column(Text, nullable=False)
    location_raw = Column(Text, nullable=True)
    location_normalized = Column(Text, nullable=True)
    remote = Column(Boolean, nullable=True)
    department = Column(Text, nullable=True)  # normalized controlled-vocab category
    department_raw = Column(Text, nullable=True)  # untouched original ATS value (retune escape hatch)
    employment_type = Column(Text, nullable=True)
    description_html = Column(Text, nullable=True)
    description_text = Column(Text, nullable=True)
    apply_url = Column(Text, nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    dedup_key = Column(String(40), nullable=False)
    experience_level = Column(String, nullable=True)
    # Heuristic enrichment columns
    tech_tags = Column(ARRAY(String), nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    sponsorship_flag = Column(String, nullable=True, default="unknown")
    # all-MiniLM-L6-v2 vector of build_embedding_text(); NULL until embedded
    embedding = Column(Vector(384), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # sha256 of the embed text; lets incremental ingest re-embed only changed content
    # (not just rows where embedding IS NULL). NULL for legacy rows until first re-ingest.
    content_hash = Column(String(64), nullable=True)
    # Full-text keyword ranking is served by a functional GIN index on JOB_SEARCH_FTS_EXPR
    # (created in the Alembic migration), not a stored column — see the constant's note.

    company = relationship("Company", back_populates="jobs")


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    companies_total = Column(Integer, nullable=False, default=0)
    companies_ok = Column(Integer, nullable=False, default=0)
    companies_failed = Column(Integer, nullable=False, default=0)
    jobs_seen = Column(Integer, nullable=False, default=0)
    jobs_new = Column(Integer, nullable=False, default=0)
    jobs_closed = Column(Integer, nullable=False, default=0)
    failures = Column(JSONB, nullable=False, default=list)


# ── Phase 2: User identity ────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("auth_provider", "auth_provider_id"),)

    id = Column(Integer, primary_key=True)
    auth_provider = Column(String, nullable=False)
    auth_provider_id = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    # sha256 of the browser-extension bearer token (plaintext shown once at issue). Null = no token.
    extension_token_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    saved_searches = relationship("SavedSearch", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    full_name = Column(String, nullable=True)
    headline = Column(String, nullable=True)
    location = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    work_authorization = Column(String, nullable=True)  # e.g. "US Citizen", "H-1B", "Need sponsorship"
    remote_pref = Column(Enum(RemotePref), nullable=True)
    seniority_pref = Column(ARRAY(String), nullable=True)
    tracks = Column(ARRAY(String), nullable=True)
    tech_tags = Column(ARRAY(String), nullable=True)
    salary_floor = Column(Integer, nullable=True)
    needs_sponsorship = Column(Boolean, nullable=True)
    links = Column(JSONB, nullable=True)
    # Free text: "what I'm looking for" — embedded into the profile vector.
    about = Column(Text, nullable=True)
    # Extracted resume text (never the file itself); embedded in chunks.
    resume_text = Column(Text, nullable=True)
    resume_updated_at = Column(DateTime(timezone=True), nullable=True)
    # profile-text + engaged-jobs centroid vector; see app/ml/profile_embedding.py
    embedding = Column(Vector(384), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="profile")

    @property
    def resume_chars(self) -> int | None:
        return len(self.resume_text) if self.resume_text else None


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    status = Column(Enum(AppStatus), nullable=False, default=AppStatus.saved)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    next_action = Column(Text, nullable=True)
    next_action_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="applications")
    job = relationship("Job")
    events = relationship("ApplicationEvent", back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.at")


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    at = Column(DateTime(timezone=True), nullable=False, default=_now)

    application = relationship("Application", back_populates="events")


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    query_json = Column(JSONB, nullable=False)
    alert_frequency = Column(Enum(AlertFrequency), nullable=False, default=AlertFrequency.off)
    last_alerted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="saved_searches")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="notifications")


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body_html = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    event = Column(Enum(InteractionEvent), nullable=False)
    surface = Column(Enum(InteractionSurface), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (Index("ix_interactions_user_created", "user_id", "created_at"),)
