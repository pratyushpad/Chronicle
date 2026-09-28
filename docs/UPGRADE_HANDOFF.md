# Upgrade handoff: PR 2–8 in a cloud session

## Status (2026-09-28)

PR 1, PR 2 and #9-#12 are merged. #12 moved the scheduled refresh to GitHub Actions: a full
refresh twice a day (04:17 and 16:17 UTC) once the `NEON_DATABASE_URL` repo secret exists,
with its own run lock (`api/app/ingest/runlock.py`). PR 3-8 were combined into one PR
(`upgrade/pr3-8-combined`) on top of that main:

| Part | What shipped | Neon step |
|---|---|---|
| PR 3 Design | light/dark themes, feed and companies redesign, footer | none |
| PR 4 Student filters | term, degree levels, country, workplace, eligibility columns | migration `b7c2e4f6a8d1` (10 nullable columns) **before merge** |
| PR 5 Coverage | sources doc, empty states (Workday/Workable adapters not built) | none |
| PR 6 Quality gates | web CI job, Playwright + axe e2e, Lighthouse budget, alert escaping | none |
| PR 7 Refresh | `/status` page and API, `POST /admin/bench` | none (its run-lock migration and Actions workflow were dropped: #12 supersedes them) |
| PR 8 Docs | README, `metrics.md`, `sources.md`, this file | none |

Rules that main settled and the combined PR keeps: senior and management roles without an
early-career marker are listing-only (no stored description, no embedding); an unchanged
description is kept as stored; company money next to an amount is never pay.

**What that session could not do, and why.** The sandbox's network policy blocked the job
boards, huggingface.co and the Workable/Workday hosts. As a result:

- the replica for PR 2–8 was built from the 119 committed real postings
  (`tools/upgrade/build_fixture_replay.py`), not a fresh recording;
- similar roles were checked locally with stand-in vectors;
- the PR 4 labeled set is 135 postings, not about 200;
- PR 5's adapters are not built.

**Still open, in plan order:**

- PR 4's default hides (citizenship, clearance, MS/PhD-only) wait on a larger labeled set.
  Split it by company.
- The LCP ≤ 2.5 s goal (feed measures about 3.0 s in CI).
- Measure the full-refresh cycle from `/status` once the `NEON_DATABASE_URL` secret is set.
- The Workday and Workable adapters.

All numbers: [`metrics.md`](metrics.md).

PR 1 was built and verified locally (`upgrade/pr1-correctness`, PR #1 — https://github.com/pratyushpad/Chronicle/pull/1). PR 2–8 of
`docs/UPGRADE_PLAN.md` are meant to run in Claude Code on the web (claude.ai/code), so the
maintainer's computer can be off. This file is the complete context for that session.

## Starting the cloud session (maintainer)

1. Open claude.ai/code and choose the `pratyushpad/Chronicle` repository with branch
   `upgrade/pr1-correctness`.
2. Environment network access: allow **full** access, or at least these domains:
   - `boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com` (recording board payloads)
   - `apply.workable.com`, `www.workable.com`, `*.myworkdayjobs.com` (PR 5 fixtures only)
   - `chronicles-weld.vercel.app`, `folio-dev-lo9x.onrender.com` (read-only baseline checks)
   - `huggingface.co` (embedding model download)
   - the package registries (PyPI, npm, `cdn.playwright.dev`)
3. Paste the prompt at the bottom of this file.

## Decisions already made by the maintainer

- **Pushing:** push only `upgrade/prN-*` feature branches and open PRs with `gh`. Never push
  to `main`. PR 2 onward stays a draft until the PR below it merges.
- **Migrations:** "flag it, keep going." Test every migration on a local replica, put the exact
  Neon runbook in the PR body, mark it "run migration before merge", then continue with the next
  PR. Never run anything against Neon, and never ask for or hold a Neon URL.
- **Workday (PR 5):** robots.txt allows the job-site API, but Workday's site terms may forbid
  automated access. Build the adapter and fixture tests, but ship it with **zero active
  tenants**. The 10 verified tenants go in `api/candidates/workday_tenants.json`, with a
  one-line enable command in the PR.
- **SmartRecruiters:** its API robots.txt is `User-agent: * / Disallow: /` (only LinkedInBot
  allowed). Not built; document why in `docs/sources.md`.
- **Workable:** public endpoints, robots.txt allows them, no scraping clause. Build it, enable it
  through the verify gate, and publish a takedown contact (a GitHub issues link) in the site
  footer and README.
- **Agents:** run every subagent with `model: "opus"`. Keep usage lean: run one PR at a time,
  and give briefs precise enough that agents don't re-read the whole repo.

## Stop and ask only for

1. Anything that would touch Neon (migrations, backfills). Document it; never run it.
2. Secrets: the Actions secret `NEON_DATABASE_URL` (#12), and for email digests
   `RESEND_API_KEY` both as an Actions secret (the sender) and on Render (`/meta.email_alerts`). Tell the maintainer where to set them; never ask for the
   values in chat.
3. (Done in #12: the Actions refresh is scheduled and turns itself on with the secret.)

## Environment setup inside the cloud session

```bash
# Postgres 16 + pgvector (no Docker needed)
sudo apt-get update && sudo apt-get install -y postgresql-16 postgresql-16-pgvector
sudo service postgresql start
sudo -u postgres psql -c "create role chronicle login superuser password 'chronicle';"
sudo -u postgres createdb -O chronicle chronicle
sudo -u postgres createdb -O chronicle chronicle_test
sudo -u postgres createdb -O chronicle chronicle_dev
export LOCAL_DB=postgresql+psycopg2://chronicle:chronicle@127.0.0.1:5432
# API
cd api && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m app.ml.download
# Web
cd ../web && npm ci
cd ../tools/upgrade/web && npm install && npx playwright install --with-deps chromium
```

Always export `DATABASE_URL` explicitly (`$LOCAL_DB/chronicle...`). `app/dbguard.py` makes
alembic and backfills refuse any non-local host.

**Replica (about 30 minutes):**
1. `alembic upgrade head` on `chronicle`.
2. `python ../tools/upgrade/record_boards.py companies.seed.json /tmp/replay` (about 4 minutes;
   one polite pass).
3. `python ../tools/upgrade/replay_ingest.py /tmp/replay --seed` from `api/` (embeds every
   row).
4. `pg_dump -Fc` the result as the "before" snapshot.

See `tools/upgrade/README.md` for the rest of the harness: replica metrics, screenshots,
overflow audit and Lighthouse.

## Per-PR gate (from the maintainer's brief)

- `pytest` is green, with `TEST_DATABASE_URL=$LOCAL_DB/chronicle_test` set so the
  database-backed tests run.
- `npx tsc --noEmit`, `npm run lint`, `npm test` and `npm run build` are clean in `web/`.
- Before and after screenshots at 1440 px and 390 px, headless, committed under
  `docs/screenshots/upgrade/prN/`.
- No horizontal scroll at 360, 390 or 414 px on touched routes, and `rm_hidden: 0`
  (reduced-motion audit).
- Every fix ships with tests; extraction uses real posting text saved as fixtures.
- An independent code-review subagent reviews the PR diff, and its findings are fixed.
- The PR body covers what changed, how it was verified, before/after numbers, the Neon steps
  and any preview caveats. Vercel previews talk to the production API, so new fields are absent
  there.
- Then send the maintainer a 5-line summary.

## Measured so far (for the final before/after table)

| Metric | Before | After PR 1 | Source |
|---|---|---|---|
| Correct pay, intern postings that state pay | 3/80 (3.8%) | 77/80 (96.2%) | `docs/pay_eval.md` |
| Correct pay, hourly intern postings | 0/65 | 62/65 | `docs/pay_eval.md` |
| Intern roles in Other or unset | 50.8% (500 live, 2026-09-25); 47.6% on the replica | 3.8% on the replica (after backfill + ingest) | `replica_metrics.py`, `scripts/department_report.py` |
| All roles in Other or unset | 24.2% on the replica | 7.6% on the replica | same |
| Mobile overflow (360/390/414 px) | every route 443 px wide (658 px signed in) | 0 (6 routes signed out, 3 signed in, at 360, 390 and 414 px) | tools/upgrade harness |
| Reduced motion: hidden feed cards | 20 of 20 | 0 | harness |
| Lighthouse, feed, mobile (production) | perf 88, LCP 3.75 s, CLS 0 | measured in PR 3 and PR 6 | `lh.mjs` |
| Full-refresh cycle | about 4–5 days (the latest production run covered only 7 boards) | one Actions run per refresh, twice a day (#12), once its secret is set | `ingest-actions.yml`, `/status` |

## Known facts for later PRs

- **Write amplification (PR 7 prerequisite).** Every ingest upsert rewrites each seen row's
  description, even when it's unchanged, and leaves a dead TOAST copy behind. The replica
  grew from 379 MB to 539 MB over four back-to-back full passes while the live description
  data grew only 4.5%. Production already does this, but slowly: about 65 boards per run.
  A 12-hour full refresh would do it about nine times faster, so PR 7 must keep unchanged
  descriptions first (for example `CASE WHEN content changed THEN excluded ELSE jobs.description_text`)
  and measure dead-tuple growth before enabling any schedule.

- **Storage.** The replica is 379 MB for 45k rows: TOAST 204 MB, HNSW index 88 MB, heap 65 MB.
  Neon's cap is 0.5 GB and production is probably closer to it. Measure storage growth in every
  PR that writes more data.
- **Hiring velocity (PR 3).** The Anduril spikes are ingest artifacts. Production opened counts
  were 853 in the week of 2026-06-22, which was the first ingest, then 595 and 607 in re-check
  weeks and 0 in between. The board's own `first_published` dates ramp smoothly from about 20 a
  week to about 230 a week.
- **Dead slugs.** 7 dead Greenhouse/Ashby slugs 404 on every run: marqeta, clickhouse,
  postman, instabase, temporaltechnologies, amplitude, bitso. The PR 7 status page should
  surface them.
- **PR 3 perf lead.** The production feed's LCP of 3.75 s is probably the server-side fetch of
  the full company list for FilterBar, plus the API round-trip.

## Prompt to paste into the cloud session

> Continue the Chronicle upgrade from `docs/UPGRADE_HANDOFF.md` and `docs/UPGRADE_PLAN.md`
> (read both fully, plus the PR 2–8 sections). PR 1 is done. Set up the environment and the
> replica exactly as the handoff says, then build PR 2 → PR 8 in order on stacked branches
> (`upgrade/pr2-job-pages` based on `upgrade/pr1-correctness`, and so on). Follow the ground
> rules, the decisions and the per-PR gate in the handoff. Stop only for the three listed
> reasons. After each PR, give me a 5-line summary; at the end, fill in the before/after table.
