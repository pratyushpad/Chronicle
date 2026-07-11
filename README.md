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
  embed (ONNX int8 MiniLM, 384-dim, at ingest + nightly sweep)
        │
        ▼
   PostgreSQL + pgvector (jobs + embeddings, HNSW cosine index)
        │
        ├──► keyword search (ILIKE) ─┐
        ├──► semantic search (cosine)├─► RRF fusion ──► hybrid results
        │                            ┘
        ├──► For-You v2: profile vector (profile text + engaged-jobs centroid)
        │      → top-200 cosine retrieval → 0.6·cosine + 0.4·rule-score rerank
        │
        ▼
   FastAPI read layer ──► Next.js feed UI (mode toggle, "why" strings)
```

Ingestion is **profile-agnostic** — every open role a company posts is stored, across all
departments. Filtering happens at read time in the API/UI, so the company registry is a
*source* list, not a role filter.

## Features

- **Live registry** of 220+ companies (~15k open roles), ingested on a recurring schedule
  with per-company fault isolation (one broken board never blocks the run).
- **Cross-source deduplication** — the same req posted to multiple ATS boards, or the
  same role posted to multiple cities, collapses into one card without merging genuinely
  distinct openings.
- **Accounts & tracking** — Google OAuth, saved jobs, an application tracker (kanban-style
  statuses), saved searches, and email alerts for new matching roles.
- **Semantic + hybrid search** — every job is embedded (all-MiniLM-L6-v2, int8 ONNX — no
  torch, free-tier friendly) into pgvector; search offers keyword, pure semantic, and a
  hybrid mode that fuses both rankings with Reciprocal Rank Fusion. An HNSW cosine index
  keeps vector retrieval fast; semantic/hybrid degrade gracefully to keyword if the
  embedding model is unavailable.
- **Recommendations ("For You" v2)** — two-stage matching: pgvector retrieves candidates
  by cosine against a profile vector (profile text + a weighted centroid of saved/applied
  jobs), then a blend of semantic similarity and the explainable rule score reranks them.
  Every card keeps a human-readable "why" string.
- **Measured, not vibes** — an offline eval harness (`api/scripts/eval_matching.py`)
  scores rule-based vs semantic vs hybrid ranking on held-out engagements, with bootstrap
  95% confidence intervals. Across 10 synthetic personas, hybrid lifts NDCG@10 from 0.76 to
  0.83 and MRR from 0.88 to 1.00 over the rule baseline (recall@50 0.91 → 1.00). The same
  harness runs in `db` mode against real logged engagements. See
  [docs/eval_results.md](docs/eval_results.md).
- **Interaction logging** — impressions/clicks/saves are captured per surface
  (feed/search) as training data for a future learned ranker.
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
| Embeddings | all-MiniLM-L6-v2 (int8 ONNX via onnxruntime + tokenizers — no torch, ~150 MB RSS) |
| Database | PostgreSQL + pgvector (HNSW) + SQLAlchemy 2.0 + Alembic |
| Auth (web→API) | HMAC-signed short-lived internal tokens (`api/app/internal_auth.py`) |
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
cp .env.example .env                # set DATABASE_URL + INTERNAL_API_SECRET
pip install -e ".[dev]"
python -m app.ml.download           # fetch the ONNX embedding model (~23 MB, one-time)
python -m alembic upgrade head      # includes CREATE EXTENSION vector (needs pgvector)
uvicorn app.main:app --reload --port 8000

# 3. Ingest (populates the registry with real job data, embeds new jobs)
python -m app.ingest.schedule --once
python -m scripts.backfill_embeddings   # embed any pre-existing corpus

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

- `GET /jobs` (`?mode=keyword|semantic|hybrid`), `GET /jobs/{id}`, `GET /meta` — the
  public feed, filterable and paginated; semantic/hybrid rank by pgvector cosine + RRF
- `GET /companies`, `GET /companies/{id}`, `GET /companies/{id}/velocity`
- `GET/POST /saved`, `GET/POST/PUT/DELETE /applications`, `GET/POST/DELETE /searches`
- `GET /recommendations`, `GET /notifications`, `POST /interactions/batch`
- `GET/POST/DELETE /users/me/extension-token`, `POST /extension/saved` — browser extension

Authenticated endpoints require an `X-Internal-Auth` token — an HMAC-SHA256-signed,
5-minute claim minted by the Next.js server proxy (`web/src/lib/internal-token.ts`) and
verified by the API (`api/app/internal_auth.py`). Raw identity headers are never trusted.

See `api/app/routers/` for the full set of endpoints and request/response schemas.

## Registry expansion

Companies are added via a verify-then-write gate (`api/app/ingest/verify_and_add_companies.py`):
a candidate is only written to the registry after being live-probed against its ATS and
confirmed to have at least one open role. See `api/candidates/README.md` for how the
current batches were sourced.
