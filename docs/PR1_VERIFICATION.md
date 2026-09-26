# PR 1 verification report

**Status: complete (2026-09-26).** Filled in by an independent verifying Claude agent (scheduled run). It lives on branch
`upgrade/pr1-verification`, which is based on `upgrade/pr1-correctness`
([PR #1](https://github.com/pratyushpad/Chronicle/pull/1)).

## Instructions for the verifying agent (keep this section)

Verify, independently and skeptically, that PR #1 does what it says and that it serves the
product goal. Don't trust the PR description, commit messages or earlier reports; check the
code and run things. Read `docs/UPGRADE_PLAN.md`, `docs/pay_eval.md`, the PR description, and
`git log origin/main..origin/upgrade/pr1-correctness`. Then fill in sections 1–5 below.

**Rules:**
- Never connect to any non-local database. Neon is production.
- Don't merge, close or comment on PRs.
- Don't push to `main` or `upgrade/pr1-correctness`, and don't change application code.
- Only edit this file, then commit it and push it to `upgrade/pr1-verification`. If the
  environment refuses that branch, use `claude/pr1-verification` and say so.
- Mark each claim **verified** (with the command or evidence), **not verified** (with the
  reason) or **wrong** (with a file:line and a reproduction).

## 1. The product goal, and where PR 1 fits

**Goal (from `docs/UPGRADE_PLAN.md`):** make Chronicle the most useful internship and early-career
job board a student can open. Every role should read clearly, every fact on the page should be
true, and the site should feel fast on a phone. Two hard rules: never invent data (unknown pay,
dates or eligibility stay unknown), and never hurt production (Neon's free tier caps storage at
0.5 GB, Render has 512 MB of RAM, and formatting-only changes must never trigger re-embeds).

**PR 1 fixes correctness first.** Before it, the facts a student sees were wrong:
- hourly intern pay was multiplied into fake annual salaries ("$30–45/hr" became "$30k–45k");
- about half of intern roles were filed under "Other" or "People" because the ATS department
  was a program label like "Internships";
- Greenhouse "posted" dates were really last-edited dates;
- the freshness copy promised things the system doesn't do;
- the mobile layout overflowed, and feed cards were invisible under reduced motion.

PR 1 also lays the base the later PRs build on:
- one text pipeline and a version-2 content hash, so PR 2's description reformatting won't
  re-embed anything;
- the Neon safety guard;
- database-backed tests in CI.

It is the only PR in the plan that is high-risk to production, because it changes ingest and
the schema and needs a Neon migration and backfill.

## 2. What PR 1 claims to do

Status key: **verified** = I checked it with the command or evidence shown. **not verified** =
I couldn't check it (reason given). **wrong** = it doesn't hold (details given).

| # | Claim | Status |
|---|---|---|
| C1 | Pay is stored as posted (`pay_min/max/currency/period/source`). Structured ATS pay (Ashby, Lever, Greenhouse `pay_input_ranges`) comes first, then a text parser that assigns a period only from evidence. | **verified**: code read (`pay.py`, adapters, `runner.py`); pay eval and my own sentences in §3 B |
| C2 | Intern pay eval goes from 3/80 to 77/80 correct, hourly from 0/65 to 62/65, with 0/39 invented. | **verified**: re-ran `scripts.eval_pay` and got exactly these numbers (as a development-set result, which is how the doc describes it) |
| C3 | The parser "never guesses" or invents pay. Free-text pay needs a pay label or a period cue. | **partly wrong**: a period cue alone counts as evidence, so non-pay money with a period is read as pay (Finding F2) |
| C4 | `salary_min/max` become annualized, USD-only sort keys. | **verified**: `annual_usd`; the backfill test run showed hourly $30–45 giving 62,400–93,600, and non-USD giving NULL. Note: no API endpoint sorts or filters on them today. |
| C5 | Program labels no longer decide the department. The order is: a specific raw department, then the title, then ATS hints. New categories added. The UI never shows "Other". | **verified**: 33 of my own cases (§3 C); `displayDepartment` hides "Other" |
| C6 | Intern roles in "Other"/unset drop from 48.2% to 3.8% on the replica. | **not verified**: the replica and its recorded boards aren't in this environment |
| C7 | `posted_at` is Greenhouse `first_published`. The pre-2026 cutoff still reads `updated_at`. Age is `LEAST(posted_at, first_seen_at)` everywhere. | **verified**: `greenhouse.py` `parse()`, `runner.py:126-131`, `JOB_AGE` in `jobs.py`; DB test `test_age_is_least_of_posted_and_first_seen` passed |
| C8 | Content hash v2 covers only source fields and ignores formatting. The upsert keeps the embedding for a legacy or NULL hash and nulls it only when two v2 hashes differ. | **verified**: my own script (§3 D) and the DB tests that drive the real `_ingest_company` |
| C9 | The first production ingest after merge re-embeds nothing (replica: 45,233 rows upgraded, 0 nulled). | **mostly verified**: the rule is proven in the DB tests. I couldn't re-run the full replica replay (no recording available here). |
| C10 | The backfill is a dry run by default, batched, never touches `content_hash` or `embedding`, skips v2 rows, never clears pay, can't loop, and is safe to re-run. | **verified**: my own local run (§3 E) plus `test_backfill_pr1`. Nuance: the Greenhouse `posted_at` step is one unbatched UPDATE (F4). |
| C11 | The migration only adds columns (5 nullable ones, catalog-only, `lock_timeout` 5s) and can be reversed. | **verified**: upgrade, downgrade -1 and upgrade again on local Postgres 16 |
| C12 | Alembic and the backfills refuse a non-local database unless `CHRONICLE_ALLOW_REMOTE_DB=1`. | **verified**: both refuse `ep-foo.neon.tech`; a local host passes |
| C13 | Rollback is "revert the merge; the columns are additive so old code runs on the new schema." | **incomplete**: true for the schema, but the backfilled data (NULL Greenhouse `posted_at`) degrades old code's feed (F1) |
| C14 | `/jobs/{id}` now returns pay, tags and sponsorship. There is one `JobListItem` builder. Alert emails show pay as posted. The alert-email crash (a local variable shadowing the `html` module) is fixed. | **verified**: live local API response; code read; `test_alert_email` passed |
| C15 | Department filters (feed and alerts) are exact matches. | **verified**: `jobs.py`, `alerts.py:38` |
| C16 | Freshness copy states what `/meta.freshness` measures, with a number-free fallback. | **verified**: local `/meta` returns the `freshness` block, and the feed shows "2 of 598 company boards re-checked in the last 7 days" |
| C17 | The nav collapses into a sheet on narrow screens, and no route overflows at 360/390/414. | **verified locally**: 0 overflows on 5 routes × 3 widths × 2 motion settings, and the sheet opens and closes with Escape. Note: it collapses below **`lg`**, not `md` as the PR text says (harmless). |
| C18 | Under `prefers-reduced-motion`, feed cards are visible. | **verified locally**: 20/20 visible, screenshot checked |
| C19 | `tsc`, lint, vitest and build are clean. pytest shows 368 passed with DB-backed tests. | **verified**: identical numbers |
| C20 | DB-backed tests run in CI against a pgvector service. | **verified**: `ci.yml` reviewed (it runs the migration, then pytest with `TEST_DATABASE_URL`) |
| C21 | The Vercel preview is reviewable (layout, nav, reduced motion). | **not verified**: the sandbox proxy returns 403 for `*.vercel.app` and `*.onrender.com`. I ran the same checks against a local build instead (§3 F). |

## 3. Checks run (command → result)

Environment: Python 3.12 venv (the project requires 3.12 or later; the first attempt with 3.11
failed to install), Node from the sandbox, local Postgres 16 with `postgresql-16-pgvector`
installed by apt, and headless Chromium 1194.

**A. API tests**
- `cd api && python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/python -m pytest tests/ -q`
  → **360 passed, 8 skipped** (no database).
- Set up the local database: `CREATE DATABASE chron_verify; CREATE EXTENSION vector;` then
  `DATABASE_URL=postgresql+psycopg2://chron:chron@localhost:5432/chron_verify .venv/bin/python -m alembic upgrade head`
  → it migrated to `a1f3c5e7b9d2`.
- `TEST_DATABASE_URL=<same> .venv/bin/python -m pytest tests/ -q -rs` → **368 passed, 0 skipped**.
  This includes the upsert hash-version rule, the backfill, FTS, prune and age ordering.
- Migration round-trip: `alembic downgrade -1` → the `pay_*` columns are gone. `alembic upgrade head`
  → 5 nullable columns come back (`numeric`, `varchar`).
- Guard:
  - `DATABASE_URL=postgresql+psycopg2://u:p@ep-foo.neon.tech/db python -m alembic current` →
    "Refusing to run alembic migrations against non-local database host 'ep-foo.neon.tech'".
  - `python -m app.ingest.backfill_pr1` with the same URL → refused.
  - The same with `127.0.0.1` → the guard passes and it goes on to try the connection.

**B. Pay**
- `.venv/bin/python -m scripts.eval_pay --details` → it matches `docs/pay_eval.md` exactly:
  - 77/80 stated-pay postings correct (3/80 before);
  - 62/65 hourly postings correct;
  - 117/120 overall;
  - 0/39 postings with pay invented.
- The 3 "after" misses are the ones the doc names: Cresta Toronto `$30-$50 per hour` is labeled
  CAD, and two PsiQuantum postings.
- 22 sentences of my own (script `scratchpad/pay_check.py`) → **21/22 as expected**:
  - hourly ranges and single rates, including one with a housing stipend next to it;
  - an annual base with equity;
  - OTE → none;
  - equity only → none;
  - relocation or learning stipend → none;
  - a monthly stipend and a monthly range;
  - GBP per annum;
  - EUR written as `€55.000` with "jährlich";
  - CA$ hourly;
  - `Pay: $25 - $40` → hourly (the magnitude rule);
  - `Pay: $3,000 - $4,000` → none (ambiguous, correctly left out);
  - `$120M Series C` → none;
  - weekly, daily and INR monthly amounts;
  - `150k-180k USD` base;
  - a salary next to a 401(k) match (the salary is kept);
  - wellness and home-office amounts → none.
- The miss: `Customers save $50,000 per year on average` → **$50,000/yr invented**. A follow-up
  probe also got `We handle over $20 per hour of compute` and `The team saves $75 per hour of
  manual work` wrong (both read as hourly pay). It correctly rejected tuition, 401(k), commuter,
  phone and referral amounts, and `$2M per day`. See F2.
- Periods: every accepted case got the right period. Nothing was ever given a period without a
  cue, a label or an unambiguous magnitude.

**C. Departments.** `normalize_department(raw, title, hints)` on 33 cases of my own:
- 29 are what a student would expect. For example:
  - Internships + "Software Engineering Intern, Backend" → Engineering;
  - Early Career + ML Research → ML & AI;
  - Pipeline (N/A) + New Grad SWE → Engineering;
  - Campus + SRE → Infrastructure;
  - Business Development → Sales;
  - Internal Audit → Finance;
  - Technical Recruiter → People;
  - Autonomy Software → Robotics & Autonomy;
  - hint "Robotics" on a bare "Intern" title → Robotics & Autonomy.
- Weak or debatable results (not blocking):
  - "GTM Strategy Intern" → Other;
  - "Solutions Architect, New Grad" → Other;
  - "Research Intern – 3D Vision…, Self-Driving" → Research (I'd expect ML & AI);
  - "Hospitality Intern" → Other (fine).
- A specific raw department always beats the title. So raw "Engineering" with "Recruiting
  Coordinator Intern" gives Engineering. That is by design.

**D. Hash and re-embedding** (script `scratchpad/hash_check.py`, run against the PR code):
- The hash stays the same for: whitespace reflow, `p`→`div` with `strong`→`b`/`em`, `ul`→`ol`,
  added `<script>`/`<style>`, `&nbsp;`, and extra whitespace in the title.
- The hash changes for: a real text edit, or a changed title.
- Edits past 4,000 non-whitespace characters are ignored; edits before that change the hash.
- Known trade-off: `"a b"` and `"ab"` hash the same (whitespace is dropped completely).
- Upsert rule (`runner.py:200-205`):
  - `left(stored,2) = left(new,2) AND stored <> new` → a legacy hex hash (never starts with "v")
    is adopted and keeps its embedding;
  - a NULL stored hash makes the expression NULL, so the embedding is kept;
  - two different v2 hashes → the embedding is nulled.
- `test_upsert_hash_versions` (it drives the real `_ingest_company` against Postgres) passed.

**E. Backfill.** I ran it myself on a fresh local database (`chron_bf`, seed at
`scratchpad/seed.sql`) with 6 legacy-shaped Greenhouse rows, all carrying the same embedding:
- **Dry run** (`--batch 2`): it reported 5 department changes, 3 pay rows and 5 `posted_at`
  clears. A before/after `diff` of the table was **empty**, so the dry run wrote nothing.
- **`--apply --batch 2`** gave:
  - hourly `$30 — $45 USD per hour` → 30–45 USD/hour, with the annual sort key 62,400–93,600;
  - split legacy text `$ 52 , 000 - $ 60 , 000 per year` → repaired to 52k–60k/yr;
  - the v2-hash row was untouched (department "Other", `posted_at` kept);
  - `content_hash` and the embedding md5 were identical on every row;
  - the legacy fake salary from "$50 gift card" (50000) was **not cleared** ("never clears"
    works as designed; see F3);
  - "Customers save $50,000 per year" was **set as pay** (F2 reaches the backfill too).
- **Re-run** → 0 departments, 0 pay and 0 `posted_at` changes (idempotent).
- Termination: keyset pagination with a stall guard (`_batches`). The `or_()` stays
  parenthesized. With a batch size of 2 across 3 passes, the run finished.

**F. Web**
- `npm ci`, then:
  - `npx tsc --noEmit` → exit 0;
  - `npm run lint` → "No ESLint warnings or errors";
  - `npm test` → **32/32 passed**;
  - `NEXT_PUBLIC_API_URL=https://folio-dev-lo9x.onrender.com AUTH_SECRET=verify-local-secret npm run build`
    → exit 0. There are "Compiled with warnings" from `@auth/core`/`next-auth` (Edge runtime
    import traces), which don't come from this PR's code.
- The Vercel preview and the production API were **unreachable** (proxy 403). Instead I ran:
  - the PR's API locally (`uvicorn`, against the backfilled `chron_bf` plus 25 more intern rows);
  - a web build pointed at it (`next start`);
  - a Playwright check (`scratchpad/mobile_check.py`).
- Results:
  - `/`, `/jobs`, `/jobs?experience_level=intern`, `/jobs/1` and `/companies` at 360/390/414,
    each with `reduced_motion` both `reduce` and `no-preference` → **scrollWidth equals the
    viewport width in all 30 cases**;
  - the feed shows 20/20 cards visible;
  - cards read "$45 to 55/hr", and the detail page reads "$30 to 45/hr";
  - the Menu button opens a dialog sheet (Roles/Companies/Tracker) and Escape closes it;
  - I checked the 390px reduced-motion screenshot by eye.
- Code review:
  - `formatPay`: new-API mode is keyed on whether `pay_period` is present. A null period shows
    nothing. Old-API mode shows legacy annual figures and never back-derives an hourly rate.
    Pydantic always serializes `pay_period`, so every PR 1 surface uses new-API mode.
  - `relativeAge`: floors each unit, is pure (the caller passes `now`), and returns null more
    than a day in the future.
  - `jobAge`: shows a posted date only if it is at most 1 day after `first_seen`.
  - `Nav.tsx`: closes on route change, uses the Radix sheet, and has aria labels.

**G. Diff review** (`git diff origin/main...origin/upgrade/pr1-correctness -- api web .github`)
- No secrets. The only credential is the CI service password `chronicle`.
- `ci.yml` interpolates no untrusted `${{ }}`.
- No `dangerouslySetInnerHTML` on the job page.
- The new pay span in alert emails is escaped.
- Pay values are bounded to NUMERIC(12,2) before insert (`_resolve`). `annual_usd` is USD-only
  and bounded (≤ 2M/yr), so the int4 `salary_*` columns can't overflow.
- Greenhouse `pay_transparency=true` rides on the existing list call, so there are no extra
  requests. Ingest stays streaming, and there is no new per-job memory beyond the parsed text.
- Storage: the upsert already rewrites every row on every ingest (it sets `description_text`),
  so the first v2 ingest costs no more than any other run. The backfill touches about 65k row
  versions (13k department + 21k pay + 31.7k `posted_at`, replica figures) on top of that. These
  are heap-only dead tuples, since TOASTed description values are carried over, not copied. That
  is modest, but it lands on a 0.5 GB cap.

## 4. Findings (bugs, risks, gaps; most severe first)

**F1. Medium: the rollback plan and the backfill-to-deploy window hurt old code's feed.**
- **Where:** `api/app/ingest/backfill_pr1.py:142-148` sets `posted_at = NULL` on every legacy
  Greenhouse row (about 31.7k of 45k on the replica). Old code, which is still deployed
  between runbook steps 4 and 5 and is again after a rollback, orders the feed by
  `posted_at DESC NULLS LAST`, filters with `posted_after` on `posted_at`, and uses `posted_at`
  for For You recency. See `origin/main:api/app/routers/jobs.py:101,146,220` and
  `recommendations.py:125-131,188,237`.
- **Effect during the window:** every Greenhouse role sinks below all Lever/Ashby roles, is
  dropped by any "posted after" filter, and gets no recency boost.
- **Effect after a rollback:** the feed stays that way indefinitely. The rollback note says to
  keep ingest paused (correctly, because old code would re-embed every v2-hashed row), so
  nothing refills `posted_at`.
- **Reproduction:** after `backfill_pr1 --apply` on a local DB,
  `SELECT count(*) FROM jobs WHERE source='greenhouse' AND posted_at IS NULL` gives every
  legacy GH row. Then run `main`'s `/jobs?sort=posted_at`, and GH rows appear only after all
  non-GH rows.
- **Fix (runbook only, no code change needed):**
  - keep the window short (apply, then merge immediately), or run the backfill *after* the
    deploy is live (the new code tolerates un-backfilled rows: `JOB_AGE` falls back to
    `first_seen_at`, and the pay columns are just NULL);
  - for rollback, restore from the Neon backup branch rather than only reverting the code, or
    accept the degraded ordering.

**F2. Low–medium: free-text pay can still be invented from non-pay money with a period cue.**
- **Where:** `api/app/ingest/pay.py:644-654` accepts a candidate when `t.cue` is present, even
  with no pay label.
- **Reproduction:**
  `parse_pay_text("Customers save $50,000 per year on average using our product.")` →
  `50000–50000 USD year`.
- **Other false positives:** `"We handle over $20 per hour of compute per GPU."` → $20/hr.
  `"The team saves $75 per hour of manual work."` → $75/hr.
- **Wrong band:** it can even displace the real wage when that wage isn't labeled.
  `"Customers save $50,000 per year… The internship pays $45 per hour."` → $50,000/yr. Ties
  go to the earliest candidate, `_select` at `pay.py:161-167`.
- **Confirmed in the backfill:** it wrote this pay to a row in my local run.
- **Mitigations already there:** a labeled wage wins ("Pay range: $45 - $55 per hour" beats
  it), and the 39 real no-pay postings in the eval had 0 inventions.
- **Suggested follow-up:** require a pay label, or "salary"/"pay"/"wage"/"rate"/"compensation"
  within the sentence, for free-text candidates, and reject verbs like save/process/handle
  before the amount. This contradicts the "never invent data" ground rule, but it is rare in
  intern postings, so it's a follow-up, not a merge blocker.

**F3. Low: legacy fake salaries survive the backfill on rows it can't re-parse.**
- **Where:** `backfill_pr1.py:127-129` never clears. For example, a legacy `salary_min=50000`
  from "$50 gift card" stays, with `pay_*` NULL.
- **Why it's harmless:**
  - the UI doesn't show it (`pay_period` is null, so `formatPay` returns null);
  - no endpoint sorts or filters on `salary_*`;
  - the next ingest overwrites active rows.
- **What remains:** it lingers only on inactive rows and in the legacy API fields.
- **Reproduction:** row 4 in §3 E.

**F4. Low: the `posted_at` step isn't batched.** `backfill_pr1.py:148` is a single UPDATE of
about 31.7k rows, with no `lock_timeout` set. That's acceptable with ingest paused as the
runbook requires, but "batches of 1,000" in the runbook only describes steps 1–2.

**F5. Low (already there before this PR, planned for PR 6): alert-email HTML is not escaped.**
`alerts.py:51,64,67,71,80` interpolate `job.title`, `company_name`, `job.apply_url` and
`search.name` raw. ATS titles are third-party text. PR 1 escapes only its own new pay span.
PR 6 already plans "alert emails get escaping".

**F6. Informational.**
- The nav sheet breakpoint is `lg` (`Nav.tsx:164,375`), not `md` as the PR description says.
- `docs/pay_eval.md`'s numbers are a development set (the doc says so).
- The replica metrics (C6, C9) can't be reproduced without the recording.
- Department misses listed in §3 C.

I found no correctness bug in the hash or upsert rule, the migration, the guard or the web
formatters, and no security regression.

## 5. Verdict

**PR 1 is correct and, with one runbook change, safe to merge after the Neon migration and
backfill.**

What holds up under independent checks:
- the embedding-safe hash transition;
- the additive, reversible migration;
- the dry-run-first, v2-skipping, idempotent backfill that never touches the hash or embedding;
- the local-only guard;
- the pay eval numbers;
- department mapping;
- the mobile and reduced-motion fixes;
- all test suites.

On the failures it targets, the product gets much more truthful.

**Before merging, change the runbook (no code change needed):**
1. **(F1)** Either run `backfill_pr1 --apply` right before the merge and merge immediately, or
   run it just *after* the Render deploy is live. The new code handles un-backfilled rows.
   Also state that a rollback should restore the Neon backup branch (or re-run ingest with the
   new code), because reverting the code alone leaves Greenhouse roles at the bottom of the
   feed.
2. Check Neon storage headroom before the backfill (it adds about 65k heap row versions), and
   let autovacuum run, or `VACUUM jobs`, afterwards.

**Recommended follow-ups (not blocking):**
- F2: tighten free-text evidence so "save/handle $X per year/hour" is never pay.
- F5: alert-email escaping, already scheduled for PR 6.
- F3/F4: cosmetic.
