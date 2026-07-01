# Chronicle — Session Handoff

**Date:** 2026-07-01
**Branch:** `main`
**Status:** Two sessions' work BUILT + LOCALLY VERIFIED. **Nothing pushed. Prod coordinated pass NOT yet run.**

---

## SESSION 2 (2026-07-01) — Autofill extension + registry scaling + company intelligence

Plan file: `~/.claude/plans/chronicle-session-ticklish-owl.md`. All three workstreams built and
locally verified: `pytest` **43 green**, web `tsc --noEmit` clean, extension builds + typechecks.
Dedup fixtures (SIMBA / Databricks) still green.

### A — Browser autofill extension (`extension/`, MV3 + TS, esbuild)
- **Fill-only, never submits** (no `form.submit()`, no submit-button click) — stated in popup + README.
- Backend: `api/app/security.py` (token gen/sha256/verify), `api/app/routers/extension.py`
  (token mgmt via `X-User-Email`; `/extension/me|profile|saved` via `Authorization: Bearer`).
  `POST /extension/saved` **find-or-creates** Company + Job + saved Application; **new companies
  are `active=False`** so they never bypass the verify_and_add gate (ingest runner only iterates
  active companies). Job dedup key uses the same `keying_title`/`dedup_title`/`make_dedup_key`
  helpers as the runner, so a later ingest upserts the same row.
- Migration `api/alembic/versions/d5f2b8c31e40_extension_token_and_profile.py`
  (`down_revision = c4e1a7b90d21`): `users.extension_token_hash`, `profiles.phone`,
  `profiles.work_authorization` — all nullable/additive.
- CORS: `allow_origin_regex=r"chrome-extension://.*"` in `api/app/main.py`.
- Web: `web/src/app/settings/page.tsx` (token generate/copy/revoke + autofill profile fields),
  `web/src/app/api/user/extension-token/route.ts`, Nav "Settings" link, `/settings` in middleware.
- Extension: `extension/src/{background,content/*,popup/*,config/atsMaps.ts,lib/*}`. Adding an ATS =
  one map in `atsMaps.ts` + one branch in `detect.ts`. `npm install && npm run build` → `dist/`.

### E — Registry scaling
- `verify_and_add_companies.py` now takes a **JSON batch path** arg (`load_candidates`), keeps
  `--commit` (default dry-run).
- `api/candidates/batch1.json` — **22 companies, every one probed live and confirmed active**
  (greenhouse 12 / ashby 7 / lever 3), zero seed collisions. Local dry-run confirms the verify
  gate classifies (active / quarantined / skipped) correctly.

### D — Company hiring velocity (stretch)
- `GET /companies/{id}/velocity` in `api/app/routers/jobs.py` (opened/closed per week from
  `first_seen_at`/`last_seen_at`; + active_now, new_this_week, opened/closed last 30d).
- Web: `getCompanyVelocity` in `lib/api.ts`, `web/src/components/HiringVelocity.tsx` (hand-rolled
  monochrome SVG, no chart dep), rendered on the company detail page (progressive — never breaks
  the page if it errors).

**New/changed files (session 2):** new `api/app/security.py`, `api/app/routers/extension.py`,
`api/alembic/versions/d5f2b8c31e40_*.py`, `api/candidates/batch1.json`, `api/tests/test_security.py`,
`web/src/app/settings/page.tsx`, `web/src/app/api/user/extension-token/route.ts`,
`web/src/components/HiringVelocity.tsx`, and the whole `extension/` tree; edits to
`api/app/models.py`, `main.py`, `schemas.py`, `routers/jobs.py`,
`ingest/verify_and_add_companies.py`, `web/src/lib/api.ts`, `web/src/components/Nav.tsx`,
`web/src/middleware.ts`, `web/src/app/companies/[id]/page.tsx`.

---

## SESSION 1 (2026-07-01) — Pre-Scale Fixes + Safe Scaling

Plan file: `~/.claude/plans/chronicle-pre-scale-abundant-sprout.md`.

---

## TL;DR for the next Claude

