"""Embed jobs that don't have vectors yet.

Only rows with embedding IS NULL are ever touched: the ingest upsert
(runner.py on_conflict_do_update) never changes title/description on
conflict, so an existing embedding never goes stale. If that upsert ever
starts updating description_text, it must also NULL the embedding.
"""
import logging

from sqlalchemy import select, update
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
            select(
                Job.id,
                Job.title,
                Job.department,
                Job.location_normalized,
                Job.location_raw,
                Job.tech_tags,
                Job.description_text,
                Company.name.label("company_name"),
            )
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
        job_ids = [row.id for row in rows]
        texts = [
            build_embedding_text(
                title=row.title,
                company_name=row.company_name,
                department=row.department,
                location=row.location_normalized or row.location_raw,
                tech_tags=row.tech_tags,
                description_text=row.description_text,
            )
            for row in rows
        ]
        # End the read transaction BEFORE encoding. ONNX inference on a full page runs
        # for minutes, and a connection left idle mid-transaction gets closed by Neon —
        # which then failed the commit below and took the whole ingest run down with it.
        # Releasing here means the write re-checks out a live (pre-pinged) connection.
        session.commit()
        vectors = embedder.encode(texts, batch_size=batch_size)
        session.execute(
            update(Job),
            [{"id": jid, "embedding": vector} for jid, vector in zip(job_ids, vectors)],
        )
        session.commit()
        total += len(rows)
        if limit is not None and total >= limit:
            break
    if total:
        log.info("embedded %d jobs%s", total, f" (company_id={company_id})" if company_id else "")
    return total
