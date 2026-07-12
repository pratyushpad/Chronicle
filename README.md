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
        ├──► keyword search (Postgres FTS, ts_rank_cd) ─┐
        ├──► semantic search (cosine) ──────────────────├─► RRF fusion ──► hybrid results
        │                                               ┘
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

- **Live registry** of 220+ verified companies (~15k open roles), auto-refreshed every
  24–48h with per-company fault isolation (one broken board never blocks the run). The
  refresh is incremental and idempotent: it upserts changed roles, soft-closes roles that
  vanished from a board (only for boards it actually reached that run), re-embeds only
  content-changed roles, and prunes long-closed roles to stay within Neon's free storage.
  (A curated pipeline to scale the registry toward 1000+ verified boards is in
  `api/candidates/` — see Registry expansion.)
- **Cross-source deduplication** — the same req posted to multiple ATS boards, or the
  same role posted to multiple cities, collapses into one card without merging genuinely
  distinct openings.
- **Accounts & tracking** — Google OAuth, saved jobs, an application tracker (kanban-style
  statuses), saved searches, and email alerts for new matching roles.
- **Full-text + semantic hybrid search** — keyword search is real Postgres full-text
  ranking: a weighted expression (title = A, department + location = C) materialized as a
  **functional GIN index**, ranked by `ts_rank_cd(websearch_to_tsquery(...))` — lexical
  relevance, not substring matching. (A functional index rather than a stored `tsvector`
  column: a stored column of the description body would bloat storage and its `ADD` rewrites
  the table past Neon's 512 MB free tier. The body is left to semantic search instead.) Every
  job is also embedded (all-MiniLM-L6-v2, int8 ONNX — no torch, free-tier friendly) into
  pgvector. Search offers keyword (FTS), pure semantic, and a hybrid mode that fuses the
  **full-text** and vector rankings with Reciprocal Rank Fusion. An HNSW cosine index keeps
  vector retrieval fast; FTS falls back to ILIKE and semantic/hybrid degrade to keyword if the
  relevant index or embedding model is unavailable. (Lexical ranking is Postgres `ts_rank_cd`
  — full-text, not literal BM25.)
- **Recommendations ("For You" v2)** — two-stage matching: pgvector retrieves candidates
  by cosine against a profile vector (profile text + a weighted centroid of saved/applied
  jobs), then a blend of semantic similarity and the explainable rule score reranks them.
  Every card keeps a human-readable "why" string.
- **Measured, not vibes** — an offline eval harness (`api/scripts/eval_matching.py`)
  scores rule-based vs semantic vs hybrid ranking on held-out engagements, with bootstrap
  95% confidence intervals. Across 24 synthetic personas across diverse role families and
  seniorities, hybrid lifts recall@50 from 0.71 to 0.96 and MRR from 0.80 to 0.98 over the
  rule baseline, with NDCG@10 0.58 → 0.81 (semantic and hybrid are close on the persona set;
  the gap widens on real engagement data). The same harness runs in `db` mode against real
  logged engagements. See [docs/eval_results.md](docs/eval_results.md).
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
| Scheduler | External cron (GitHub Actions + cron-job.org) → secured `POST /admin/ingest`; APScheduler also runs as a one-shot CLI |
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
- `GET /health` — cheap, DB-free liveness probe (used by the external keep-warm)
- `POST /admin/ingest` — secured trigger for an incremental refresh (see Refresh & ops)
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
confirmed to have at least one open role (new companies default to inactive until confirmed).
See `api/candidates/README.md` for how the current batches were sourced and how to run the
`candidates/pool_scale.json` scale-up pool through the probe → verify pipeline.

## Refresh & operations

**Keep-warm.** Render's free tier spins the API down after ~15 min idle. The primary
keep-warm is an external **cron-job.org** monitor hitting `GET /health` every 5 min (free,
fires reliably); the `.github/workflows/keep-warm.yml` GitHub Action is a backup, since
GitHub scheduled crons drop fires on low-activity repos. To set it up: create a cron-job.org
job, method GET, URL `https://<api-host>/health`, every 5 minutes. The frontend also shows
skeletons and retries once on timeout, so a cold start never renders a blank screen.

**Auto-refresh (every 24–48h).** `POST /admin/ingest` triggers an incremental, idempotent
refresh in the background (returns `202` immediately; a DB run-lock prevents overlap). It is
guarded by a dedicated `INGEST_SECRET` (header `X-Ingest-Secret`; 401 without it). The
`.github/workflows/ingest.yml` scheduled workflow calls it daily with the repo secret
`INGEST_SECRET` (also set as a Render env var). Because GitHub crons are unreliable, a second
daily cron-job.org trigger to the same endpoint is a safe backup — the run-lock + idempotent
upsert make a double-fire harmless. A `budget_seconds` query param bounds wall-clock time so a
large run fits a Render window and continues (stalest-first) on the next invocation.

**Storage caveat.** Neon's free tier is ~0.5 GB. At 1000+ companies the full posting history
would exceed it, so ingest **prunes** roles that have been closed and unseen for >30 days
(hard-delete; embeddings drop with the row). Only active + recently-closed roles stay hot.
Retaining longer history requires a paid Neon tier.

**Migrations.** Schema changes are Alembic migrations; against prod Neon they are applied
manually (`alembic upgrade head`) after a snapshot. The FTS `search_tsv` column, its GIN
index, and `content_hash` ship as migrations `c1a2b3d4e5f6` and `d2b3c4e5f6a7`.
