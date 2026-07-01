"""Verified bulk company add — a gate before growing the registry.

Don't insert unverified slugs (a bad slug silently pollutes counts). For each
candidate (name, ats, slug, industry) this hits the ATS endpoint and classifies:
  - >=1 job            -> register active=True
  - dead / error / 0   -> register active=False (quarantined) + log the reason
  - already in registry -> skip (unique ats+slug)

Persists to BOTH targets so additions survive a re-seed:
  - the Company table (upsert, same pattern as registry.seed_companies_if_empty)
  - companies.seed.json (append, de-duped on ats+slug)

Bounded concurrency, per-request timeout, per-company try/except so one bad slug
never aborts the run. Additive — reuses the existing adapter contract.

Run from the api/ directory:
    python -m app.ingest.verify_and_add_companies                       # dry-run sample batch (no writes)
    python -m app.ingest.verify_and_add_companies --commit              # persist the sample batch
    python -m app.ingest.verify_and_add_companies candidates/batch1.json          # dry-run a JSON batch
    python -m app.ingest.verify_and_add_companies candidates/batch1.json --commit # persist a JSON batch

The JSON file is a list of {name, ats, slug, industry?} objects. For a real bulk add,
either pass a JSON path or import verify_and_add(candidates) with your own list.
"""
import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402 — after dotenv
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.db import get_session  # noqa: E402 — db reads DATABASE_URL at import
from app.models import ATSSource, Company  # noqa: E402
from .registry import _SEED_FILE  # noqa: E402
from .runner import _ADAPTERS  # noqa: E402

log = logging.getLogger(__name__)

_CONCURRENCY = 8
_TIMEOUT = 10


@dataclass(frozen=True)
class Candidate:
    name: str
    ats: str
    slug: str
    industry: str | None = None


@dataclass
class VerifyResult:
    candidate: Candidate
    status: str  # "active" | "quarantined" | "skipped"
    job_count: int = 0
    reason: str | None = None


async def _verify_one(
    cand: Candidate,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    existing: set[tuple[str, str]],
) -> VerifyResult:
    if (cand.ats, cand.slug) in existing:
        return VerifyResult(cand, "skipped", reason="already in registry")
    try:
        ats = ATSSource(cand.ats)
    except ValueError:
        return VerifyResult(cand, "quarantined", reason=f"unknown ats '{cand.ats}'")
    adapter = _ADAPTERS.get(ats)
    if adapter is None:
        return VerifyResult(cand, "quarantined", reason=f"no adapter for '{cand.ats}'")
    async with sem:
        try:
            jobs = await adapter.fetch(cand.slug, client)
        except Exception as exc:  # never let one bad slug abort the run
            return VerifyResult(cand, "quarantined", reason=f"{type(exc).__name__}: {exc}")
    n = len(jobs)
    if n >= 1:
        return VerifyResult(cand, "active", job_count=n)
    return VerifyResult(cand, "quarantined", reason="0 jobs returned")


async def _verify_all(candidates: list[Candidate], existing: set[tuple[str, str]]) -> list[VerifyResult]:
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return list(await asyncio.gather(*(_verify_one(c, client, sem, existing) for c in candidates)))


def _persist(results: list[VerifyResult], session) -> int:
    """Upsert verified candidates into the Company table AND append them to
    companies.seed.json (de-duped). Skips 'skipped' rows and any with an
    unstorable (unknown) ats. Returns the number of new seed.json entries."""
    seed = json.loads(_SEED_FILE.read_text())
    seed_keys = {(e["ats"], e["slug"]) for e in seed}
    added = 0
    for r in results:
        if r.status == "skipped":
            continue
        cand = r.candidate
        try:
            ats = ATSSource(cand.ats)
        except ValueError:
            continue  # cannot store an unknown ats enum; stays out of the registry
        active = r.status == "active"
        session.execute(
            insert(Company)
            .values(
                name=cand.name, ats=ats, slug=cand.slug,
                careers_url=None, industry=cand.industry, active=active,
            )
            .on_conflict_do_update(
                constraint="companies_ats_slug_key",
                set_={"name": cand.name, "industry": cand.industry, "active": active},
            )
        )
        if (cand.ats, cand.slug) not in seed_keys:
            seed.append({
                "name": cand.name, "ats": cand.ats, "slug": cand.slug,
                "careers_url": None, "industry": cand.industry, "active": active,
            })
            seed_keys.add((cand.ats, cand.slug))
            added += 1
    session.commit()
    if added:
        _SEED_FILE.write_text(json.dumps(seed, indent=2) + "\n")
    return added


