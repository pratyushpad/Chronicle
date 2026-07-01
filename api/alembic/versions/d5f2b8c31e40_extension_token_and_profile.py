"""add extension token + profile phone/work_authorization

Revision ID: d5f2b8c31e40
Revises: c4e1a7b90d21
Create Date: 2026-07-01

Adds `users.extension_token_hash` (sha256 of the browser-extension bearer token)
and `profiles.phone` / `profiles.work_authorization` (autofill fields the
extension reads). All nullable — additive, safe on prod.
"""
from alembic import op
import sqlalchemy as sa

revision = "d5f2b8c31e40"
down_revision = "c4e1a7b90d21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("extension_token_hash", sa.String(), nullable=True))
    op.add_column("profiles", sa.Column("phone", sa.String(), nullable=True))
    op.add_column("profiles", sa.Column("work_authorization", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "work_authorization")
    op.drop_column("profiles", "phone")
    op.drop_column("users", "extension_token_hash")
