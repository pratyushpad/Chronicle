"""jobs.content_hash for delta-only re-embedding

Revision ID: c1a2b3d4e5f6
Revises: b9d6f2a75c84
Create Date: 2026-07-11

Content hash (sha256 of the embed text) so incremental ingest can re-embed only rows
whose content actually changed, instead of only rows where embedding IS NULL. NULL for
existing rows until their next ingest pass recomputes it.
"""
from alembic import op
import sqlalchemy as sa

revision = "c1a2b3d4e5f6"
down_revision = "b9d6f2a75c84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("content_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "content_hash")