- Code is done and verified locally: `pytest` 39 green, `tsc --noEmit` clean.
- **Not committed, not pushed.** User controls commit/push timing.
- **The prod pass against Neon has NOT been run.** It must run as ONE coordinated pass behind a FRESH Neon backup branch (checklist at the bottom). Per prod-safety guardrails, do NOT run it autonomously — the user takes the backup branch and runs it.
- One judgment call made without asking: added `\bai\b` to the Data vocab so "Applied AI" (114 rows) → Data instead of Other. Flag if unwanted.

---

## Task 1 — Server-side department normalization (controlled vocabulary)

**Problem:** No `normalize_department()` existed in the backend; raw ATS department stored verbatim. The fragile cleanup lived in the frontend (`formatDepartment` in `web/src/lib/utils.ts`), which rejoined the whole parent→child chain, so cards rendered `SALES - SQUARE OUTSIDE` (internal org segment leaked). Doesn't scale to 1,000 companies each with its own garbage segment.

**Fix:**
- `api/app/ingest/normalize.py` — added `normalize_department(raw) -> str | None`. Strips leading numeric/req codes, keyword-matches an **ordered** controlled vocab (`_DEPT_KEYWORDS`) → 16 categories (Engineering, Product, Design, Data, Sales, Marketing, Finance, Operations, People, Legal, Support, Security, Research, IT, G&A). Order matters: Security before Engineering, Marketing before Product/Sales, Sales's "account executive" before Finance's "accounting". Position-independent so it never emits the trailing org segment. Returns `None` for empty, `"Other"` for no-match.
- `api/app/models.py` — added `department_raw = Column(Text, nullable=True)` on `Job` (preserves untouched original for cheap retuning). `department` now holds the normalized category.
- `api/alembic/versions/c4e1a7b90d21_add_department_raw.py` — NEW migration. `down_revision = "b3d7e9f2a1c5"`. Adds/drops `department_raw`.
- `api/app/ingest/runner.py` — sets `department=normalize_department(raw.department)` + `department_raw=raw.department`.
- `api/app/ingest/backfill_departments.py` — NEW. For each Job: if `department_raw` is null, `department_raw = department`; then `department = normalize_department(department_raw)`. Idempotent, batched commits of 1000. Run: `python -m app.ingest.backfill_departments`.
- `web/src/lib/utils.ts` — `formatDepartment()` reduced to a passthrough (`return raw?.trim() ?? ""`). No re-casing (preserves `G&A`/`IT`), no segment peeling. Removed `DEPT_GROUP_PREFIXES`.

**Local verification:** backfill re-normalized 14871/20070 rows → 16 clean facets + Other (~21%). `20213 S&M - Sales - Square Outside` → `Sales` with `department_raw` preserved. Zero "square" leaks.

---

## Task 2 — Fix confirmed dedup over-collapse (NOT conditional)

**Confirmed on prod:** 62 divergent groups / 422. Databricks = four genuinely distinct reqs (`Staff Software Engineer (Data Platform)`, `(Money)`, `(Compute)`, `(Growth)`) merged into ONE card.

**Root cause:** `normalize_title`'s `_REQ_ID_RE` strips ALL trailing parentheticals, discarding the team qualifier before `make_dedup_key` runs.

**Fix (user-confirmed approach — "preserve title qualifier," req-id as tie-breaker only):**
- `api/app/ingest/normalize.py` — added `keying_title()` that preserves the alphabetic team qualifier (`(data platform)` vs `(money)`) while stripping genuine req-id noise (numeric parentheticals, `req#`/`jr`/`ref` suffixes). Location suffix still stripped downstream by existing `dedup_title`.
- `api/app/ingest/runner.py` — dedup path now: `make_dedup_key(company.id, dedup_title(keying_title(raw.title), l_norm))`.
- `api/app/ingest/backfill_dedup.py` — now keys off the **raw title** via `keying_title(job.title)` (NOT `title_normalized`, which is already stripped).
- **Do NOT key on `source_job_id`** — cross-city posts have different req ids, so req-id keying would un-collapse the verified SIMBA win (Skopje+Zagreb).

**Local verification:** backfill_dedup re-keyed 1494 rows. Databricks team reqs split into 4 distinct keys; the real `- Backend` cross-city role stays collapsed (SIMBA preserved). Databricks group locked as a test fixture in `test_dedupe.py`.

---

## Task 3 — Verified bulk company add (build + test only this pass)

