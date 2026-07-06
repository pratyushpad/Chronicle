"""Embed jobs that don't have vectors yet.

Only rows with embedding IS NULL are ever touched: the ingest upsert
(runner.py on_conflict_do_update) never changes title/description on
conflict, so an existing embedding never goes stale. If that upsert ever
starts updating description_text, it must also NULL the embedding.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Job
from app.ml.embedder import DEFAULT_BATCH_SIZE, get_embedder
from app.ml.text import build_embedding_text

log = logging.getLogger(__name__)

_PAGE_SIZE = 500


def embed_missing_jobs(
    session: Session,
    company_id: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
) -> int:
    """Embed jobs WHERE embedding IS NULL; returns number embedded.

    Commits after each page so the work is resumable and never holds a
    long transaction against prod.
    """
    embedder = get_embedder()
    total = 0
    while True:
        stmt = (
            select(Job, Company.name.label("company_name"))
            .join(Company, Job.company_id == Company.id)
            .where(Job.embedding.is_(None))
            .order_by(Job.id)
            .limit(_PAGE_SIZE)
        )
        if company_id is not None:
            stmt = stmt.where(Job.company_id == company_id)
        rows = session.execute(stmt).all()
        if not rows:
            break
        texts = [
            build_embedding_text(
                title=row.Job.title,
                company_name=row.company_name,
                department=row.Job.department,
                location=row.Job.location_normalized or row.Job.location_raw,
                tech_tags=row.Job.tech_tags,
                description_text=row.Job.description_text,
            )
            for row in rows
        ]
        vectors = embedder.encode(texts, batch_size=batch_size)
        for row, vector in zip(rows, vectors):
            row.Job.embedding = vector
        session.commit()
        total += len(rows)
        if limit is not None and total >= limit:
            break
    if total:
        log.info("embedded %d jobs%s", total, f" (company_id={company_id})" if company_id else "")
    return total
