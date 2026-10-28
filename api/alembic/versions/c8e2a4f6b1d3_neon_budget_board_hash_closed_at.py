"""companies.board_hash and jobs.closed_at (Neon budget)

Revision ID: c8e2a4f6b1d3
Revises: b7c2e4f6a8d1
Create Date: 2026-10-28

board_hash lets the daily ingest skip a board whose payload is unchanged. closed_at is
the prune clock: roles closed longer than PRUNE_INACTIVE_DAYS ago are hard-deleted.
Both are nullable and metadata-only on Postgres (no table rewrite).
"""
from alembic import op
import sqlalchemy as sa

revision = "c8e2a4f6b1d3"
down_revision = "b7c2e4f6a8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("board_hash", sa.String(length=64), nullable=True))
    op.add_column("jobs", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "closed_at")
    op.drop_column("companies", "board_hash")
