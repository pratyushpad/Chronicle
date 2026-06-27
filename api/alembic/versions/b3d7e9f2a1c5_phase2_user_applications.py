"""phase2 user applications notifications

Revision ID: b3d7e9f2a1c5
Revises: 6b6a06f1fcbe
Create Date: 2026-06-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b3d7e9f2a1c5"
down_revision = "6b6a06f1fcbe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enrich jobs ───────────────────────────────────────────────────────────
    op.add_column("jobs", sa.Column("tech_tags", postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column("jobs", sa.Column("salary_min", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("salary_max", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("sponsorship_flag", sa.String(), nullable=True, server_default="unknown"))

    # ── Users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("auth_provider", sa.String(), nullable=False),
        sa.Column("auth_provider_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("auth_provider", "auth_provider_id", name="uq_users_provider"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ── Profiles ──────────────────────────────────────────────────────────────
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("headline", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("remote_pref", sa.String(), nullable=True),
        sa.Column("seniority_pref", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("tracks", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("tech_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("salary_floor", sa.Integer(), nullable=True),
        sa.Column("needs_sponsorship", sa.Boolean(), nullable=True),
        sa.Column("links", postgresql.JSONB(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Saved jobs ────────────────────────────────────────────────────────────
    op.create_table(
        "saved_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_saved_jobs"),
    )
    op.create_index("ix_saved_jobs_user", "saved_jobs", ["user_id"])

    # ── Applications ──────────────────────────────────────────────────────────
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="saved"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("next_action_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_applications"),
    )
    op.create_index("ix_applications_user", "applications", ["user_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    # ── Application events ────────────────────────────────────────────────────
    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_events_application", "application_events", ["application_id"])

    # ── Saved searches ────────────────────────────────────────────────────────
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("query_json", postgresql.JSONB(), nullable=False),
        sa.Column("alert_frequency", sa.String(), nullable=False, server_default="off"),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saved_searches_user", "saved_searches", ["user_id"])

    # ── Notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user", "notifications", ["user_id"])

    # ── Email outbox ──────────────────────────────────────────────────────────
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_outbox")
    op.drop_table("notifications")
    op.drop_table("saved_searches")
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("saved_jobs")
    op.drop_table("profiles")
    op.drop_table("users")
    op.drop_column("jobs", "sponsorship_flag")
    op.drop_column("jobs", "salary_max")
    op.drop_column("jobs", "salary_min")
    op.drop_column("jobs", "tech_tags")
