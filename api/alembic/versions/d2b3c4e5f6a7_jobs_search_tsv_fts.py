"""jobs.search_tsv weighted full-text vector + GIN index

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-11

Replaces ILIKE substring keyword search with real Postgres full-text ranking. A GENERATED
STORED tsvector (title=A, dept+location=C, description=D) with a GIN index lets
`_keyword_search` rank by ts_rank_cd(websearch_to_tsquery(...)) and feeds honest lexical
ranks into the hybrid RRF fusion. The exact SQL mirrors app.models.JOB_SEARCH_TSV_SQL.
"""
from alembic import op

from app.models import JOB_SEARCH_TSV_SQL

revision = "d2b3c4e5f6a7"
down_revision = "c1a2b3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE jobs ADD COLUMN search_tsv tsvector "
        f"GENERATED ALWAYS AS ({JOB_SEARCH_TSV_SQL}) STORED"
    )
    # GIN index for fast @@ matching; CONCURRENTLY would need autocommit — plain build is
    # fine for the one-time manual run against Neon (table locked briefly).
    op.execute("CREATE INDEX ix_jobs_search_tsv ON jobs USING GIN (search_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_search_tsv")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS search_tsv")
