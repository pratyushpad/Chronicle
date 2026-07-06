"""Latency benchmark for semantic/hybrid search.

    python -m scripts.bench_search [--n 50] [--mode hybrid] [--synthesize 50000]

--synthesize inserts inactive synthetic jobs with random unit vectors to
grow the corpus to N rows for a worst-case index test (they're is_active
false so the app never shows them; delete with --cleanup).
"""
import argparse
import logging
import random
import statistics
import time

from dotenv import load_dotenv

load_dotenv()

import numpy as np  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402

from app.db import get_session  # noqa: E402
from app.models import Job  # noqa: E402
from app.ml.embedder import get_embedder  # noqa: E402

log = logging.getLogger(__name__)

QUERIES = [
    "machine learning engineer recommender systems",
    "backend engineer distributed systems golang",
    "frontend react typescript design systems",
    "data engineer spark airflow pipelines",
    "security engineer threat detection",
    "product manager growth experimentation",
    "site reliability engineer kubernetes",
    "new grad software engineer",
    "research scientist large language models",
    "ios mobile engineer swift",
]

_SYNTH_MARKER = "__bench_synthetic__"


def synthesize(session, target_total: int) -> None:
    current = session.execute(select(func.count()).select_from(Job)).scalar_one()
    needed = target_total - current
    if needed <= 0:
        log.info("corpus already has %d rows (>= %d)", current, target_total)
        return
    template = session.execute(select(Job).limit(1)).scalar_one()
    rng = np.random.default_rng(42)
    log.info("inserting %d synthetic rows...", needed)
    batch: list[Job] = []
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for i in range(needed):
        vec = rng.standard_normal(384).astype(np.float32)
        vec /= np.linalg.norm(vec)
        batch.append(
            Job(
                company_id=template.company_id,
                source=template.source,
                source_job_id=f"{_SYNTH_MARKER}{i}",
                title=f"Synthetic role {i}",
                title_normalized=f"synthetic role {i}",
                apply_url="https://example.invalid",
                dedup_key=f"bench{i:035d}",
                embedding=vec.tolist(),
                first_seen_at=now,
                last_seen_at=now,
                is_active=False,
            )
        )
        if len(batch) >= 1000:
            session.add_all(batch)
            session.commit()
            batch = []
    if batch:
        session.add_all(batch)
        session.commit()


def cleanup(session) -> None:
    n = session.execute(
        delete(Job).where(Job.source_job_id.like(f"{_SYNTH_MARKER}%"))
    ).rowcount
    session.commit()
    log.info("deleted %d synthetic rows", n)


def bench(session, mode: str, n: int) -> None:
    embedder = get_embedder()
    embedder.encode(["warmup"])
    latencies = []
    for i in range(n):
        q = random.choice(QUERIES)
        t0 = time.perf_counter()
        qvec = embedder.encode([q])[0]
        stmt = (
            select(Job.id, Job.dedup_key)
            .where(Job.embedding.isnot(None))
            .order_by(Job.embedding.cosine_distance(qvec))
            .limit(200)
        )
        session.execute(stmt).all()
        if mode == "hybrid":
            session.execute(
                select(Job.id, Job.dedup_key)
                .where(Job.is_active == True, Job.title.ilike(f"%{q.split()[0]}%"))
                .order_by(Job.posted_at.desc().nullslast())
                .limit(200)
            ).all()
        latencies.append((time.perf_counter() - t0) * 1000)
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    total = session.execute(select(func.count()).select_from(Job)).scalar_one()
    print(f"mode={mode} corpus={total} n={n}: p50={p50:.0f}ms p95={p95:.0f}ms max={latencies[-1]:.0f}ms")
    assert p95 < 400, f"p95 {p95:.0f}ms exceeds 400ms budget"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--mode", choices=["semantic", "hybrid"], default="hybrid")
    parser.add_argument("--synthesize", type=int, default=None, metavar="TOTAL")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    random.seed(42)
    session = get_session()
    try:
        if args.cleanup:
            cleanup(session)
            return
        if args.synthesize:
            synthesize(session, args.synthesize)
        bench(session, args.mode, args.n)
    finally:
        session.close()


if __name__ == "__main__":
    main()
