# Upgrade verification harness (dev-only)

Tools used to verify the Sept 2026 upgrade PRs (`docs/UPGRADE_PLAN.md`). Nothing here runs in
production, and none of it may ever point at Neon: every Python tool refuses a non-local
`DATABASE_URL`.

## Local database

Any Postgres 16 with pgvector works. With Docker:

```bash
docker run -d --name chronicle-upgrade-db -e POSTGRES_DB=chronicle \
  -e POSTGRES_USER=chronicle -e POSTGRES_PASSWORD=chronicle \
  -p 127.0.0.1:5434:5432 pgvector/pgvector:pg16
docker exec chronicle-upgrade-db psql -U chronicle -d chronicle \
  -c "create database chronicle_test;" -c "create database chronicle_dev;"
```

Without Docker (Ubuntu): `apt-get install postgresql-16 postgresql-16-pgvector`, then create the
same role and databases. Always export the URL explicitly, e.g.
`DATABASE_URL=postgresql+psycopg2://chronicle:chronicle@127.0.0.1:5434/chronicle`.

## Record once, replay always

| Tool | What it does |
|---|---|
| `record_boards.py <companies.seed.json> <out_dir>` | One polite pass over every active board (concurrency 3, spaced requests per host). Saves each raw payload as `<out_dir>/<ats>/<slug>.json.gz` plus `manifest.json`. About 4 minutes, about 70 MB gzipped. |
| `replay_ingest.py <out_dir> [--seed] [--no-embed] [--only ats:slug,...] [--budget N]` | Runs the real `run_ingest` against the recorded bytes through an httpx `MockTransport`: no network, deterministic. Run it from `api/` so the checked-out branch's code is what runs. |
| `replica_metrics.py <postgres-url> [label]` | Read-only metrics as JSON: department "Other" share (all roles and interns), pay coverage, hash versions, NULL embeddings, storage, tuple stats. |
| `sample_intern_pay.py <out_dir> <out.jsonl> [n] [seed]` | Stratified sample of real intern postings for blind pay labeling. |

Building a replica: `alembic upgrade head` on the local DB, then
`replay_ingest.py <out_dir> --seed` (embeds every row, which takes about 13 minutes on an M-series
Mac). Snapshot it with `pg_dump -Fc` so each branch can start from the same data.

Proving a hash or format change doesn't re-embed: restore the snapshot, run the branch's migration
and backfill, then `replay_ingest.py --no-embed` twice. Count `embedding IS NULL` after each pass:
the first pass may null genuinely changed rows, the second must null none.

## Web checks (`web/`)

`npm install` once in `tools/upgrade/web`, plus `npx playwright install chromium`. All of it is
headless.

| Tool | What it does |
|---|---|
| `shots.mjs <config.json>` | Screenshots at the configured sizes (1440×900, 390×844) and a horizontal-overflow audit at 360/390/414 px that names the offending elements. With `"reducedMotionAudit": true` it also reports text blocks left invisible under `prefers-reduced-motion: reduce`. The config shape is in the file header. |
| `lh.mjs <url> [runs] [label]` | Lighthouse on mobile, median of N runs (performance, accessibility, LCP, CLS, TBT). |
| `mint-session.mjs <web_dir> <email>` | Mints an Auth.js session cookie so signed-in pages of a local build can be checked. It refuses unless `LOCAL_AUTH_SECRET` starts with `local-`, so it can only ever match a throwaway local secret. |
