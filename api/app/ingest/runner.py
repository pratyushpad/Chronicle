import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import case, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ATSSource, Company, IngestRun, Job
from .adapters.base import BoardTooLarge
from .adapters.ashby import AshbyAdapter
from .adapters.greenhouse import GreenhouseAdapter
from .adapters.lever import LeverAdapter
from .dedupe import make_content_hash, make_dedup_key
from .normalize import (
    dedup_title,
    extract_salary,
    extract_tech_tags,
    infer_experience_level,
    infer_remote,
    infer_sponsorship,
    keying_title,
    normalize_department,
    normalize_location,
    normalize_title,
    parse_posted_at,
    strip_html,
)
from .registry import load_active_companies

log = logging.getLogger(__name__)

_ADAPTERS = {
    ATSSource.greenhouse: GreenhouseAdapter(),
    ATSSource.lever: LeverAdapter(),
    ATSSource.ashby: AshbyAdapter(),
}
# Low concurrency so at most this many spooled board downloads are in flight at once.
# Board *contents* are no longer held in memory at all (adapters stream job-by-job), so
# this now bounds only the spool overhead — keeps the ingest within Render's 512MB free
# tier (10-wide OOM'd the instance).
_CONCURRENCY = 3

# Postings run to novella length (Anduril's board averages ~22 KB of description HTML
# per job). Past this the tail is boilerplate — legal notices, benefits, EEO text — that
# adds nothing to search or embedding quality but costs Neon storage on every row.
_MAX_DESC_CHARS = 20_000


def _describe_error(exc: BaseException) -> str:
    """"{type}: {message} @ {file}:{line}" — the crash site, not just the symptom.

    Failure records used to store bare str(exc), which for a data-dependent, not-
    locally-reproducible board says nothing: four Lever boards failed with
    "'NoneType' object is not subscriptable" and there was no way to tell which field
    access raised it. We report the LAST frame inside our own code because the true
    top of the stack is usually a third-party frame (httpx, json) that names a library
    line rather than the assumption of ours that turned out to be wrong.

    Degrades gracefully: no traceback (or no frames) yields plain "{type}: {message}".
    The message is capped at 500 chars (matching _close_crashed_run's discipline in
    admin.py) — failures land in IngestRun.failures JSONB on a storage-constrained
    Neon, and some libraries put whole response bodies into exception text.
    """
    msg = str(exc)
    if len(msg) > 500:
        msg = msg[:500] + "…"
    label = f"{type(exc).__name__}: {msg}"
    tb = exc.__traceback__
    if tb is None:
        return label
    frames = traceback.extract_tb(tb)
    if not frames:
        return label
    ours = [f for f in frames if "app/" in f.filename]
    frame = ours[-1] if ours else frames[-1]
    return f"{label} @ {frame.filename}:{frame.lineno}"


