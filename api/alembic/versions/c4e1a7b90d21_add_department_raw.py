"""add jobs.department_raw

Revision ID: c4e1a7b90d21
Revises: b3d7e9f2a1c5
Create Date: 2026-06-30

Adds `department_raw` to preserve the original ATS department string; the existing
`department` column is repurposed to hold the normalized controlled-vocab category.
The `backfill_departments` script copies old department → department_raw, then
overwrites department with the normalized value.
"""
from alembic import op
import sqlalchemy as sa

revision = "c4e1a7b90d21"
down_revision = "b3d7e9f2a1c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("department_raw", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "department_raw")
