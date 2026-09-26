"""ingest_runs: at most one open run (atomic run lock)

Revision ID: c8d3f5a7b9e2
Revises: b7c2e4f6a8d1
Create Date: 2026-09-26

A partial unique index lets at most one ingest_runs row have finished_at NULL, so two
triggers that race (GitHub + a backup cron, or two Actions runs) can't both start: the
second INSERT fails and that run exits. Runs left open by a crash are closed first
(anything open for more than 2 hours, the app's existing stale-lock window), so the index
can be built. Catalog-light: ingest_runs is a few hundred rows.
"""
from alembic import op

revision = "c8d3f5a7b9e2"
down_revision = "b7c2e4f6a8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        """
        UPDATE ingest_runs
           SET finished_at = started_at,
               failures = coalesce(failures, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
                   'company', NULL, 'ats', NULL, 'slug', NULL,
                   'error', 'closed by migration c8d3f5a7b9e2: run never finished (crashed)'))
         WHERE finished_at IS NULL AND started_at < now() - interval '2 hours'
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_ingest_runs_one_open ON ingest_runs ((true)) WHERE finished_at IS NULL"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("DROP INDEX IF EXISTS ux_ingest_runs_one_open")
