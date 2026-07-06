"""interactions table — raw engagement events for future learned ranking

Revision ID: a8c5e1f64b73
Revises: f7b4d0e53a62
Create Date: 2026-07-05

Append-only log of user x job events (impression/click/save/apply/dismiss)
with the surface they happened on (feed/search/alert). No ML consumes this
yet; it exists so a future learned ranker has training data from day one.
"""
from alembic import op
import sqlalchemy as sa

revision = "a8c5e1f64b73"
down_revision = "f7b4d0e53a62"
branch_labels = None
depends_on = None

_EVENT = sa.Enum("impression", "click", "save", "apply", "dismiss", name="interactionevent")
_SURFACE = sa.Enum("feed", "search", "alert", name="interactionsurface")


def upgrade() -> None:
    op.create_table(
        "interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("event", _EVENT, nullable=False),
        sa.Column("surface", _SURFACE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interactions_user_created", "interactions", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_interactions_user_created", table_name="interactions")
    op.drop_table("interactions")
    _EVENT.drop(op.get_bind(), checkfirst=True)
    _SURFACE.drop(op.get_bind(), checkfirst=True)
