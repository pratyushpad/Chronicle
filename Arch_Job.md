# OpenRoles — Baseline Architecture

> Working name: **OpenRoles** (rename freely). This document is the build spec for the
> **baseline** only. The baseline has **zero AI** in it: pull every open role from a
> registry of companies via their public ATS APIs, normalize, dedupe, store, and serve a
> browsable/filterable feed that refreshes every 48 hours. Recommendations, the
> questionnaire, and the swipe UI are **Phase 2** and are explicitly out of scope here —
> the schema leaves hooks for them, nothing more.

---

## 0. Scope guard (read first)

**In scope (baseline):**
- Company registry (seed: ~50 companies, expandable).
- Source adapters for Greenhouse, Lever, Ashby (public, keyless JSON endpoints).
- Normalizer → one unified `Job` schema.
- Deduplication across sources.
- Storage (PostgreSQL) with `first_seen` / `last_seen` lifecycle.
- Scheduler: concurrent, fault-isolated ingestion every 48h.
- Read API (FastAPI) with filters.
- Feed UI (Next.js) in the Serif design system.

**Explicitly OUT of scope (do NOT build):**
- Any scoring, ranking, or ML.
- The onboarding questionnaire.
- Personalized recommendations.
- The Tinder/swipe interface.
- User accounts / auth (the baseline is a public, read-only feed).
- LinkedIn / Indeed / Handshake scraping.

> If a change request would add anything from the OUT list, stop and confirm. The baseline
> is "done" when the feed shows real jobs from all registry companies and refreshes on a
> 48h schedule. Ship that before anything else.

---

## 1. Storage vs. filtering (the core principle)

Ingestion is **profile-agnostic**: store *every* open role a company posts — engineering,
design, sales, finance, recruiting, ops, all of it. Never drop a role at ingestion time.

Filtering is a **read-layer** concern: the API and UI filter the stored data per request.
A marketing major and an ML student hit the same database and get different views. This
separation is what makes this "a Simplify," not "a job bot for one person." The 50
companies are a **source** list, not a **role** filter.

---

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | Read API + ingestion package share one codebase. |
| HTTP | **httpx (async)** | Concurrent fan-out across companies. |
| Fuzzy match | **rapidfuzz** | Dedup. |
| DB | **PostgreSQL 16** | `jobs`, `companies`, `ingest_runs`. |
| ORM/migrations | **SQLAlchemy 2.0 + Alembic** | Typed models, versioned schema. |
| Scheduler | **APScheduler** (in-process worker) | One-shot CLI mode too, so it runs under cron / GitHub Actions if preferred. |
| Frontend | **Next.js 14 (App Router) + TypeScript** | Reuses the existing scaffold. |
| Styling | **Tailwind + shadcn/ui** | Serif tokens replace the old dark tokens. |
| Container | **Docker + docker-compose** | api, worker, db, web. |

Rationale: this is the stack you already know (FastAPI from FacePulse/Argus, Next.js/TS
from the scaffold), so build time goes into the *systems* parts — adapters, dedup,
fault-isolated scheduling — not into learning tooling.

---

## 3. High-level architecture

```
                         ┌──────────────────────────────────────────┐
                         │            INGESTION (worker)            │
                         │                                          │
  companies table  ───►  │  registry  ──►  adapters (async, fanned  │
   (ATS + slug)          │                 out, fault-isolated)     │
                         │                     │                    │
                         │   Greenhouse ──┐    │                    │
                         │   Lever ───────┼──► normalizer ──► dedup │
                         │   Ashby ───────┘                    │    │
                         │                                     ▼    │
                         │                              upsert jobs │
                         └──────────────────┬───────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │   PostgreSQL    │
                                   │  jobs/companies │
                                   └────────┬────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐        ┌───────────────┐
                                   │  FastAPI (read) │ ◄────► │  Next.js feed │
                                   │  /jobs filters  │  JSON  │  (Serif UI)   │
                                   └─────────────────┘        └───────────────┘
```

The worker and the API are separate processes. The worker writes; the API only reads.

---

## 4. Repo structure

