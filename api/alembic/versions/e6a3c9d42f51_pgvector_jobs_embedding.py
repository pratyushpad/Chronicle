"""pgvector extension + jobs.embedding + HNSW index

Revision ID: e6a3c9d42f51
Revises: d5f2b8c31e40
Create Date: 2026-07-05

Enables the pgvector extension and adds a nullable 384-dim embedding column
to jobs (all-MiniLM-L6-v2 vectors, L2-normalized) with an HNSW cosine index.
Nullable + additive — safe on prod; rows are embedded by the ingest worker /
backfill script.

Downgrade drops the index and column but leaves the extension installed
(dropping it would break any other vector column added later).
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "e6a3c9d42f51"
down_revision = "d5f2b8c31e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("jobs", sa.Column("embedding", Vector(384), nullable=True))
    op.execute(
        "CREATE INDEX ix_jobs_embedding_hnsw ON jobs "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_embedding_hnsw")
    op.drop_column("jobs", "embedding")
