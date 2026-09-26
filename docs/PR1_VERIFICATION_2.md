# PR 1 verification report — second, independent verifier

**Status: complete (2026-09-26).** Filled in by the second, independent verifying Claude agent. It lives on branch
`upgrade/pr1-verification-2`, which is based on `upgrade/pr1-correctness`
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
- Only edit this file, then commit it and push it to `upgrade/pr1-verification-2`. If the
  environment refuses that branch, use `claude/pr1-verification-2` and say so.
- Mark each claim **verified** (with the command or evidence), **not verified** (with the
  reason) or **wrong** (with a file:line and a reproduction).

## 1. The product goal, and where PR 1 fits

Chronicle is an internship and early-career job board that pulls live postings from ~600
companies' ATS boards (Greenhouse, Lever, Ashby). The upgrade plan's goal is that a student
opening it on a phone sees roles that read clearly and where **every fact shown is true**: pay as
the posting states it, a real department, an honest date, honest freshness claims.

PR 1 ("Correctness the user can see") is the foundation of the 8-PR plan. It fixes the facts
(pay, department, dates, freshness copy), makes the site usable at phone width, and lays the
plumbing the later PRs depend on: one `plain_text` pipeline, a content hash (v2) that only
changes when the source posting changes (so PR 2's description reformatting re-embeds nothing),
a guard that keeps alembic and backfills off Neon unless you opt in, and DB-backed tests in CI.
It is the only high-risk PR in the plan, because it changes ingest and the schema.

## 2. What PR 1 claims to do

| # | Claim | Result |
|---|---|---|
| 1 | Hourly pay no longer ×1000; stored as posted (`pay_min/max/currency/period/source`), `salary_min/max` = annualized USD only | **verified**. `resolve_pay` on fixtures and my own sentences; `annual_usd` returns None for non-USD (L4 GBP row below) |
| 2 | Structured ATS pay first (Ashby `compensation`, Lever `salaryRange`, Greenhouse `pay_input_ranges` via `&pay_transparency=true`) | **verified**. Code (`adapters/*.parse`, `greenhouse.py:12`); fixture output shows `source=ats` for Datadog, Rocket Lab and Hermeus |
| 3 | Period only from evidence; never guesses | **mostly verified**. Mid-range amounts with no cue ($800, $5,000–8,000) → nothing. **One exception**: an unlabeled range where both ends are ≥ $20k is treated as a salary (finding M1) |
| 4 | Pay eval: 3/80 → 77/80 stated, 0/65 → 62/65 hourly, 0/39 invented | **verified**. Both `scripts.eval_pay` and my own separate scorer give 77/80, 62/65, 117/120 and 0/39 |
| 5 | Departments: program labels fall through to title/ATS hints; new categories; "Other" never rendered | **verified** (tests; backfill run moved "Other" → "Engineering"; `displayDepartment` hides "Other"; seeded feed shows Hardware, Robotics & Autonomy, Manufacturing) |
| 6 | Greenhouse `posted_at` = `first_published`; pre-2026 cutoff still reads `updated_at`; age = `LEAST(posted_at, first_seen_at)` | **verified** (`greenhouse.py` parse, `runner.py` freshness line, `JOB_AGE` in `routers/jobs.py`, `test_age_is_least...` passes on real PG) |
| 7 | Hash v2 = source fields only; legacy hash adopted without re-embedding; v2↔v2 change nulls embedding; whitespace-only edits don't | **verified** on local PG (section 3, C) |
| 8 | Backfill: dry run writes nothing, terminates, skips v2 rows, never touches hash/embedding, never clears pay, fixes hourly pay, nulls GH posted_at, safe to re-run | **verified** (section 3, C) |
| 9 | Alembic/backfill refuse non-local hosts unless `CHRONICLE_ALLOW_REMOTE_DB=1` | **verified** for normal URLs; can be bypassed with a crafted `?host=` query parameter (finding L1) |
| 10 | Migration: 5 nullable columns, catalog-only, `lock_timeout` 5s, reversible | **verified** (upgrade → downgrade → upgrade on local PG16) |
| 11 | `/jobs/{id}` returns pay/tags/sponsorship | **verified** (local API: `pay_min 29, pay_period hour, tech_tags ['python']`) |
| 12 | Alert emails render pay as posted; `html` shadowing crash fixed | **verified** (code + `test_alert_email.py`) |
| 13 | Honest freshness copy from `/meta.freshness` with a number-free fallback | **verified** (code: `_freshness`, `boardsRechecked` returns null when the block is absent/inconsistent) |
| 14 | Mobile: nav in a sheet, 0 overflow at 360/390/414; reduced motion shows all cards | **verified locally** (headless Chromium against a local build + local API; the Vercel preview was unreachable from this sandbox). The PR text says the nav collapses "below `md`" but the code uses `lg` (cosmetic doc mismatch) |
| 15 | ESLint + vitest; tsc/lint/test/build clean | **verified** |
| 16 | DB-backed tests in CI (pgvector service) | **verified** (`ci.yml`; `api-tests` check green on head `b5b73dd`; locally 368 passed, 0 skipped with a DB) |
| 17 | Replica numbers (516 intern postings with pay, "Other" 48.2% → 3.8%, 0 embeddings nulled over 45,233 rows) | **not verified**: the replica isn't available to me. The mechanism behind "0 nulled" is verified in (7) |
| 18 | `docs/pay_eval.md`: "two PsiQuantum postings express pay as a rate table **without currency symbols**" | **partly wrong**. The Australian one has no symbols, but the US one does (`$27.50`, `$31.00` …); it's missed because the table layout separates amounts from the "Hourly Rate" header. Either way nothing is shown, so no wrong pay |

## 3. Checks run (command → result)

Environment: Python 3.12.3 venv, local Postgres 16 plus `postgresql-16-pgvector`, Node 22. Never pointed at a remote DB.

**A. API tests**
- `pip install -e '.[dev]'` → ok
- `python -m pytest tests/ -q` (no DB) → **360 passed, 8 skipped**
- `DATABASE_URL=<local> python -m alembic upgrade head` → ok; `downgrade -1` then `upgrade head` → ok (migration reversible)
- `TEST_DATABASE_URL=<local> python -m pytest tests/ -q -rs` → **368 passed, 0 skipped**
- GitHub `api-tests` check on head `b5b73dd` → success

**B. End-to-end pay**
- My own scorer: `Adapter.parse(raw)` → `resolve_pay(raw.pay, plain_text(raw.description_html))` over all 120 labeled postings → stated pay correct **77/80**, no-pay postings **39/39 show nothing**, unclear-period posting shows nothing. The misses are Cresta Toronto ("$30–$50 per hour", labeled CAD, shown USD) and two PsiQuantum rate tables (shown: nothing).
- Samples compared with the posting: Datadog "$100,000—$110,000 USD" → `$100k to 110k/yr` (ats); Zipline "The hourly rate … is $40 per hour" → `$40/hr`; Palantir "$10,500/month" → `$10,500/mo`; Hermeus Lever salaryRange 25–33 per-hour → `$25 to 33/hr` (ats); Rocket Lab "$60,008 CAD" → `CA$60k/yr` (ats); Varda "Hourly Rate: $33.00" → `$33/hr`.
- `python -m scripts.eval_pay --details` → same table as `docs/pay_eval.md` (3/80 → 77/80; 0/65 → 62/65; 43/120 → 117/120; 0/39 invented).
- 51 adversarial sentences of my own. **No pay** for: 401(k) match, $150 wellness stipend, OTE (two forms), $40k RSUs, "Equity: $100k–250k annually", "deals from $50,000 to $500,000", housing stipend, learning stipend, $120M raised, $2B processed, $50 gift card, $200 a night, ¥ with no cue, "30 - 45 engineers", $99/month product price, tuition reimbursement, signing bonus, relocation, prizes, donations, training budget, $4.5B valuation, "2020-2024 … 50,000-100,000 users", cost-of-living adjustment, commissions, per diem, grants, tuition assistance, "$5,000–8,000" (ambiguous), "$800" (ambiguous). **Correct pay** for: split HTML `$150,<strong>000</strong>` (script text ignored) → 150k–180k/yr, €45.000–55.000/yr, £18.50/hr, ₹6,00,000–8,00,000/yr, "$45 - $55 per hour", "Monthly stipend: $8,000", "Salary Range $30 — $45 USD" → hourly, "Base salary … Commission OTE …" → base only, "Hourly: $40 to $45. Relocation: $5,000." → $40–45/hr. **Invented pay** (finding M1): "Average contract value $120k–$300k", "Customers range from $20,000 to $100,000 in annual contract value", "portfolio of $50,000 - $200,000 accounts", "small business loans of $25,000 - $500,000", "Home prices … $300,000 to $600,000", "Our average ticket size is $40k-$80k", "save $30,000 - $50,000 per year on cloud bills", "Scholarship: $20,000 - $30,000", "50,000 - 100,000 USD accounts" → all shown as /yr salaries. "Customers pay $15 - $30 per hour for our service" and "$25 per hour of volunteer time donated" → shown as /hr.

**C. Backfill and upsert on local PG** (`/tmp` script, committed DB, not hermetic)
- Seeded 7 rows: legacy all-hex hashes plus embeddings, GH `posted_at`, hourly pay stored ×1000, a "$50M raised / $500K deals" row with legacy `salary_min=50000`, a GBP hourly row, a row with a v2 hash plus ATS pay, and a Lever row with a NULL hash.
- `run(apply=False, batch=2)` → stats `scanned 6, dept_changed 6, pay_set 4, gh_posted_at_nulled 5`; **nothing written** (checked).
- `run(apply=True, batch=2)` → terminated in 0.03 s. Hourly rows fixed (`$25–35/hr` → salary_min 52,000; `$30–45/hr` → 62,400). GBP → `pay_*` set, `salary_*` NULL. The v2 row was **skipped** (kept its ATS pay 40–50, department and posted_at). The Lever row kept `posted_at`. The $50M row kept its legacy `salary_min=50000` ("never clears"; the new web doesn't display it, see L3). **content_hash and embedding unchanged on every row.**
- Re-run → `dept_changed 0, pay_set 0, gh_posted_at_nulled 0` (idempotent).
- `runner._ingest_company` with a fake adapter:
  - pass 1: legacy rows → v2 hash, **embedding kept**, including one whose text had really changed (the documented trade-off). The row that already had a different v2 hash → embedding **nulled** (correct).
  - pass 2 (identical data) → nothing nulled.
  - pass 3 (one v2 row's pay edited) → only that row nulled.
  - pass 4 (whitespace-only edit) → kept.

**D. dbguard**
- `DATABASE_URL=postgresql://u:p@ep-fake-123.us-east-2.aws.neon.tech/db alembic current` → "Refusing to run alembic migrations against non-local database host …", exit 1.
- Same with `fake.example.invalid` → refused, exit 1.
- With `CHRONICLE_ALLOW_REMOTE_DB=1` → passes the guard (then fails DNS, as expected).
- `postgresql+psycopg2://u:p@localhost/db?host=fake.example.invalid` → **passes the guard** and psycopg2 connects to `fake.example.invalid` (finding L1).
- `backfill_pr1` runs the same guard at import.

**E. Web**
- `npm ci`; `npx tsc --noEmit` → 0; `npm run lint` → "No ESLint warnings or errors"; `npm test` → 32/32 passed.
- `NEXT_PUBLIC_API_URL=https://folio-dev-lo9x.onrender.com AUTH_SECRET=… npm run build` → success. One webpack warning about `jose` using CompressionStream in the Edge runtime; it comes from a dependency.
- Vercel preview: **not reachable** (the sandbox's egress proxy denied the CONNECT), so it wasn't checked.
- Substitute: rebuilt against a local API (uvicorn over my local DB, seeded by running all 120 fixture postings through the real adapters and `_ingest_company`), `next start`, then headless Chromium at 360/390/414 px × reducedMotion {no-preference, reduce} over `/`, `/jobs`, `/jobs?experience_level=Internship`, `/companies`, `/jobs/<id>`. Results:
  - `scrollWidth == viewport` on every route and width (no horizontal scroll);
  - feed **20/20 cards visible** under both motion settings;
  - the Menu button is visible at 390 and opens a dialog, which closes on Escape;
  - cards show "£22 to 26/hr", "$29/hr", "$42 to 60/hr";
  - the job page shows "$29/hr" and "Verified 3m ago".
- Signed-in views were not checked.
- Reviewed `format.ts`: pure, fixed locale/UTC. A null `pay_period` from the new API shows nothing, never falling back to legacy `salary_*`; the old API → annual figures. It never back-derives hourly.
- Reviewed `Nav.tsx`: one notifications fetch shared by the bell and the sheet; the sheet closes on route change; 44–52 px targets; the popover is capped at `100vw-2rem`.

**F. Diff review**: read `api/` (pay, backfill, runner, dedupe, adapters, alerts, routers, migration, dbguard), `.github/ci.yml`, `web/src/lib/format.ts` and `Nav.tsx`. Findings below.

## 4. Findings (bugs, risks, gaps; most severe first)

No blocking bugs found. In order of severity:

**M1 (medium, not a regression): unlabeled salary-scale ranges are read as a yearly salary, so pay can be invented from company or customer money.**
- Where: `api/app/ingest/pay.py:650-651`. `salary_scale_range` lets any range with both ends ≥ 20,000 count as pay with no pay label or cue. Also, "range" counts as a pay label (`pay.py:400`, `\branges?\b`), and a "per hour"/"per year" cue next to a customer price is accepted (`pay.py:651`).
- Reproduce: `parse_pay_text("Average contract value $120k–$300k.")` → USD 120,000–300,000/yr. Also invented: "Customers range from $20,000 to $100,000 in annual contract value", "portfolio of $50,000 - $200,000 accounts", "loans of $25,000 - $500,000", "Home prices … $300,000 to $600,000", "Our average ticket size is $40k-$80k", "Customers pay $15 - $30 per hour for our service".
- Impact: this breaks "never invent data" for sales, fintech and marketplace postings with no stated pay. It is **not a regression**, because the old parser matched these too, and a real labeled salary still wins over it in `_select`. It didn't show up on the 39 no-pay eval postings (0/39), so production frequency is unmeasured.
- Suggested follow-up: require a label, cue or "salary" for salary-scale ranges too, or add `contract|value|portfolio|accounts|loans?|prices?|ticket|customers?|save` to the exclusions. Then re-run `scripts.eval_pay` to confirm 77/80 holds.

**L1 (low): the Neon guard can be bypassed by a `?host=` query parameter.**
- Where: `api/app/dbguard.py:22-26`. `db_host` reads only the URL's netloc, but libpq/psycopg2 honour `?host=` in the query string.
- Reproduce: `DATABASE_URL='postgresql+psycopg2://u:p@localhost/db?host=fake.example.invalid' python -m alembic current` passes the guard, then psycopg2 tries to resolve `fake.example.invalid`. The same happens with an empty netloc plus `?host=`.
- Impact: needs an unusual URL, so it doesn't normally happen by accident. Fix: also refuse when the query has `host`/`hostaddr` that isn't local.

**L2 (low, documented trade-off): a real content edit that lands in the same ingest as a row's first v2 hash keeps the stale embedding until the next edit.**
- Where: `runner.py` `content_changed` (version-aware compare).
- Reproduce: in my run, pass 1 on row L2 with fully changed text → v2 hash adopted, embedding kept.
- Impact: bounded, and accepted in the code comment. It affects only postings edited between the last pre-merge ingest and the first post-merge ingest.

**L3 (low): the backfill never clears wrong legacy `salary_min/max`.**
- Where: `backfill_pr1.py` "never clears".
- Reproduce: a row whose old parser read "$50M raised" as `salary_min=50000` keeps it.
- Impact: the new web shows nothing, because `formatPay` uses `pay_period` when the key is present and it's NULL. But `salary_min` still drives any pay sort or filter, and old clients, until that board's next ingest rewrites it. Ingest re-derives everything on the next run after merge, so this is transient.

**L4 (low): behaviour changes worth knowing, not bugs.**
- The department filter and alert matching are now exact (`routers/jobs.py`, `alerts.py`). A saved search with a partial department string like "engineer" now matches nothing.
- Roles that used to sit under "Engineering" (ML, infra, hardware) move to the new categories, so the "Engineering" quick filter and existing Engineering alerts show fewer roles.
- The default feed sort now orders by `LEAST(posted_at, first_seen_at)`, which `ix_jobs_posted_at` can't serve. That index didn't serve the `DISTINCT ON (dedup_key)` feed query before either, so I expect no measurable change. Not benchmarked.

**L5 (docs): two small inaccuracies.**
- `docs/pay_eval.md` says both PsiQuantum misses lack currency symbols; the US one has `$` amounts (see claim 18).
- The PR body says the nav collapses "below `md`"; the code uses `lg`.

**Production risk (Render 512 MB / Neon 0.5 GB):**
- Migration: 5 nullable columns, catalog-only, `lock_timeout` 5s. Negligible storage.
- `description_text` stays capped at 20,000 chars. Lever descriptions grow (lists + additional), but under the cap.
- The upsert already rewrote every row each run, so there's no new bloat pattern.
- The backfill runs from the operator's machine (≤ 1,000 rows × ≤ 20 KB per batch), not on Render.
- Ingest memory: `pay_transparency=true` adds small `pay_input_ranges` arrays per job, and `plain_text` is per posting. I don't expect a meaningful change, but I didn't run a 512 MB container test (the plan lists one; I haven't seen its output).
- Runbook ordering: the migration must run before merge, because the new code selects the `pay_*` columns. That is stated correctly.

## 5. Verdict

**Correct and safe to merge after the Neon runbook in the PR description.**

- Every claim I could check held up:
  - pay eval reproduced exactly with an independent scorer;
  - 0 invented pay on the no-pay eval postings;
  - the hash transition keeps embeddings;
  - the backfill terminates, is idempotent and leaves hashes/embeddings alone;
  - the guard blocks normal remote URLs;
  - web builds, lints and tests clean;
  - no overflow and all cards visible under reduced motion at 360/390/414 locally.
- Nothing I found is a regression or a data-loss risk.
- Worth a follow-up PR (not blocking): M1 (salary-scale ranges without a pay label) and L1 (`?host=` guard bypass).
- Follow the runbook exactly: pause ingest, backup branch, migrate, backfill dry run then `--apply`, merge, re-enable ingest.
- *Amended after the comparison in §6:* adopt the first verifier's runbook change (F1): run the backfill `--apply` immediately before merging (or just after deploy), and roll back by restoring the Neon backup branch.
- Not verified by me: the replica-scale numbers, signed-in mobile views, and the live Vercel preview (blocked by the sandbox network).

## 6. Comparison with the first verifier

_Written after sections 1–5 were committed (commit `6c6e392`), from `docs/PR1_VERIFICATION.md` on
`upgrade/pr1-verification` (status: complete, 2026-09-26)._

**Verdicts agree.** Both reports say PR 1 is correct and safe to merge after the Neon
migration and backfill. Report 1 adds one runbook change (its F1), which I re-checked and
accept (below).

**Checks where we agree.** We got the same results independently:
- pytest: 360 passed / 8 skipped without a DB; 368 passed / 0 skipped with one;
- migration round-trip;
- `eval_pay` reproduces `docs/pay_eval.md` exactly (77/80, 62/65, 117/120, 0/39);
- hash v2 adopts legacy hashes and keeps embeddings, and v2↔v2 changes null them;
- the backfill: dry run writes nothing, it terminates, it's idempotent, it skips v2 rows,
  never touches hash/embedding and never clears pay;
- tsc, lint, vitest 32/32 and the build are clean;
- the Vercel preview was unreachable for both of us, so both ran a local build against a local
  API. Both found 0 overflow at 360/390/414 and 20/20 cards visible under reduced motion;
- nav breakpoint is `lg`, not `md` (my L5, their F6).

**Findings we both made, in different words:**
- **Invented pay from non-pay money.** My M1 and their F2 are the same weakness reached two
  ways. Mine: an unlabeled range with both ends ≥ 20k counts as a salary (`pay.py:650`). Theirs:
  an explicit period cue with no label counts as pay (`pay.py:651`, "Customers save $50,000 per
  year"). Both are real; I reproduced cue-only cases too ("Customers pay $15 - $30 per hour").
  Their extra point is also right: an unlabeled false positive can outrank an unlabeled real
  wage, because ties go to the earliest candidate. We rate it the same way: real, not a
  regression for most cases, a follow-up, not a blocker. The fix should cover both paths.
- **Legacy fake salaries survive the backfill** (my L3, their F3). Same finding. Small
  correction to report 1: it says no endpoint filters on `salary_*`, but For You does.
  `recommendations.py:189` drops jobs whose `salary_max` is under the user's salary floor.
  A stale legacy value can therefore still affect For You until that row is re-ingested.
  Still low severity.

**Only in report 1. I re-checked each; all are right:**
- **F1 (medium): the `posted_at` backfill hurts the old code's feed.** Confirmed from the code:
  `main` orders the feed by `Job.posted_at` desc, nulls last (`origin/main:api/app/routers/jobs.py:101`),
  filters `posted_after` on `posted_at` (`:146`), and uses `posted_at` for For You recency
  (`recommendations.py:125`). So once the backfill nulls ~31.7k Greenhouse `posted_at` values,
  every Greenhouse role sinks below all Lever/Ashby roles until the new code deploys. After a
  code-only rollback with ingest paused, that lasts indefinitely. I missed this; it's the most
  important runbook point in either report. **I adopt their fix:** run `--apply` immediately
  before merging, or just after the deploy (the new code handles un-backfilled rows through
  `LEAST(posted_at, first_seen_at)` and NULL `pay_*`), and roll back by restoring the Neon
  backup branch, not by reverting code alone.
- **F4 (low):** the `posted_at` step is one unbatched UPDATE. Confirmed (`backfill_pr1.py`,
  step 3). It's fine with ingest paused.
- **F5 (low, pre-existing):** alert-email HTML interpolates `job.title`, `company_name`,
  `apply_url` and `search.name` unescaped (`alerts.py:51,64,67,71,80`). Confirmed. It isn't
  introduced by this PR, and PR 6 plans it.
- **Neon headroom:** check storage and vacuum after the backfill (~65k dead row versions).
  Reasonable; I hadn't raised it.

**Only in report 2 (this one):**
- **L1 (low):** the dbguard can be bypassed with `?host=` in the URL. Report 1 tested only
  normal URLs. Reproduced above: psycopg2 connects to the query-string host.
- **L2:** a genuine edit coinciding with a row's first v2 ingest keeps the stale embedding. The
  code comment documents this; report 1 mentions the hash trade-offs but not this one.
- **Doc error in `docs/pay_eval.md`:** one of the two PsiQuantum misses *does* have `$` symbols.
- **Exact department matching changes behaviour for saved searches and the Engineering
  filter** (L4).

**Combined verdict:** correct and safe to merge after the Neon runbook, **with report 1's F1
change to the runbook**: apply the backfill right before (or right after) the merge, and roll
back by restoring the Neon backup branch. Follow-ups, not blockers: tighten free-text pay
evidence (M1/F2, both paths), close the `?host=` guard bypass (L1), escape alert emails (F5,
PR 6).
