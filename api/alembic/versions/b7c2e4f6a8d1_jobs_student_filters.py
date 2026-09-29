"""add jobs student-filter columns (term, degree, graduation window, citizenship,
U.S.-person, clearance, workplace, country)

Revision ID: b7c2e4f6a8d1
Revises: a1f3c5e7b9d2
Create Date: 2026-09-26

Extracted at ingest from each posting's full text (app/ingest/eligibility.py). All
nullable with no default: a catalog-only change on Postgres (no table rewrite), and NULL
means "the posting doesn't say". Ingest fills rows as boards are re-fetched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7c2e4f6a8d1"
down_revision = "a1f3c5e7b9d2"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("term_season", sa.String(8)),
    ("term_year", sa.SmallInteger()),
    ("degree_levels", postgresql.ARRAY(sa.String(8))),
    ("grad_year_min", sa.SmallInteger()),
    ("grad_year_max", sa.SmallInteger()),
    ("us_citizen_required", sa.Boolean()),
    ("us_person_required", sa.Boolean()),
    ("clearance_required", sa.Boolean()),
    ("workplace_type", sa.String(8)),
    ("country", sa.String(2)),
)


def upgrade() -> None:
    # Fail fast rather than queue behind a running ingest's locks (and block reads).
    op.execute("SET LOCAL lock_timeout = '5s'")
    for name, type_ in _COLUMNS:
        op.add_column("jobs", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for name, _ in reversed(_COLUMNS):
        op.drop_column("jobs", name)
