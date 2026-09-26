"""Replay recorded board payloads through the REAL ingest runner — no network.

Run from the repo's api/ directory (so `app` imports resolve to the checked-out branch):
  DATABASE_URL=postgresql+psycopg2://chronicle:chronicle@127.0.0.1:5434/<db> \
    .venv/bin/python <this> <replay_dir> [--no-embed] [--budget N] [--only ats:slug,...] [--seed]

Refuses any non-local DATABASE_URL. Serves recorded bytes keyed by (ats, slug) regardless of
query params, so adapter URL changes on a branch still replay. Unknown hosts get a 599 so a
new adapter can't silently hit the network through this harness.
"""
import argparse
import asyncio
import gzip
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

HOSTS = {
    "boards-api.greenhouse.io": "greenhouse",
    "api.lever.co": "lever",
    "api.ashbyhq.com": "ashby",
}


def _assert_local_db() -> str:
    url = os.environ.get("DATABASE_URL", "")
    host = urlparse(url.replace("+psycopg2", "").replace("+psycopg", "")).hostname
    if host not in {"127.0.0.1", "localhost"}:
        sys.exit(f"refusing: DATABASE_URL host {host!r} is not local")
    return url


def _slug(url) -> str | None:
    parts = url.path.strip("/").split("/")
    # greenhouse /v1/boards/{slug}/jobs, lever /v0/postings/{slug}, ashby /posting-api/job-board/{slug}
    return parts[2] if len(parts) >= 3 else None


def build_transport(replay_dir: Path):
    import httpx

    def handler(request: "httpx.Request") -> "httpx.Response":
        ats = HOSTS.get(request.url.host)
        if ats is None:
            return httpx.Response(599, text=f"unrecorded host {request.url.host}")
        f = replay_dir / ats / f"{_slug(request.url)}.json.gz"
        if not f.exists():
            return httpx.Response(404, text="not recorded")
        return httpx.Response(200, content=gzip.decompress(f.read_bytes()),
                              headers={"content-type": "application/json"})

    return httpx.MockTransport(handler)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("replay_dir")
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument("--only", default=None, help="comma list of ats:slug")
    ap.add_argument("--seed", action="store_true", help="upsert companies.seed.json first")
    args = ap.parse_args()
    _assert_local_db()
    replay_dir = Path(args.replay_dir)

    import httpx
    transport = build_transport(replay_dir)
    _Real = httpx.AsyncClient

    class _ReplayClient(_Real):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    httpx.AsyncClient = _ReplayClient  # runner does `httpx.AsyncClient()`

    sys.path.insert(0, os.getcwd())
    from app.db import get_session
    from app.ingest import runner
    from app.ingest import registry

    if args.no_embed:
        import app.ml.embed_jobs as ej
        ej.embed_missing_jobs = lambda *a, **k: 0

    if args.only:
        wanted = {tuple(x.split(":", 1)) for x in args.only.split(",")}
        _orig = runner.load_active_companies
        runner.load_active_companies = lambda s, stale_first=False: [
            c for c in _orig(s, stale_first=stale_first) if (c.ats.value, c.slug) in wanted
        ]

    session = get_session()
    try:
        if args.seed:
            registry.seed_companies_if_empty(session)
        t0 = time.monotonic()
        run = asyncio.run(runner.run_ingest(session, budget_seconds=args.budget))
        out = {
            "run_id": run.id, "secs": round(time.monotonic() - t0, 1),
            "companies_total": run.companies_total, "ok": run.companies_ok,
            "failed": run.companies_failed, "jobs_seen": run.jobs_seen,
            "jobs_new": run.jobs_new, "jobs_closed": run.jobs_closed,
            "failures": [f.get("slug") for f in (run.failures or [])][:20],
        }
        print(json.dumps(out))
    finally:
        session.close()


if __name__ == "__main__":
    main()