async def _ingest_company(
    company: Company,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    run_start: datetime,
    session: Session,
    deadline: datetime | None = None,
) -> dict:
    adapter = _ADAPTERS[company.ats]
    result = {"company_id": company.id, "jobs_seen": 0, "jobs_new": 0, "error": None, "skipped": False}

    async with sem:
        # Runtime-budget checkpoint (C3): once the run is over budget, stop fetching new
        # boards. Skipped companies keep their old last_ingested_at, so the staleness
        # ordering picks them first on the next scheduled run — the corpus refreshes in
        # chunks across invocations without ever leaving the DB half-written.
        # This MUST be checked after acquiring the semaphore: gather() starts every task
        # at t=0, so a pre-semaphore check always passes and the budget never engages.
        if deadline is not None and datetime.now(tz=timezone.utc) >= deadline:
            result["skipped"] = True
            return result

        _CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Consume the board as a stream: adapter.fetch is an async generator, so at no
        # point does a whole board (2,100 jobs × ~22 KB of description HTML) exist in
        # memory — peak is one RawJob plus the spooled download.
        #
        # Session-safety note (single Session shared by all concurrent tasks): the
        # rollbacks below can only ever discard THIS company's uncommitted upserts.
        # iter_board_json finishes the network download before its first yield, and the
        # per-job body below contains no awaits — so from the first upsert through the
        # commit this task never yields to the event loop, and no sibling task can be
        # holding uncommitted work when a rollback fires.
        for attempt in range(2):
            try:
                # Reset before each attempt: a retry after a partial consume must not
                # double-count the jobs the failed attempt already streamed.
                result["jobs_seen"] = 0
                result["jobs_new"] = 0
                now = datetime.now(tz=timezone.utc)

                async for raw in adapter.fetch(company.slug, client):
                    posted = parse_posted_at(raw.posted_at)
                    if posted is not None and posted < _CUTOFF:
                        continue  # skip stale pre-2026 postings

                    result["jobs_seen"] += 1
                    t_norm = normalize_title(raw.title)
                    l_norm = normalize_location(raw.location)
                    # Key off keying_title (preserves the distinguishing team qualifier), NOT t_norm.
                    dedup = make_dedup_key(company.id, dedup_title(keying_title(raw.title), l_norm))
                    desc_text = strip_html(raw.description_html)
                    # Extract from the FULL text before truncating: salary bands and
                    # sponsorship language usually sit at the very bottom of a long
                    # posting, past _MAX_DESC_CHARS. Truncating first would silently
                    # drop the comp data that makes those rows worth having.
                    sal_min, sal_max = extract_salary(desc_text)
                    tags = extract_tech_tags(desc_text)
                    sponsor = infer_sponsorship(desc_text)
                    dept = normalize_department(raw.department)
                    exp_level = infer_experience_level(raw.title)
                    # Cap what we store AND what we hash, in that order: the hash must
                    # cover exactly the text we persist. An unchanged long posting then
                    # hashes identically every run, so it never re-embeds; and an edit
                    # past the cap — invisible in the stored text — can't churn the
                    # embedding either.
                    desc_text = desc_text[:_MAX_DESC_CHARS]
                    chash = make_content_hash(raw.title, desc_text, l_norm, dept, tags)

                    ins = insert(Job).values(
                        company_id=company.id,
                        source=ATSSource(adapter.source),
                        source_job_id=raw.source_job_id,
                        title=raw.title,
                        title_normalized=t_norm,
                        location_raw=raw.location,
                        location_normalized=l_norm,
                        remote=infer_remote(raw),
                        department=dept,
                        department_raw=raw.department,
                        employment_type=raw.employment_type,
                        description_text=desc_text,
                        apply_url=raw.apply_url,
                        posted_at=posted,
                        dedup_key=dedup,
                        experience_level=exp_level,
                        tech_tags=tags,
                        salary_min=sal_min,
                        salary_max=sal_max,
                        sponsorship_flag=sponsor,
                        content_hash=chash,
                        first_seen_at=now,
                        last_seen_at=now,
                        is_active=True,
                    )
                    # On re-ingest, refresh the mutable content fields, and when the content hash
                    # changed (title/description/location/dept/tags), null the embedding so
                    # embed_missing_jobs re-embeds only that row — delta-only, never the whole corpus.
                    content_changed = Job.content_hash.is_distinct_from(ins.excluded.content_hash)
                    stmt = ins.on_conflict_do_update(
                        constraint="jobs_source_source_job_id_key",
                        set_={
                            "last_seen_at": now,
                            "is_active": True,
                            "title": raw.title,
                            "title_normalized": t_norm,
                            "location_raw": raw.location,
                            "location_normalized": l_norm,
                            "department": dept,
                            "department_raw": raw.department,
                            "employment_type": raw.employment_type,
                            "description_text": desc_text,
                            "apply_url": raw.apply_url,
                            "posted_at": posted,
                            "experience_level": exp_level,
                            "tech_tags": tags,
                            "salary_min": sal_min,
                            "salary_max": sal_max,
                            "sponsorship_flag": sponsor,
                            "content_hash": chash,
                            "embedding": case((content_changed, None), else_=Job.embedding),
                        },
                    )
                    # xmax = 0 iff the row was freshly inserted (an upsert-update stamps xmax).
                    # The old inserted_primary_key check was truthy for updates too, so
                    # jobs_new always equaled jobs_seen.
                    was_insert = session.execute(
                        stmt.returning(literal_column("(xmax = 0)"))
                    ).scalar_one()
                    if was_insert:
                        result["jobs_new"] += 1
                break
            except BoardTooLarge as exc:
                # Deterministic — a retry just re-downloads the same oversized payload.
                # (The cap trips during the download, before any job is yielded, so this
                # rollback is belt-and-braces.)
                session.rollback()
                result["error"] = str(exc)
                return result
            except Exception as exc:
                # Discard this company's partial upserts before retrying, so a second
                # attempt re-upserts from a clean transaction instead of stacking on
                # half-written rows.
                session.rollback()
                if attempt == 0:
                    await asyncio.sleep(2)
                else:
                    result["error"] = _describe_error(exc)
                    return result

        # Checkpoint in the same transaction as this board's jobs: if the process dies
        # on a LATER board (the Jul 30–31 OOM loop), this company must not return to
        # the front of the stalest-first queue — re-fetching the same mega-board first
        # on every run is what turned one OOM into four consecutive crashed runs.
        # Stays inside the semaphore so the "no await between first upsert and commit"
        # property above is true by construction.
        session.execute(
            update(Company)
            .where(Company.id == company.id)
            .values(last_ingested_at=datetime.now(tz=timezone.utc))
        )
        session.commit()

    # Embed the rows we just inserted (embedding IS NULL). Best-effort:
    # a missing/broken model must never fail an ingest run. The deadline applies
    # here too — a backlog-heavy run can otherwise spend an unbounded tail inside
    # ONNX inference and OOM the 512 MB instance; rows left NULL are swept when
    # their company is next fetched, so skipping only defers, never loses.
    if deadline is not None and datetime.now(tz=timezone.utc) >= deadline:
        return result
    try:
        from app.ml.embed_jobs import embed_missing_jobs

        embed_missing_jobs(session, company_id=company.id, deadline=deadline)
    except Exception:
        log.exception("embedding failed for company %s (ingest itself succeeded)", company.slug)

    # Cross-source dedup: prefer earliest first_seen_at for same dedup_key
    # (handled via on_conflict: we keep existing first_seen_at untouched on update)

    return result


