"""profiles.embedding for For-You v2 semantic matching

Revision ID: f7b4d0e53a62
Revises: e6a3c9d42f51
Create Date: 2026-07-05

Nullable 384-dim profile vector: blend of the profile-text embedding and a
weighted centroid of engaged-job embeddings (applied 2x, saved 1x). Computed
on profile save and nightly by the worker. No index — profiles are looked up
by user_id, never searched by vector.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "f7b4d0e53a62"
down_revision = "e6a3c9d42f51"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("embedding", Vector(384), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "embedding")
