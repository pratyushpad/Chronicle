"""profiles.about + resume_text for real profile matching

Revision ID: b9d6f2a75c84
Revises: a8c5e1f64b73
Create Date: 2026-07-05

Free-text "about / what I'm looking for" and extracted resume text (we store
text only — never the uploaded file; Render disk is ephemeral anyway). Both
feed the profile embedding alongside the structured fields.
"""
from alembic import op
import sqlalchemy as sa

revision = "b9d6f2a75c84"
down_revision = "a8c5e1f64b73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("about", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("resume_text", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("resume_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "resume_updated_at")
    op.drop_column("profiles", "resume_text")
    op.drop_column("profiles", "about")