async def run_ingest(session: Session, budget_seconds: int | None = None) -> IngestRun:
    """Incremental, idempotent ingest of all active boards.

    Idempotent: upsert on (source, source_job_id) means running twice back-to-back
    creates no duplicates and (via content_hash) re-embeds nothing unchanged. Companies
    are processed stalest-first (last_ingested_at ASC), and if budget_seconds is given the
    run stops fetching new boards past that wall-clock budget — the rest refresh on the
    next scheduled run. Per-company commits mean the DB is never left half-written.
    """
    run_start = datetime.now(tz=timezone.utc)
    deadline = run_start + timedelta(seconds=budget_seconds) if budget_seconds else None
    run = IngestRun(started_at=run_start, failures=[])
    session.add(run)
    session.commit()
    session.refresh(run)

    companies = load_active_companies(session, stale_first=True)
    run.companies_total = len(companies)
    session.commit()

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        tasks = [
            _ingest_company(c, client, sem, run_start, session, deadline=deadline)
            for c in companies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    jobs_seen = 0
    jobs_new = 0
    failures = []
    ok = 0
    skipped = 0
    ok_ids: list[int] = []

    for company, result in zip(companies, results):
        if isinstance(result, Exception):
            failures.append({
                "company": company.name,
                "ats": company.ats.value,
                "slug": company.slug,
                # gather(return_exceptions=True) hands back the live exception object,
                # so __traceback__ is intact and names the crash site here too.
                "error": _describe_error(result),
            })
            run.companies_failed += 1
        elif result.get("skipped"):
            skipped += 1  # over budget — left for the next run, last_ingested_at untouched
        elif result.get("error"):
            failures.append({
                "company": company.name,
                "ats": company.ats.value,
                "slug": company.slug,
                "error": result["error"],
            })
            run.companies_failed += 1
        else:
            ok += 1
            ok_ids.append(company.id)
            jobs_seen += result["jobs_seen"]
            jobs_new += result["jobs_new"]
            # last_ingested_at is stamped per company inside _ingest_company —
            # doing it here (end of run) meant a crashed run advanced nothing.

    # Everything from here to the end runs under try/finally: the soft-close and the
    # run-row commit hit the DB and can raise (a dropped Neon connection is the
    # documented failure mode, 3d02be3) — and an aborted tail is exactly when leaving
    # the model resident hurts most, since the process survives and keeps serving.
    try:
        # Soft-close vanished roles — but ONLY for companies we actually fetched this
        # run. A board that timed out or errored must never deactivate its jobs (they'd
        # flip back active next run, churning the corpus and the "closed" counts).
        # Scoping to ok_ids is what makes soft-close safe at 1000+ boards where
        # transient failures are routine.
        jobs_closed = 0
        if ok_ids:
            closed_result = session.execute(
                update(Job)
                .where(
                    Job.company_id.in_(ok_ids),
                    Job.last_seen_at < run_start,
                    Job.is_active == True,
                )
                .values(is_active=False)
            )
            jobs_closed = closed_result.rowcount

        run.companies_ok = ok
        run.jobs_seen = jobs_seen
        run.jobs_new = jobs_new
        run.jobs_closed = jobs_closed
        run.failures = failures
        run.finished_at = datetime.now(tz=timezone.utc)
        session.commit()

        # Rolling stale-posting prune (B3): keep only active + recently-closed roles
        # hot so the corpus stays within Neon's free storage budget. Best-effort — a
        # prune failure must never fail the ingest run.
        try:
            from .prune import prune_stale_jobs

            prune_stale_jobs(session)
        except Exception:
            log.exception("stale-job prune failed (ingest itself succeeded)")

        # Saved-search alerts (in-app notification + email digest) fire off this run's
        # new jobs. Best-effort: an alert failure must never fail the ingest run.
        # Without this call the /admin/ingest path would never alert — schedule.py is
        # not how prod runs.
        try:
            from .alerts import run_alerts

            await run_alerts(session, run_start)
        except Exception:
            session.rollback()
            log.exception("saved-search alerts failed (ingest itself succeeded)")

        # A fresh run changes /meta's inputs; drop its in-process cache so the
        # "Updated …" label and "NEW SINCE LAST RUN" counts reflect this run
        # immediately (C4).
        try:
            from app.routers.jobs import invalidate_meta_cache

            invalidate_meta_cache()
        except Exception:
            log.debug("meta cache invalidation skipped", exc_info=True)
    finally:
        # Hand the model's ~150-250 MB back to the OS. On Render's 512 MB free tier
        # the ONNX session loaded during this run's embed phase would otherwise stay
        # resident in the web process forever, leaving near-zero headroom for ordinary
        # request traffic — the box has OOM'd while completely idle because of it.
        # In a finally so it runs even when the tail aborts (dropped Neon connection):
        # that path leaves the process alive and serving, which is exactly when a
        # leaked resident model hurts most.
        #
        # Off the event loop (to_thread): release does a full gc.collect() over a heap
        # that just held the ORT arena — blocking the loop with it would stall every
        # in-flight request. Embedding is finished by now (embed_missing_jobs is
        # synchronous inside _ingest_company), so nothing in this run reloads it.
        # Cost is that the first semantic search after a run pays a ~2s reload; an
        # idle process that stays alive beats a fast one that gets OOM-killed.
        # Best-effort — releasing memory must never fail the run.
        try:
            from app.ml.embedder import release_embedder

            await asyncio.to_thread(release_embedder)
        except Exception:
            log.exception("embedder release failed (ingest itself succeeded)")

    log.info(
        "Ingest complete: %d/%d companies OK, %d skipped (budget), %d new jobs, %d closed, %d failures",
        ok, len(companies), skipped, jobs_new, jobs_closed, len(failures),
    )
    return run