```
openroles/
├─ api/
│  ├─ app/
│  │  ├─ main.py                  # FastAPI app, CORS, router mount
│  │  ├─ db.py                    # engine, session
│  │  ├─ models.py                # SQLAlchemy: Company, Job, IngestRun
│  │  ├─ schemas.py               # Pydantic response models
│  │  ├─ routers/
│  │  │  └─ jobs.py               # GET /jobs, GET /jobs/{id}, GET /companies, GET /meta
│  │  └─ ingest/
│  │     ├─ registry.py           # load companies from DB (seeded from companies.seed.json)
│  │     ├─ normalize.py          # unified Job shape + helpers
│  │     ├─ dedupe.py             # dedup key + fuzzy collapse
│  │     ├─ runner.py             # async orchestration, fault isolation, upsert
│  │     ├─ schedule.py           # APScheduler entry + one-shot CLI
│  │     └─ adapters/
│  │        ├─ base.py            # ATSAdapter protocol (the contract)
│  │        ├─ greenhouse.py
│  │        ├─ lever.py
│  │        └─ ashby.py
│  ├─ alembic/                    # migrations
│  ├─ companies.seed.json         # the registry seed
│  └─ tests/
│     ├─ test_adapters.py         # fixture-based, no live network
│     ├─ test_normalize.py
│     └─ test_dedupe.py
├─ web/
│  ├─ src/app/
│  │  ├─ layout.tsx               # fonts (next/font), <body> tokens
│  │  ├─ page.tsx                 # landing (Serif hero)
│  │  ├─ jobs/page.tsx            # the feed (filter + list)
│  │  └─ jobs/[id]/page.tsx       # job detail
│  ├─ src/components/
│  │  ├─ JobCard.tsx
│  │  ├─ FilterBar.tsx
│  │  ├─ SectionLabel.tsx         # the rule-line + small-caps label
│  │  └─ ui/                      # shadcn primitives
│  ├─ src/lib/api.ts              # typed fetch wrapper to FastAPI
│  ├─ tailwind.config.ts          # Serif tokens
│  └─ src/app/globals.css         # CSS vars, fonts, utilities
└─ docker-compose.yml
```

---

## 5. Data model

### `companies`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | text | "Stripe" |
| `ats` | enum(`greenhouse`,`lever`,`ashby`) | which adapter to use |
| `slug` | text | the board token / site name |
| `careers_url` | text, nullable | for display |
| `active` | bool | skip in run if false |
| `last_ingested_at` | timestamptz, nullable | |
| | | **unique(`ats`, `slug`)** |

### `jobs`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | internal |
| `company_id` | FK → companies | |
| `source` | enum | same values as `ats` |
| `source_job_id` | text | stable id from the ATS |
| `title` | text | |
| `title_normalized` | text | lowercased, trimmed, see §8 |
| `location_raw` | text, nullable | |
| `location_normalized` | text, nullable | |
| `remote` | bool, nullable | inferred when ATS doesn't say |
| `department` | text, nullable | |
| `employment_type` | text, nullable | full-time/intern/contract when available |
| `description_html` | text, nullable | raw JD |
| `description_text` | text, nullable | stripped, for future search/embeddings |
| `apply_url` | text | the real ATS apply link — always link out here |
| `posted_at` | timestamptz, nullable | when ATS exposes it |
| `dedup_key` | text, indexed | see §8 |
| `first_seen_at` | timestamptz | set on first insert |
| `last_seen_at` | timestamptz | updated every run the job appears |
| `is_active` | bool | false when not seen in latest run (role closed) |
| | | **unique(`source`, `source_job_id`)** |

