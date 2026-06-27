import enum
from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


def _now():
    return datetime.now(timezone.utc)


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
    department = Column(Text, nullable=True)
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
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

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
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    saved_jobs = relationship("SavedJob", back_populates="user", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    saved_searches = relationship("SavedSearch", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    full_name = Column(String, nullable=True)
    headline = Column(String, nullable=True)
    location = Column(String, nullable=True)
    remote_pref = Column(Enum(RemotePref), nullable=True)
    seniority_pref = Column(ARRAY(String), nullable=True)
    tracks = Column(ARRAY(String), nullable=True)
    tech_tags = Column(ARRAY(String), nullable=True)
    salary_floor = Column(Integer, nullable=True)
    needs_sponsorship = Column(Boolean, nullable=True)
    links = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="profile")


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    saved_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="saved_jobs")
    job = relationship("Job")


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
