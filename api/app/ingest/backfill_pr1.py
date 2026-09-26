"""One-off backfill for the PR 1 fixes, so existing rows are right immediately instead of
waiting for their board's next re-ingest (which recomputes all of this anyway, from the
full raw posting and with structured ATS pay).

What it changes, per active or inactive row:
  * department — re-derived with the new normalize_department(department_raw, title).
    (ATS hints aren't stored, so ingest can do slightly better later.)
  * pay_* and the annualized salary_min/max — set from the new pay parser run over the
    stored description, ONLY where it finds pay. It never clears anything: stored legacy
    text lost its line breaks, so the parser can miss pay there that it reads correctly
    from the raw posting (e.g. "Base Salary: $140,000 to $250,000" followed by an
    "Equity + Benefits" line). The next ingest re-derives every pay field from the raw
    posting anyway.
  * posted_at on Greenhouse rows → NULL. It held Greenhouse's updated_at (any edit moved
    it); the next ingest fills in the real first_published. Age falls back to
    first_seen_at meanwhile.
It never touches content_hash or embedding, so nothing is re-embedded.

Dry run by default. From api/:
    python -m app.ingest.backfill_pr1            # report only, writes nothing
    python -m app.ingest.backfill_pr1 --apply    # write, committing per batch
Refuses a non-local database unless CHRONICLE_ALLOW_REMOTE_DB=1 (see app/dbguard.py).
"""
import argparse
import collections
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from app.dbguard import assert_local_or_allowed  # noqa: E402

assert_local_or_allowed(os.environ.get("DATABASE_URL"), "backfill_pr1")

from sqlalchemy import func, or_, select, update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import get_session  # noqa: E402 — db reads DATABASE_URL at import
from app.models import ATSSource, Job  # noqa: E402
from .normalize import normalize_department  # noqa: E402
from .pay import annual_usd, parse_pay_text  # noqa: E402

log = logging.getLogger(__name__)

# Rows worth re-parsing for pay: a currency marker in the text, or a legacy salary that
# may need correcting/clearing. Filtered server-side so the other rows' descriptions
# never cross the network. A real or_() (not raw SQL text): it must stay parenthesized
# when ANDed with the keyset predicate, or every batch returns the same rows forever.
_PAY_CANDIDATE = or_(
    Job.description_text.op("~")(r"[$£€₹]|USD|CAD|GBP|EUR|AUD"),
    Job.salary_min.is_not(None),
)
_PAY_FIELDS = ("pay_min", "pay_max", "pay_currency", "pay_period", "pay_source", "salary_min", "salary_max")


def _pay_values(desc: str | None) -> dict | None:
    """New pay columns for a stored description, or None to leave the row as it is."""
    pay = parse_pay_text(desc)
    if pay is None:
        return None
    lo, hi = annual_usd(pay)
    return {"pay_min": pay.min, "pay_max": pay.max, "pay_currency": pay.currency,
            "pay_period": pay.period, "pay_source": pay.source,
            "salary_min": lo, "salary_max": hi}


def _batches(session, stmt, batch: int):
    """Keyset pagination by id. Refuses to spin: every batch must move past the last."""
    last_id = 0
    while True:
        rows = session.execute(stmt.where(Job.id > last_id).order_by(Job.id).limit(batch)).all()
        if not rows:
            return
        if rows[-1].id <= last_id:
            raise RuntimeError(f"keyset pagination stalled at id {last_id}")
        yield rows
        last_id = rows[-1].id


def run(apply: bool, batch: int, session: Session | None = None) -> dict:
    own_session = session is None
    session = session or get_session()
    stats: dict = {"scanned": 0, "dept_changed": 0, "dept_moves": collections.Counter(),
                   "pay_scanned": 0, "pay_set": 0, "gh_posted_at_nulled": 0}
    try:
        # 1) departments — small columns only
        stmt = select(Job.id, Job.department, Job.department_raw, Job.title)
        for rows in _batches(session, stmt, batch):
            updates = []
            for r in rows:
                stats["scanned"] += 1
                new = normalize_department(r.department_raw, r.title)
                if new != r.department:
                    stats["dept_changed"] += 1
                    stats["dept_moves"][(r.department, new)] += 1
                    updates.append({"id": r.id, "department": new})
            if apply and updates:
                session.execute(update(Job), updates)
                session.commit()

        # 2) pay — only rows that can carry it
        stmt = select(Job.id, Job.description_text, *(getattr(Job, f) for f in _PAY_FIELDS)).where(_PAY_CANDIDATE)
        for rows in _batches(session, stmt, batch):
            updates = []
            for r in rows:
                stats["pay_scanned"] += 1
                vals = _pay_values(r.description_text)
                if vals is None:
                    continue
                current = {f: getattr(r, f) for f in _PAY_FIELDS}
                if all((current[f] == vals[f]) or (current[f] is None and vals[f] is None) for f in _PAY_FIELDS):
                    continue
                stats["pay_set"] += 1
                updates.append({"id": r.id, **vals})
            if apply and updates:
                session.execute(update(Job), updates)
                session.commit()

        # 3) Greenhouse posted_at held updated_at — clear it (one statement)
        gh = Job.source == ATSSource.greenhouse
        stats["gh_posted_at_nulled"] = session.execute(
            select(func.count()).select_from(Job).where(gh, Job.posted_at.is_not(None))
        ).scalar_one()
        if apply and stats["gh_posted_at_nulled"]:
            session.execute(update(Job).where(gh, Job.posted_at.is_not(None)).values(posted_at=None))
            session.commit()
    finally:
        if own_session:
            session.close()
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--batch", type=int, default=1000)
    args = ap.parse_args()
    stats = run(args.apply, args.batch)
    mode = "APPLIED" if args.apply else "DRY RUN (nothing written)"
    log.info("backfill_pr1 — %s", mode)
    log.info("  rows scanned: %d; department changed: %d", stats["scanned"], stats["dept_changed"])
    for (old, new), n in stats["dept_moves"].most_common(25):
        log.info("    %-22s -> %-20s %6d", old, new, n)
    log.info("  pay: %d candidate rows re-parsed; %d set/corrected (nothing is ever cleared)",
             stats["pay_scanned"], stats["pay_set"])
    log.info("  greenhouse posted_at cleared (held updated_at): %d", stats["gh_posted_at_nulled"])


if __name__ == "__main__":
    main()