**File:** `api/app/ingest/verify_and_add_companies.py` (NEW).
- `Candidate(name, ats, slug, industry)` + `VerifyResult` dataclasses.
- `_verify_one`: skip if already in registry → quarantine on unknown ats / no adapter / exception / 0 jobs → active on ≥1 job. Bounded concurrency (`Semaphore(8)`), per-request `timeout=10`, per-company try/except.
- `_persist`: upserts `Company` table (`on_conflict_do_update` on `companies_ats_slug_key`) AND appends to `companies.seed.json` de-duped on `(ats, slug)`. Skips `skipped`/unknown-ats rows.
- `main()` with `--commit` flag (default = dry-run so it never mutates `seed.json` accidentally).

**Local verification (dry-run):** `_SAMPLE` proved all paths — Affirm/greenhouse → active (164 jobs), Stripe → skipped (already seeded), bad slug → quarantined (404), workday → quarantined (unknown ats). `seed.json` left untouched.

**For the real bulk add:** user supplies the candidate list later, then `verify_and_add(candidates)` or run with `--commit`.

---

## Tests

- `api/tests/test_normalize.py` — +8 dept tests (Square Outside→Sales, Eng-Infra→Engineering, Sales-EMEA→Sales, Marketing→Marketing, unknown→Other, Security Engineering→Security, Product Marketing→Marketing, empty→None).
- `api/tests/test_dedupe.py` — +4 tests using the Databricks fixture (4 reqs→4 keys, same-qualified cross-post→1 key, numeric req-id stripped, `keying_title` preserves alpha qualifier). Plus existing SIMBA cross-city collapse test still green.
- **`pytest` 39 green, `tsc --noEmit` clean.**

---

## Files changed this session

**Modified:** `api/app/ingest/normalize.py`, `api/app/ingest/runner.py`, `api/app/ingest/backfill_dedup.py`, `api/app/models.py`, `api/tests/test_dedupe.py`, `api/tests/test_normalize.py`, `web/src/lib/utils.ts`
**New:** `api/alembic/versions/c4e1a7b90d21_add_department_raw.py`, `api/app/ingest/backfill_departments.py`, `api/app/ingest/verify_and_add_companies.py`

---

## ⚠️ REMAINING WORK — Prod coordinated pass (user's to execute)

Both sessions re-key/backfill or grow prod data. Run as ONE coordinated pass behind a FRESH Neon
backup branch. Per prod-safety guardrails: do NOT run autonomously; the user takes the backup
branch and runs it. `alembic upgrade head` now applies BOTH new migrations
(`c4e1a7b90d21` department_raw + `d5f2b8c31e40` extension token/profile). All commands run from
`api/` with the Neon pooled URL explicit.

```
# 0. Take a FRESH Neon backup branch first (covers the whole window)

# 1. Migrate (department_raw + extension token/profile columns)
DATABASE_URL='<neon_pooled_url>' alembic upgrade head

# 2. Session-1 backfills, in order
DATABASE_URL='<neon_pooled_url>' python -m app.ingest.backfill_departments
DATABASE_URL='<neon_pooled_url>' python -m app.ingest.backfill_dedup

# 3. Session-2 registry scaling — verify-and-add the batch, then ingest the new companies
DATABASE_URL='<neon_pooled_url>' python -m app.ingest.verify_and_add_companies candidates/batch1.json --commit
DATABASE_URL='<neon_pooled_url>' python -m app.ingest.schedule --once

# 4. Verify ONCE on the DEPLOYED URL (not localhost):
#    - departments clean, no "Square Outside", clean facets
#    - four Databricks "Staff Software Engineer (<team>)" reqs = 4 cards
#    - SIMBA cross-city still collapsed to 1
#    - company count rose (~201 → ~223); verify_and_add report sane (active/quarantined/skipped)
#    - a company detail page shows the Hiring Velocity chart
```

Code changes deploy via the normal flow (Vercel/Render auto-deploy on push, pages lag 5–60min on
revalidate cache). Migrations + backfills + verify-and-add + ingest are the manual Neon steps.
The extension is loaded unpacked from `extension/dist` (see `extension/README.md`) and pointed at
the deployed API URL with a token from the web **Settings** page.

## Deferred (not this pass)

AI/ML chip relabel, job-detail whitespace, employment-type formatting, redundant REMOTE/NEW filter controls, alert double-opt-in.