def _summarize(results: list[VerifyResult], added: int | None) -> None:
    buckets = {"active": [], "quarantined": [], "skipped": []}
    for r in results:
        buckets[r.status].append(r)
    log.info("── verify_and_add summary ──────────────────────────────")
    log.info("  active (live w/ jobs): %d", len(buckets["active"]))
    for r in buckets["active"]:
        log.info("    ✓ %-24s %s/%s  (%d jobs)", r.candidate.name, r.candidate.ats, r.candidate.slug, r.job_count)
    log.info("  quarantined (active=false): %d", len(buckets["quarantined"]))
    for r in buckets["quarantined"]:
        log.info("    ✗ %-24s %s/%s  — %s", r.candidate.name, r.candidate.ats, r.candidate.slug, r.reason)
    log.info("  skipped (already in registry): %d", len(buckets["skipped"]))
    for r in buckets["skipped"]:
        log.info("    · %-24s %s/%s", r.candidate.name, r.candidate.ats, r.candidate.slug)
    if added is None:
        log.info("  (dry run — no writes)")
    else:
        log.info("  persisted: %d new seed.json entries + Company upserts", added)


def verify_and_add(candidates: list[Candidate], persist: bool = True) -> list[VerifyResult]:
    """Verify each candidate against its ATS and (optionally) register it. Returns
    the per-candidate results; also prints a summary."""
    session = get_session()
    try:
        existing = {
            (row.ats.value, row.slug)
            for row in session.execute(select(Company.ats, Company.slug)).all()
        }
        results = asyncio.run(_verify_all(candidates, existing))
        added = _persist(results, session) if persist else None
    finally:
        session.close()
    _summarize(results, added)
    return results


# Small sample batch: known-good slugs across all three ATSes + one deliberately-bad
# slug to prove quarantine. Whether a good slug lands "active" vs "skipped" depends on
# current registry state (idempotent).
_SAMPLE = [
    Candidate("Affirm", "greenhouse", "affirm", "FinTech"),  # live w/ jobs → active
    Candidate("Stripe", "greenhouse", "stripe", "FinTech"),  # already seeded → skipped
    Candidate("Definitely Not A Real Company", "greenhouse", "zzz-nonexistent-slug-xyz", "Test"),  # 404 → quarantined
    Candidate("Bogus ATS Co", "workday", "whoever", "Test"),  # unknown ats → quarantined
]


def load_candidates(path: str) -> list[Candidate]:
    """Load a JSON batch of {name, ats, slug, industry?} objects into Candidates."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of candidate objects")
    out: list[Candidate] = []
    for i, e in enumerate(data):
        try:
            out.append(Candidate(name=e["name"], ats=e["ats"], slug=e["slug"], industry=e.get("industry")))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"{path}[{i}]: missing/invalid field ({exc}) in {e!r}") from exc
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates_path", nargs="?", help="JSON batch file (default: built-in sample)")
    parser.add_argument("--commit", action="store_true", help="persist results (default: dry run)")
    args = parser.parse_args()
    candidates = load_candidates(args.candidates_path) if args.candidates_path else _SAMPLE
    log.info("Loaded %d candidate(s)%s", len(candidates), f" from {args.candidates_path}" if args.candidates_path else " (built-in sample)")
    verify_and_add(candidates, persist=args.commit)


if __name__ == "__main__":
    main()
