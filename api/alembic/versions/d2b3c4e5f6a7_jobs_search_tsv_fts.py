"""jobs full-text keyword ranking via a functional GIN index

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-12

Replaces ILIKE substring keyword search with real Postgres full-text ranking. Materialized
as a FUNCTIONAL GIN index on JOB_SEARCH_FTS_EXPR (title=A, tech_tags=B, dept+location=C) —
NOT a STORED tsvector column: a stored column of full descriptions bloats storage and its
ADD triggers a table rewrite that exceeds Neon's 512 MB free tier. A functional index adds
no column and needs no rewrite. Queries (`_keyword_search`, hybrid arm) use the identical
expression so the planner uses this index. Body text is intentionally not indexed (semantic
search covers meaning; tech_tags covers skills).
"""
from alembic import op

from app.models import JOB_SEARCH_FTS_EXPR

revision = "d2b3c4e5f6a7"
down_revision = "c1a2b3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX ix_jobs_search_fts ON jobs USING GIN (({JOB_SEARCH_FTS_EXPR}))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_search_fts")
