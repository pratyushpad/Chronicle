"""add jobs.pay_* (pay as posted: amount, currency, period, source)

Revision ID: a1f3c5e7b9d2
Revises: f4d5e6a7b8c9
Create Date: 2026-09-26

Pay is stored exactly as the posting states it ("$45–55 per hour" → 45, 55, USD, hour);
`salary_min/max` become annualized USD sort keys derived from it. All columns are
nullable with no default, so on Postgres this is a catalog-only change (no table
rewrite). `app/ingest/backfill_pr1.py` fills existing rows from their stored text; ingest
fills the rest (and adds structured ATS pay) as boards are re-fetched.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1f3c5e7b9d2"
down_revision = "f4d5e6a7b8c9"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("pay_min", sa.Numeric(12, 2)),
    ("pay_max", sa.Numeric(12, 2)),
    ("pay_currency", sa.String(3)),
    ("pay_period", sa.String(8)),
    ("pay_source", sa.String(8)),
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
