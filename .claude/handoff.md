# Chronicle — Claude Handoff

## What this app is
Chronicle is a Simplify-style job aggregator that pulls every open role from 201 top tech companies via Greenhouse/Lever/Ashby ATS APIs into one searchable feed. Phase 2 adds Google OAuth, DB-backed tracker/saved jobs, "For You" recommendations, and email alerts.

## Stack
- **Frontend**: Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui → deployed on Vercel at `https://chronicles-weld.vercel.app`
- **Backend**: Python 3.14 + FastAPI (port 8002 locally) → deployed on Render at `https://folio-dev-lo9x.onrender.com`
- **Database**: PostgreSQL — Neon (production) + local PostgreSQL 16
- **Auth**: NextAuth v5 (Google OAuth) — JWT sessions, `X-User-Email` header pattern to FastAPI
- **Email**: Resend (not yet configured — RESEND_API_KEY still a placeholder)

## How to run locally
```bash
# 1. Start Postgres
brew services start postgresql@16

# 2. Start FastAPI
cd api && DATABASE_URL=postgresql+psycopg2://openroles:openroles@localhost:5432/openroles \
  /Library/Frameworks/Python.framework/Versions/3.14/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload

# 3. Start Next.js
cd web && npm run dev   # runs on port 3001

# 4. Run ingest (optional, local DB)
cd api && DATABASE_URL=postgresql+psycopg2://openroles:openroles@localhost:5432/openroles \
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m app.ingest.schedule --once
```

## Auth flow
1. User clicks Sign In → NextAuth Google OAuth
2. On success, Nav calls `POST /api/user/sync` → syncs to FastAPI via `X-User-Email` header
3. All authenticated API routes pass `X-User-Email` to FastAPI; `get_current_user` dep in `users.py` resolves the User row

## Production env vars
**Render** (FastAPI):
- `DATABASE_URL` — Neon connection string (without `channel_binding=require`)
- `AUTH_SECRET`
- `INTERNAL_API_SECRET`

**Vercel** (Next.js):
- `NEXT_PUBLIC_API_URL=https://folio-dev-lo9x.onrender.com`
- `AUTH_URL=https://chronicles-weld.vercel.app`
- `AUTH_SECRET`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `INTERNAL_API_SECRET`

## Key files
| File | Purpose |
|---|---|
| `api/app/routers/jobs.py` | `/jobs`, `/companies`, `/meta` endpoints |
| `api/app/routers/recommendations.py` | "For You" scoring engine |
| `api/app/routers/applications.py` | Tracker state machine |
| `api/app/ingest/runner.py` | ATS fetch + normalize + upsert |
| `api/app/ingest/schedule.py` | `--once` flag for manual runs |
| `web/src/components/JobCard.tsx` | Job card with logo, save, track |
| `web/src/components/FilterBar.tsx` | Quick pills + filter inputs |
| `web/src/app/for-you/page.tsx` | Recommendations page |
| `web/src/app/tracker/page.tsx` | Kanban tracker |
| `web/src/auth.ts` | NextAuth v5 config |
| `web/src/middleware.ts` | Protects `/tracker`, `/saved`, `/for-you`, `/onboarding` |

## DB migrations
```bash
cd api && DATABASE_URL=<neon_url> python3 -m alembic upgrade head
```

## Known issues / TODO
- Render free tier spins down after 15min idle — first request after sleep takes ~50s
- RESEND_API_KEY not set — email alerts won't send until configured at resend.com
- GitHub repo typo: named `Chornicle` instead of `Chronicle`
- Company logos use Clearbit API (`logo.clearbit.com/{domain}`) — may fail for some companies
- Ingest runs manually for now; needs a cron job for automated 48h refresh in production

## Workflow
- Test changes on localhost first, commit + push once when satisfied
- Vercel auto-deploys on push to `main`; Render auto-deploys on push to `main`
- Neon DB is shared between local migrations and production
