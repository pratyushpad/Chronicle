"""Keep the jobs table small: clear the heavy columns of closed roles, then hard-delete roles
that have been closed longer than PRUNE_INACTIVE_DAYS (default 14).

Neon's free tier caps storage and bills egress and compute, so a closed role should cost a
few hundred bytes and then nothing. A role that a user has on file is never deleted: every
foreign key that points at jobs.id is discovered from the database catalog at run time (so a
table added by a later migration is protected without touching this file), and a job with a
row in any of them is kept. The one exception is interaction telemetry of kind
`impression`: the feed logs one per card shown, so protecting them would protect nearly
every job. Impressions are deleted with the job; click, save, apply and dismiss protect it.
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

DEFAULT_PRUNE_INACTIVE_DAYS = 14
DEFAULT_BATCH_SIZE = 500
# Legacy name kept for callers and tests that imported it.
STALE_AFTER_DAYS = DEFAULT_PRUNE_INACTIVE_DAYS

# Interaction events that do not protect a job (see the module docstring).
_DISPOSABLE_INTERACTION_EVENTS = ("impression",)


def prune_days() -> int:
    return int(os.environ.get("PRUNE_INACTIVE_DAYS", DEFAULT_PRUNE_INACTIVE_DAYS))


@dataclass
class PruneResult:
    cleared_rows: int = 0      # closed roles whose description/embedding were cleared
    cleared_bytes: int = 0     # estimated bytes those columns held
    deleted_rows: int = 0
    deleted_bytes: int = 0     # estimated bytes of the deleted rows (pg_column_size)
    protected_rows: int = 0    # prunable by age but kept because user data references them
    dry_run: bool = True

    @property
    def freed_bytes(self) -> int:
        return self.cleared_bytes + self.deleted_bytes

    def summary(self) -> str:
        verb = "would delete" if self.dry_run else "deleted"
        clear = "would clear" if self.dry_run else "cleared"
        return (
            f"prune {'DRY RUN' if self.dry_run else 'APPLIED'}: "
            f"{clear} description/embedding on {self.cleared_rows} closed roles "
            f"(~{self.cleared_bytes} bytes), {verb} {self.deleted_rows} roles "
            f"(~{self.deleted_bytes} bytes), kept {self.protected_rows} aged roles because "
            f"user data references them; estimated bytes freed ~{self.freed_bytes}"
        )


def _referencing_fks(session: Session) -> list[tuple[str, str]]:
    """(table, column) of every single-column foreign key that references jobs(id)."""
    rows = session.execute(text("""
        SELECT cl.relname, att.attname
        FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        JOIN pg_class ref ON ref.oid = con.confrelid
        JOIN pg_namespace ns ON ns.oid = ref.relnamespace
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
        WHERE con.contype = 'f' AND ref.relname = 'jobs' AND ns.nspname = current_schema()
          AND array_length(con.conkey, 1) = 1
    """)).all()
    return sorted((r[0], r[1]) for r in rows)


def _protected_clause(fks: list[tuple[str, str]]) -> str:
    """SQL predicate, true when no user data references the job (alias j)."""
    parts = []
    for table, col in fks:
        t, c = f'"{table}"', f'"{col}"'
        extra = ""
        if table == "interactions":
            evs = ", ".join(f"'{e}'" for e in _DISPOSABLE_INTERACTION_EVENTS)
            extra = f" AND x.event::text NOT IN ({evs})"
        parts.append(f"NOT EXISTS (SELECT 1 FROM {t} x WHERE x.{c} = j.id{extra})")
    return " AND ".join(parts) if parts else "TRUE"


def clear_closed_payloads(session: Session, dry_run: bool = False, result: PruneResult | None = None) -> PruneResult:
    """Null description_text and embedding on closed roles that still carry them (rows
    closed before the ingest started doing this at close time). The row stays."""
    result = result or PruneResult(dry_run=dry_run)
    row = session.execute(text("""
        SELECT count(*), COALESCE(sum(COALESCE(pg_column_size(description_text), 0)
                                    + COALESCE(pg_column_size(embedding), 0)), 0)
        FROM jobs
        WHERE is_active = false AND (description_text IS NOT NULL OR embedding IS NOT NULL)
    """)).one()
    result.cleared_rows += int(row[0])
    result.cleared_bytes += int(row[1])
    if not dry_run and row[0]:
        session.execute(text(
            "UPDATE jobs SET description_text = NULL, embedding = NULL "
            "WHERE is_active = false AND (description_text IS NOT NULL OR embedding IS NOT NULL)"
        ))
        session.commit()
    return result


def prune_closed_jobs(
    session: Session,
    days: int | None = None,
    dry_run: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> PruneResult:
    """Clear heavy columns on closed roles, then hard-delete roles closed more than `days`
    ago and not referenced by user data, in batches of `batch_size` (one commit each).

    The age clock is closed_at, falling back to last_seen_at for rows closed before that
    column existed. dry_run (the default) only counts and estimates; nothing is written.
    Idempotent."""
    days = prune_days() if days is None else days
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    result = PruneResult(dry_run=dry_run)
    clear_closed_payloads(session, dry_run=dry_run, result=result)

    fks = _referencing_fks(session)
    free_of_user_data = _protected_clause(fks)
    aged = "j.is_active = false AND COALESCE(j.closed_at, j.last_seen_at) < :cutoff"

    total_aged = session.execute(
        text(f"SELECT count(*) FROM jobs j WHERE {aged}"), {"cutoff": cutoff}
    ).scalar_one()
    prunable_ids_sql = f"SELECT j.id FROM jobs j WHERE {aged} AND {free_of_user_data}"

    if dry_run:
        n, size = session.execute(
            text(f"SELECT count(*), COALESCE(sum(pg_column_size(j.*)), 0) FROM jobs j "
                 f"WHERE j.id IN ({prunable_ids_sql})"),
            {"cutoff": cutoff},
        ).one()
        result.deleted_rows, result.deleted_bytes = int(n), int(size)
        result.protected_rows = int(total_aged) - int(n)
        return result

    while True:
        ids = [r[0] for r in session.execute(
            text(f"{prunable_ids_sql} ORDER BY j.id LIMIT :n"), {"cutoff": cutoff, "n": batch_size}
        )]
        if not ids:
            break
        size = session.execute(
            text("SELECT COALESCE(sum(pg_column_size(j.*)), 0) FROM jobs j WHERE j.id = ANY(:ids)"),
            {"ids": ids},
        ).scalar_one()
        # Disposable telemetry goes with the job (it cannot be left dangling on the FK).
        if any(t == "interactions" for t, _ in fks):
            session.execute(
                text("DELETE FROM interactions WHERE job_id = ANY(:ids)"), {"ids": ids}
            )
        deleted = session.execute(
            text("DELETE FROM jobs WHERE id = ANY(:ids)"), {"ids": ids}
        ).rowcount or 0
        session.commit()
        result.deleted_rows += deleted
        result.deleted_bytes += int(size)
        if len(ids) < batch_size:
            break
    result.protected_rows = int(total_aged) - result.deleted_rows
    if result.deleted_rows or result.cleared_rows:
        log.info(result.summary())
    return result


def prune_stale_jobs(session: Session, older_than_days: int | None = None) -> int:
    """Apply the prune (clear payloads, then delete). Returns rows deleted. Called at the
    end of every ingest run; best-effort there."""
    return prune_closed_jobs(session, days=older_than_days, dry_run=False).deleted_rows