> **Phase-2 hooks (leave the columns, don't use them yet):** `description_text` exists so a
> future embedding/recommendation layer has clean text without a migration. No
> `users`/`profiles`/`scores` tables in the baseline.

### `ingest_runs`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `started_at` / `finished_at` | timestamptz | |
| `companies_total` | int | |
| `companies_ok` | int | |
| `companies_failed` | int | |
| `jobs_seen` | int | |
| `jobs_new` | int | |
| `jobs_closed` | int | |
| `failures` | jsonb | `[{company, ats, slug, error}]` — fault log |

The `ingest_runs` table is the observability story. "I can show you the last run: 48/50
companies OK, 2 failed with the reason, 312 new roles, 47 closed" is a strong interview line.

---

## 6. The adapter contract (architectural centerpiece)

Every ATS returns a different shape. One Protocol normalizes that away. This interface is
the thing to point at when asked about the design.

```python
# api/app/ingest/adapters/base.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class RawJob:
    source_job_id: str
    title: str
    location: str | None
    department: str | None
    employment_type: str | None
    description_html: str | None
    apply_url: str
    posted_at: str | None          # ISO string or None; normalizer parses
    remote: bool | None

class ATSAdapter(Protocol):
    source: str                    # "greenhouse" | "lever" | "ashby"
    async def fetch(self, slug: str, client: "httpx.AsyncClient") -> list[RawJob]:
        """Hit the public endpoint for `slug`, return raw jobs. Raises on hard failure."""
```

Adding a new ATS later = one new file implementing this Protocol + an enum value. Nothing
else changes. That extensibility is the point.

---

## 7. Per-ATS adapter specs (endpoints verified current, 2026)

All three are public, keyless, no proxy. Pass the company's slug.

### Greenhouse
```
GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
```
- Jobs under `.jobs[]`. Fields: `id`, `title`, `location.name`, `absolute_url`,
  `updated_at`, `content` (HTML-entity-encoded — **decode it**), `departments[].name`.
- No salary. No native remote flag → infer from title/location text.

### Lever
```
GET https://api.lever.co/v0/postings/{slug}?mode=json
```
- Returns a JSON array. Fields: `id`, `text` (title), `categories.location`,
  `categories.team`, `categories.commitment` (employment type), `hostedUrl` (apply),
  `descriptionPlain` / `description`, `createdAt` (epoch ms).
- Supports source-side filtering params (`location`, `team`, `commitment`) — not needed
  for baseline since we store everything, but worth knowing.

### Ashby
```
GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
```
- Jobs under `.jobs[]`. Fields: `id`, `title`, `location`, `department`, `employmentType`,
  `jobUrl` (apply), `publishedAt`, `isRemote`, optional `compensation`.
- Cleanest of the three; has a real remote flag and sometimes salary.

**Adapter rules (all three):**
- Wrap the call in a timeout (10s). Raise on non-2xx or malformed payload.
- Never invent fields. Missing data → `None`. (Honest nulls, not fake values.)
- Decode/strip HTML in the normalizer, not the adapter.

---

## 8. Normalization & deduplication

### Normalize
- `title_normalized` = lowercase, collapse whitespace, strip trailing req-IDs/parens.
- `location_normalized` = lowercase, strip "Remote -", split "City, ST".
- `remote` = adapter flag if present, else `True` if `/remote/i` in title or location.
- `description_text` = strip HTML from `description_html` (use `selectolax` or `bs4`).
- `posted_at` = parse each source's date format to UTC `timestamptz`.

### Dedup
Same role gets cross-posted and reposted with new IDs. Two layers:

1. **Hard identity** (within a source): `unique(source, source_job_id)` — handled by upsert.
2. **Cross-posting collapse:** `dedup_key = sha1(company_id | title_normalized | location_normalized)`.
   On upsert, if a row with the same `dedup_key` already exists and is active, keep the
   earliest `first_seen_at` and prefer the richest record (one with salary/description).
3. **Fuzzy pass (optional, after exact works):** within a company, `rapidfuzz` on
   `title_normalized` ≥ 92 collapses "Software Engineer, Backend" vs "Backend Software
   Engineer". Ship exact first; add fuzzy only if the feed visibly shows dupes.

---

## 9. Ingestion runner (concurrency + fault isolation)

```
async def run_ingest():
    record an ingest_runs row (started_at)
    companies = load active companies from DB
    async with httpx.AsyncClient() as client:
        results = await gather_with_concurrency(
            limit=10,
            tasks=[ingest_company(c, client) for c in companies],
            return_exceptions=True,        # <-- one failure can't kill the run
        )
    for each result:
        if exception: record into failures[], increment companies_failed
        else: upsert jobs, increment companies_ok
    mark is_active=False for jobs not seen this run (closed roles) → jobs_closed
    finalize ingest_runs row (counts, finished_at)
```

Non-negotiables (these are the resume signal):
- **Bounded concurrency** (semaphore, ~10) — don't open 50 sockets at once.
- **Per-company isolation** — `return_exceptions=True`; a dead slug logs to `failures[]`
  and the run continues.
- **Per-company timeout + 1 retry** with backoff before counting a failure.
- **Idempotent upserts** — running twice produces the same DB state.
- **Closed-role detection** — anything not seen this run flips `is_active=False`; the feed
  only shows active, but history is preserved.

Run modes:
- `python -m app.ingest.schedule` → APScheduler, fires every 48h.
- `python -m app.ingest.schedule --once` → single run (for cron / GitHub Actions / manual).

---

## 10. Read API (FastAPI)

All read-only. Link out to `apply_url` — never proxy applications.

| Endpoint | Purpose |
|---|---|
| `GET /jobs` | Paginated feed. Query params below. |
| `GET /jobs/{id}` | Single job detail. |
| `GET /companies` | Registry list + per-company active job counts. |
| `GET /meta` | Filter facets (departments, locations, types) + last run summary. |

`GET /jobs` params: `q` (title search), `company`, `department`, `location`, `remote`,
`employment_type`, `posted_after`, `since_last_run` (bool → new roles), `sort`
(`posted_at` desc default), `page`, `page_size`. Only `is_active=True` returned.

> Keep filtering in SQL (indexed columns), not in Python. Index `dedup_key`,
> `company_id`, `is_active`, `posted_at`.

---

## 11. Frontend — Serif design system

The feed is content-dense, so the discipline is: **Playfair Display for headlines and the
job titles only; everything operational (filters, meta, counts) in Source Sans 3 / IBM Plex
Mono.** Let the type carry the personality; keep the working surfaces quiet. The signature
element is the **rule-line + small-caps section label** and the **thin top-accent on cards**
— spend the boldness there, keep the rest restrained.

### 11.1 Fonts (`web/src/app/layout.tsx`, next/font)
```ts
import { Playfair_Display, Source_Sans_3, IBM_Plex_Mono } from "next/font/google";
const display = Playfair_Display({ subsets:["latin"], variable:"--font-display" });
const body    = Source_Sans_3({ subsets:["latin"], variable:"--font-body" });
const mono    = IBM_Plex_Mono({ subsets:["latin"], weight:["500"], variable:"--font-mono" });
// apply `${display.variable} ${body.variable} ${mono.variable}` on <html>
```

### 11.2 Tokens (replace the old dark tokens in `tailwind.config.ts` + `globals.css`)

| Token (CSS var) | Value | Tailwind |
|---|---|---|
| `--background` | `#FAFAF8` | `bg-background` |
| `--foreground` | `#1A1A1A` | `text-foreground` |
| `--muted` | `#F5F3F0` | `bg-muted` |
| `--muted-foreground` | `#6B6B6B` | `text-muted-foreground` |
| `--accent` | `#B8860B` | `text-accent` / `bg-accent` |
| `--accent-secondary` | `#D4A84B` | hover gradients |
| `--border` | `#E8E4DF` | `border-border` |
| `--card` | `#FFFFFF` | `bg-card` |
| `--ring` | `#B8860B` | focus rings |

Fonts → `fontFamily: { display:["var(--font-display)"], body:["var(--font-body)"], mono:["var(--font-mono)"] }`.

Shadows → `sm: 0 1px 2px rgba(26,26,26,.04)`, `md: 0 4px 12px rgba(26,26,26,.06)`,
`lg: 0 8px 24px rgba(26,26,26,.08)`. Radii → cards `rounded-lg` (8px), buttons/inputs
`rounded-md` (6px).

### 11.3 Component inventory (baseline only)

- **`SectionLabel`** — the rule-line + small-caps monospace label (gold), used above each
  region. This is the signature; build it first.
- **`JobCard`** — white card, 1px border, optional 2px gold top-accent, `shadow-sm`.
  - Title: Playfair Display, `text-xl`, semibold.
  - Company + location: Source Sans 3, `text-muted-foreground`.
  - Department / type / "New": small-caps mono tags.
  - Hover: shadow → `md`, border → accent-ish, **no lift** (restraint per the system).
  - Whole card links to detail; explicit "Apply →" ghost button links out to `apply_url`.
- **`FilterBar`** — inputs `h-12`, transparent bg, focus `ring-2 ring-accent ring-offset-2`.
  Company/department/location/type selects + a search field + a "New since last run" toggle.
  On mobile, collapse into a **shadcn Sheet** drawer.
- **`Pagination`** — ghost buttons, mono page numbers.
- **Landing `/`** — Serif hero: oversized Playfair headline (`text-7xl`, tight leading),
  one-line value prop, a live `GET /meta` stat ("12,480 open roles across 50 companies,
  updated every 48 hours") rendered as a large serif display number, single gold primary CTA
  → `/jobs`. Generous `py-32`+ spacing. Subtle paper-noise overlay at low opacity + one
  ambient blurred gold glow (2% opacity) for warmth. No carousels, no stock gradients.

### 11.4 Quality floor
Responsive to mobile (cards stack, filters → Sheet), visible keyboard focus on every
control, `prefers-reduced-motion` respected, 44px min touch targets, semantic headings,
`apply_url` links carry `rel="noopener noreferrer"`.

---

## 12. Build order (do these in sequence)

1. **DB + models + migrations** — `companies`, `jobs`, `ingest_runs`. Seed `companies` from
   `companies.seed.json`.
2. **Adapter contract + Greenhouse adapter** — get Stripe's jobs into the DB end-to-end for
   *one* company. This proves the whole spine.
3. **Lever + Ashby adapters** — same contract, two more files.
4. **Normalizer + exact dedup** — unified shape, `dedup_key`, HTML stripping.
5. **Runner** — async fan-out, fault isolation, upsert, closed-role detection, `ingest_runs`.
6. **Verify the registry** — run once; check `failures[]`; fix/disable bad slugs. (This *is*
   building the registry — slugs/ATS in the seed are best-guess and need this pass.)
7. **Read API** — `/jobs` with filters, `/jobs/{id}`, `/companies`, `/meta`.
8. **Frontend tokens + fonts** — swap dark tokens for Serif; build `SectionLabel`.
9. **Feed page** — `JobCard` + `FilterBar`, wired to `/jobs`.
10. **Landing + detail pages.**
11. **Scheduler** — APScheduler 48h + `--once` CLI; docker-compose worker service.
12. **README** — architecture diagram, the adapter-contract explanation, a "killed a slug
    mid-run, here's the failure log and recovery" note. The README is where the systems
    signal lands.

Done = feed shows real, active jobs from every working company in the registry and a
scheduled run refreshes them. **Then** start using it for your own search. Phase 2 comes
from wanting features, not from guilt.

---

## 13. Phase 2 (NOT now — listed so the baseline doesn't accidentally pre-build it)

- Onboarding questionnaire → a `profiles` table.
- Recommendations: start **rule-based** (track → title/keyword filter), ship in a day.
  Upgrade to embeddings (`description_text` is already stored) only if rule-based visibly
  underperforms. Don't let "recommendations" stay a vague blob — it's "filter by track"
  until proven otherwise.
- Swipe/Tinder UI over the same feed.
- More ATS adapters (SmartRecruiters, Workable, Recruitee) — same Protocol.
- The self-hosted giants (Google, Meta, Amazon, Apple, Microsoft, NVIDIA/Workday) — harder,
  separate effort, deliberately deferred.

---

## 14. Interview talking points (what this project proves)

- Pluggable **adapter pattern** behind one Protocol; unified schema across heterogeneous
  sources.
- **Concurrent, fault-isolated** ingestion with bounded concurrency, timeouts, retries.
- **Idempotent upserts** + lifecycle tracking (first_seen/last_seen/closed-role detection).
- **Deduplication** across cross-posted listings.
- Clean **read/write separation** (worker writes, API reads).
- Observability via `ingest_runs`.

None of that is "I trained a model and wrapped it in FastAPI" — it's the systems story the
portfolio was missing.
