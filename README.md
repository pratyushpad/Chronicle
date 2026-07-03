# Chronicle

Chronicle is a job aggregator that pulls every open role directly from tech companies'
own applicant-tracking systems (Greenhouse, Lever, Ashby) into one searchable, filterable
feed — no scraping job boards, no stale listings. It ingests hundreds of companies on a
recurring schedule, normalizes and deduplicates postings across sources, and layers
accounts, saved jobs/application tracking, recommendations, alerts, and a browser
autofill extension on top.

**Live app:** [chronicles-weld.vercel.app](https://chronicles-weld.vercel.app)

## How it works

```
companies registry (ATS + slug)
        │
        ▼
  source adapters (Greenhouse / Lever / Ashby, async, fault-isolated)
        │
        ▼
  normalize (title/department/location) ──► dedupe (fuzzy match across sources)
        │
        ▼
   PostgreSQL (jobs, companies, ingest_runs)
        │
        ▼
   FastAPI read layer (filters, search, meta) ──► Next.js feed UI
```

Ingestion is **profile-agnostic** — every open role a company posts is stored, across all
departments. Filtering happens at read time in the API/UI, so the company registry is a
*source* list, not a role filter.

## Features

- **Live registry** of 500+ companies, ingested on a recurring schedule with per-company
  fault isolation (one broken board never blocks the run).
- **Cross-source deduplication** — the same req posted to multiple ATS boards, or the
  same role posted to multiple cities, collapses into one card without merging genuinely
  distinct openings.
- **Accounts & tracking** — Google OAuth, saved jobs, an application tracker (kanban-style
  statuses), saved searches, and email alerts for new matching roles.
- **Recommendations** — a "For You" feed based on profile + activity.
- **Hiring velocity** — per-company opened/closed-role trends.
- **Browser autofill extension** — fills Greenhouse/Lever/Ashby application forms from a
  Chronicle profile and saves the role to the tracker in one click. **Fill-only by
  design**: it never calls `form.submit()` or clicks a submit button — you review and
  submit every application yourself.
- **Verified registry expansion** — new companies are only added after being live-probed
  for at least one open role, and default to inactive until confirmed, so the feed never
  fills with dead boards.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI, async `httpx` for concurrent ATS fan-out |
| Dedup | rapidfuzz |
| Database | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Scheduler | APScheduler (in-process worker, also runs as a one-shot CLI) |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui |
| Auth | NextAuth v5 (Google OAuth) |
| Extension | Manifest V3 + TypeScript, esbuild |
| Infra | Docker Compose (api / worker / db / web); deployed on Vercel (web) + Render (api) + Neon (Postgres) |

## Project structure

```
api/          FastAPI backend — routers, ingestion adapters, normalization, dedup, DB models
web/          Next.js frontend
extension/    Browser autofill extension (MV3)
docker-compose.yml
```

## Running locally

Requires Python 3.12+, Node 18+, and PostgreSQL 16 (or use Docker Compose for all of it).

### Option A — Docker Compose

```bash
docker compose up --build
```

Brings up Postgres, the API (`:8000`), the ingest worker, and the web app (`:3000`).

### Option B — run each piece directly

```bash
# 1. Postgres
brew services start postgresql@16   # or your platform's equivalent

# 2. API
cd api
cp .env.example .env                # set DATABASE_URL for your local Postgres
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 3. Ingest (populates the registry with real job data)
python -m app.ingest.schedule --once

# 4. Web
cd web
npm install
npm run dev
```

### Tests

```bash
cd api && pytest
cd web && npx tsc --noEmit
```

## API overview

The FastAPI backend exposes a read API for the feed plus authenticated endpoints for
accounts:

- `GET /jobs`, `GET /jobs/{id}`, `GET /meta` — the public feed, filterable and paginated
- `GET /companies`, `GET /companies/{id}`, `GET /companies/{id}/velocity`
- `GET/POST /saved`, `GET/POST/PUT/DELETE /applications`, `GET/POST/DELETE /searches`
- `GET /recommendations`, `GET /notifications`
- `GET/POST/DELETE /users/me/extension-token`, `POST /extension/saved` — browser extension

See `api/app/routers/` for the full set of endpoints and request/response schemas.

## Registry expansion

Companies are added via a verify-then-write gate (`api/app/ingest/verify_and_add_companies.py`):
a candidate is only written to the registry after being live-probed against its ATS and
confirmed to have at least one open role. See `api/candidates/README.md` for how the
current batches were sourced.
