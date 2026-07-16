"""Drop users.extension_token_hash — the browser-extension autofill feature was removed
(router, schemas, and web routes deleted); this column was the last trace of it.

Revision ID: f4d5e6a7b8c9
Revises: e3c4d5f6a7b8
"""

import sqlalchemy as sa
from alembic import op

revision = "f4d5e6a7b8c9"
down_revision = "e3c4d5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "extension_token_hash")


def downgrade() -> None:
    op.add_column("users", sa.Column("extension_token_hash", sa.String(), nullable=True))
