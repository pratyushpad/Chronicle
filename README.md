# Chronicle

[![ci](https://github.com/pratyushpad/Chronicle/actions/workflows/ci.yml/badge.svg)](https://github.com/pratyushpad/Chronicle/actions/workflows/ci.yml)

Chronicle is a job aggregator that pulls every open role directly from tech companies'
own applicant-tracking systems (Greenhouse, Lever, Ashby) into one searchable, filterable
feed, built first for students looking for internships and early-career roles. It reads
hundreds of company boards on a rolling schedule, normalizes and deduplicates postings
across sources, and layers accounts, saved jobs/application tracking, recommendations, and
alerts on top. Every number below links to how it was measured: [docs/metrics.md](docs/metrics.md).

**Live app:** [chronicles-weld.vercel.app](https://chronicles-weld.vercel.app)

| | |
|:---:|:---:|
| ![Homepage](docs/screenshots/upgrade/pr3/after-home-1440.jpg) | ![Internship feed](docs/screenshots/upgrade/pr4/after-jobs-1440.jpg) |
| *Homepage: search and live numbers first* | *Internship feed: one search, four filters, sort* |
| ![Job detail](docs/screenshots/upgrade/pr4/after-job-1440.jpg) | ![Companies](docs/screenshots/upgrade/pr3/after-companies-1440.jpg) |
| *Job detail: pay as posted, term, degrees, sticky Apply* | *Companies: search, 21 industries* |

Screenshots are from a local build against a fixture replica of 119 real postings, so the
counts in them are small; the live site shows the full registry.

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

Ingestion is **profile-agnostic**: every open role a company posts is stored, across all
departments. Filtering happens at read time in the API/UI, so the company registry is a
*source* list, not a role filter.

## Features

- **Live registry** of 600+ verified company boards (`api/companies.seed.json`; live counts
  of open roles and re-checked boards are on the site and at `/status`), refreshed twice a
  day on GitHub Actions (see Refresh & operations), stalest boards first, with per-company
  fault isolation (one broken board never blocks the run). The
  refresh is incremental and idempotent: it upserts changed roles, soft-closes roles that
  vanished from a board (only for boards it actually reached that run), re-embeds only
  content-changed roles, keeps unchanged descriptions in place (no storage churn), and
  prunes long-closed roles to stay within Neon's free storage. Only one run goes at a time
  (a run refuses to start while another, younger than two hours, is still open).
  (A curated pipeline to scale the registry toward 1000+ verified boards is in
  `api/candidates/`; see Registry expansion.)
- **Cross-source deduplication.** The same req posted to multiple ATS boards, or the
  same role posted to multiple cities, collapses into one card without merging genuinely
  distinct openings.
- **Accounts & tracking.** Google OAuth, saved jobs, an application tracker (kanban-style
  statuses), and saved-search alerts for new matching roles: in-app always, plus email
  digests. Set `RESEND_API_KEY` in **both** places: as a GitHub Actions secret (the scheduled
  ingest sends the digests) and on the Render API (the site says "email" only when the API
  has it, via `/meta.email_alerts`, and the `ingest.yml` fallback sends from Render).
  `RESEND_FROM` and `APP_URL` fall back to defaults when empty.
- **Facts students need, only when stated.** Pay as posted ("$30 to 45/hr", structured ATS
  pay first, then the text; company money such as "$116M raised" or "saves $2M in contract
  value" is never read as pay, and an explicit pay label wins), the internship term, the degree levels a posting mentions, and
  the country. Unknown stays unknown. Extraction precision is measured on a labeled set of
  real postings, and a field reaches the site only at ≥ 0.9 held-out precision
  ([pay](docs/pay_eval.md), [student fields](docs/extraction_eval.md)); citizenship,
  clearance and MS/PhD-only filters are built but stay off until they clear that bar.
- **Early-career scope.** Senior and management roles whose title has no early-career
  marker (intern, new grad, associate, entry level and similar) are **listing-only**: they
  stay in the feed with their title, pay and location and link to the company's posting,
  but Chronicle stores no description and no embedding for them, so they don't appear in
  semantic search, For You or similar roles (`normalize.is_out_of_scope`).
- **Readable job pages.** Descriptions keep their structure (headings, lists, links) as a
  sanitized HTML subset rendered as React elements; an at-a-glance panel, sticky Apply,
  similar roles from pgvector, and closed roles marked and not indexed. Metadata, social
  images, JSON-LD (known fields only), a sitemap and robots.
- **Design.** Light and dark themes (following the system, with a toggle), WCAG AA
  contrast checked in tests for every token pair, no horizontal scroll on phones, and
  reduced-motion support.
- **Full-text + semantic hybrid search.** Keyword search is real Postgres full-text
  ranking: a weighted expression (title = A, department + location = C) materialized as a
  **functional GIN index**, ranked by `ts_rank_cd(websearch_to_tsquery(...))`. That's
  lexical relevance, not substring matching. (A functional index rather than a stored
  `tsvector` column: a stored column of the description body would bloat storage and its
  `ADD` rewrites the table past Neon's 512 MB free tier. The body is left to semantic
  search instead.) Every job is also embedded (all-MiniLM-L6-v2, int8 ONNX, no torch,
  free-tier friendly) into pgvector. Search offers keyword (FTS), pure semantic, and a
  hybrid mode that fuses the **full-text** and vector rankings with Reciprocal Rank
  Fusion. An HNSW cosine index keeps vector retrieval fast; FTS falls back to ILIKE and
  semantic/hybrid degrade to keyword if the relevant index or embedding model is
  unavailable. (Lexical ranking is Postgres `ts_rank_cd`: full-text, not literal BM25.)
- **Recommendations ("For You" v2).** Two-stage matching: pgvector retrieves candidates
  by cosine against a profile vector (profile text + a weighted centroid of saved/applied
  jobs), then a blend of semantic similarity and the explainable rule score reranks them.
  Every card keeps a human-readable "why" string.
- **Measured, not vibes.** An offline eval harness (`api/scripts/eval_matching.py`)
  scores rule-based vs semantic vs hybrid ranking on held-out engagements, with bootstrap
  95% confidence intervals. Across 24 synthetic personas across diverse role families and
  seniorities, hybrid lifts recall@50 from 0.71 to 0.96 and MRR from 0.80 to 0.98 over the
  rule baseline, with NDCG@10 going 0.58 to 0.81 (semantic and hybrid are close on the
  persona set; the gap widens on real engagement data). The same harness runs in `db` mode
  against real logged engagements. See [docs/eval_results.md](docs/eval_results.md).
- **Interaction logging.** Impressions/clicks/saves are captured per surface
  (feed/search) as training data for a future learned ranker.
- **Hiring velocity.** Per-company opened/closed-role trends, dated by each posting's own
  publish date, with roles that were already open at a board's first read left out.
- **Status page.** `/status` shows the recent ingest runs, boards failing to load, and
  freshness, straight from the run log.
- **Verified registry expansion.** New companies are only added after being live-probed
  for at least one open role, and default to inactive until confirmed, so the feed never
  fills with dead boards.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI, async `httpx` for concurrent ATS fan-out |
| Dedup | rapidfuzz |
| Embeddings | all-MiniLM-L6-v2 (int8 ONNX via onnxruntime + tokenizers, no torch, ~150 MB RSS) |
| Database | PostgreSQL + pgvector (HNSW) + SQLAlchemy 2.0 + Alembic |
| Auth (web→API) | HMAC-signed short-lived internal tokens (`api/app/internal_auth.py`) |
| Scheduler | GitHub Actions `ingest-actions` twice a day: `python -m app.ingest.schedule --once --budget 4200` (a full refresh, then embeddings); fallback until its secret exists: `ingest.yml` → secured `POST /admin/ingest` on Render |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui; Playfair Display, Inter, Source Serif |
| CI | pytest (with a pgvector service), tsc, ESLint, Vitest, build, Playwright + axe, Lighthouse budget |
| Auth | NextAuth v5 (Google OAuth) |
| Infra | Docker Compose (api / worker / db / web); deployed on Vercel (web) + Render (api) + Neon (Postgres) |

## Project structure

```
api/          FastAPI backend: routers, ingestion adapters, normalization, dedup, DB models
web/          Next.js frontend (Playwright smoke tests in web/e2e)
tools/        Verification harness: board recording/replay, replica metrics, screenshots,
              overflow audit, Lighthouse (dev-only; never points at production)
docs/         Measurements (metrics.md links them all), eval results, upgrade plan
docker-compose.yml
```

## Running locally

Requires Python 3.12+, Node 18+, and PostgreSQL 16 (or use Docker Compose for all of it).

### Option A: Docker Compose

```bash
docker compose up --build
```

Brings up Postgres, the API (`:8000`), the ingest worker, and the web app (`:3000`).

### Option B: run each piece directly

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
# API (database-backed tests run when TEST_DATABASE_URL points at a local, migrated Postgres)
cd api && TEST_DATABASE_URL=postgresql+psycopg2://chronicle:chronicle@localhost:5432/chronicle_test pytest
# Web
cd web && npx tsc --noEmit && npm run lint && npm test && npm run build
# End to end, against a running `next start` + API (CI seeds it from committed fixtures)
cd web && E2E_BASE_URL=http://localhost:3000 npx playwright test
```

## API overview

The FastAPI backend exposes a read API for the feed plus authenticated endpoints for
accounts:

- `GET /jobs` (`?mode=keyword|semantic|hybrid`, `sort=newest|relevance|pay`, `level`,
  `location`, `department`, `industry`, `term`, `country`, …), `GET /jobs/{id}` (typed
  description blocks), `GET /jobs/{id}/similar`, `GET /meta`: the public feed, filterable
  and paginated; semantic/hybrid rank by pgvector cosine + RRF
- `GET /status`: recent ingest runs, failing boards and freshness (public, cached)
- `GET /sitemap/jobs`: one URL per distinct active role, for the web sitemap
- `POST /admin/bench`: secured production search-latency benchmark
- `GET /health`: cheap, DB-free liveness probe (used by the external keep-warm)
- `POST /admin/ingest`: secured trigger for an incremental refresh (see Refresh & ops)
- `GET /companies`, `GET /companies/{id}`, `GET /companies/{id}/velocity`
- `GET/POST /saved`, `GET/POST/PUT/DELETE /applications`, `GET/POST/DELETE /searches`
- `GET /recommendations`, `GET /notifications`, `POST /interactions/batch`

Authenticated endpoints require an `X-Internal-Auth` token: an HMAC-SHA256-signed,
5-minute claim minted by the Next.js server proxy (`web/src/lib/internal-token.ts`) and
verified by the API (`api/app/internal_auth.py`). Raw identity headers are never trusted.

See `api/app/routers/` for the full set of endpoints and request/response schemas.

## Registry expansion

Companies are added via a verify-then-write gate (`api/app/ingest/verify_and_add_companies.py`):
a candidate is only written to the registry after being live-probed against its ATS and
confirmed to have at least one open role (new companies default to inactive until confirmed).
See `api/candidates/README.md` for how the current batches were sourced and how to run the
`candidates/pool_scale.json` scale-up pool through the probe → verify pipeline.

Sources and why: [docs/sources.md](docs/sources.md). Greenhouse, Lever and Ashby are read
through their public board APIs. SmartRecruiters is excluded (its robots.txt disallows
crawlers). Workday and Workable adapters are planned but not built yet. A company that wants
its board removed can [open an issue](https://github.com/pratyushpad/Chronicle/issues).

## Refresh & operations

**Keep-warm.** Render's free tier spins the API down after ~15 min idle. The primary
keep-warm is an external **cron-job.org** monitor hitting `GET /health` every 5 min (free,
fires reliably); the `.github/workflows/keep-warm.yml` GitHub Action is a backup, since
GitHub scheduled crons drop fires on low-activity repos. To set it up: create a cron-job.org
job, method GET, URL `https://<api-host>/health`, every 5 minutes. The frontend also shows
skeletons and retries once on timeout, so a cold start never renders a blank screen.

**Auto-refresh (twice a day).** `.github/workflows/ingest-actions.yml` runs
`python -m app.ingest.schedule --once` on a GitHub Actions runner at 04:17 and 16:17 UTC: it
refreshes every active board (stalest first), then embeds new roles. It needs the repo secret
`NEON_DATABASE_URL` (Neon, pooled off) and skips itself without it. Once the secret is set,
`ingest.yml`'s schedule stands down, so exactly one scheduled refresh runs (GitHub may start
scheduled runs a few hours late). Render's free 512 MB box is
too small for a full pass: `.github/workflows/ingest.yml` asks the Render API for a 600-second
slice, which reaches only a few dozen boards, so on its own a full pass takes about two weeks.
The site shows how recently boards were checked (`/meta` → `freshness`).

**Render trigger.** `POST /admin/ingest` triggers an incremental, idempotent refresh on
Render in the background (returns `202` immediately). It is guarded by a dedicated
`INGEST_SECRET` (header `X-Ingest-Secret`; 401 without it), which `ingest.yml` sends from the
repo secret `INGEST_SECRET` (also set as a Render env var). A `budget_seconds` query param
bounds wall-clock time. Both paths refuse to start while a run younger than two hours is still
open, and the upsert is idempotent, so a double-fire is harmless.


**Storage caveat.** Neon's free tier has a hard 512 MB project-size limit. Three policies
keep the live corpus (hundreds of boards, tens of thousands of roles + 384-dim embeddings)
under it: ingest stores a **sanitized HTML subset of each description, capped at 20,000
characters, never the raw ATS HTML** (the raw HTML was ~126 MB that no endpoint served;
the subset costs about 7% more than plain text), re-ingest leaves unchanged descriptions
untouched instead of rewriting them; ingest **prunes** roles closed and unseen for >30 days
(hard-delete; embeddings drop with the row); and full-text search uses a functional GIN index
rather than a stored `tsvector` column (a stored column's table rewrite alone exceeds the
limit). Scaling toward 1000+ companies-with-jobs, or retaining longer history, needs a paid
Neon tier.

**Migrations.** Schema changes are Alembic migrations; against prod Neon they are applied
manually after a Neon backup branch, with `CHRONICLE_ALLOW_REMOTE_DB=1` (Alembic and the
backfills refuse any non-local database without it). Each PR that has one carries the exact
runbook; see `docs/UPGRADE_PLAN.md`. The FTS `search_tsv` column, its GIN
index, and `content_hash` ship as migrations `c1a2b3d4e5f6` and `d2b3c4e5f6a7`.
