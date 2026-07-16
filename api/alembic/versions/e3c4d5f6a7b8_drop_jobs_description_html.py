"""Drop jobs.description_html — raw ATS HTML was stored but never read by any
endpoint (the app serves description_text). At 40k+ jobs it was ~126 MB of the
512 MB Neon free-tier cap and pushed the project into DiskFull. Descriptions
remain re-fetchable from the source boards on every ingest.

Revision ID: e3c4d5f6a7b8
Revises: d2b3c4e5f6a7
"""

import sqlalchemy as sa
from alembic import op

revision = "e3c4d5f6a7b8"
down_revision = "d2b3c4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("jobs", "description_html")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("description_html", sa.Text(), nullable=True))
