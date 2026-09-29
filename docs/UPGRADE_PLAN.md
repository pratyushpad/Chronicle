# Chronicle upgrade plan (Sept 2026)

Goal: make Chronicle the most useful, best-looking internship and early-career board a student
can open. Every role reads clearly, every fact on the page is true, and the site feels fast and
deliberate on a phone. The backlog comes from an audit of the code and the live site on
2026-09-25; every finding is re-verified before it is fixed.

This file is the plan of record: what each PR touches, its risk, and how it is verified.

## Ground rules

- `main` deploys production (Vercel + Render). Work lands as one stacked branch and PR per
  workstream (`upgrade/pr1-…` … `upgrade/pr8-…`); the maintainer merges.
- Neon is production. No migration, backfill or delete is ever run against it from this work.
  Each PR that needs one ships the migration tested on a local replica plus an exact runbook.
- Render has 512 MB. Ingest stays streaming, embed batches stay small, no DB connection is
  held across ONNX inference, and formatting-only changes never trigger re-embeds.
- Dedup invariants stay green (SIMBA collapses to one; Databricks variants stay split).
- Never invent data: unknown pay, dates or eligibility stay unknown. Every number on the site
  or in the README comes from `/meta`, the database, or a reproducible doc in `docs/`.
- Public, unauthenticated endpoints only; robots.txt and rate limits respected.
- No regressions: Google sign-in, the tracker, saved roles, For You, onboarding, settings and
  resume upload keep working.

## Facts that shaped the design

- **Storage is the binding constraint.** Neon's free tier caps storage at 0.5 GB, and a
  `description_html` column was already dropped once (`e3c4d5f6a7b8`) because raw HTML doubled
  TOAST size. Structured descriptions therefore replace the stored text in place instead of
  adding a second copy.
- **`content_hash` covered derived fields** (normalized department, tags, normalized
  location). Retuning a normalizer changed hashes, nulled embeddings, and dropped rows out of
  semantic search and For You until Render re-embedded them.
- **The pre-2026 cutoff read `posted_at`.** Switching Greenhouse to a first-published date
  without decoupling would silently drop evergreen roles.
- **Today's `strip_html`** keeps `<script>`/`<style>` text and splits text at inline tags, so
  `$150,<strong>000</strong>` became two numbers.
- **Lever descriptions dropped `lists` and `additional`**, which is where requirements, pay and
  sponsorship language usually live.
- **Structured pay was fetched but ignored**: Ashby `compensation`, Lever `salaryRange`, and
  Greenhouse `pay_input_ranges` (available on the list endpoint with `pay_transparency=true`).
- **`npm run lint` could not run** (no ESLint installed) and the web app had no tests.

## Cross-cutting decisions

1. **One text pipeline and content hash v2 (PR 1).** `plain_text(raw_html)` is block-aware,
   joins inline text without inserting spaces, and drops script/style/noscript/template. It
   feeds all extraction and the hash, always from the raw HTML, never from the stored form.
   Hash v2 covers source fields only: raw title, raw department, raw location and the first
   4,000 non-whitespace characters of the description's plain text. It is stored as
   `"v2" + 62 hex` so it can never collide with legacy all-hex hashes. The upsert nulls an
   embedding only when the stored and new hashes share a version and differ; a legacy hash is
   upgraded in place and keeps its embedding. Normalizer retunes and description reformatting
   therefore never re-embed, and no hash backfill or deploy ordering is needed.
2. **Descriptions stored in place as a sanitized HTML subset (PR 2):** `p, ul, ol, li, h2–h4,
   strong, em, a[href http/https/mailto], br`, emitted by an allowlisting walker that escapes
   all text. Output always starts with a block tag, which is the format marker; anything else
   is legacy plain text and is escaped, never parsed. The API returns typed blocks, so the web
   renders React elements without `dangerouslySetInnerHTML`.
3. **Dates.** Adapters report `updated_at` (used only for the pre-2026 cutoff) and a
   first-published `posted_at` (NULL when the ATS has none). One age expression is used
   everywhere: `LEAST(posted_at, first_seen_at)`. The UI says "Posted" only for a real publish
   date, otherwise "First seen", and shows "verified … ago" from `last_seen_at`.
4. **Backward-compatible API.** New response fields are additive; the web degrades cleanly
   against the current API, which is what Vercel previews talk to until a PR merges.
5. **Neon safety guard.** Alembic and backfill scripts refuse any database host other than
   localhost unless `CHRONICLE_ALLOW_REMOTE_DB=1` is set. Migrations set `lock_timeout`.
6. **Database-backed tests run in CI** (pgvector service) from PR 1 on.

## The PRs

| PR | Branch | Touches | Risk | Neon step |
|---|---|---|---|---|
| 1 Correctness | `upgrade/pr1-correctness` | pay parsing + structured pay, department vocabulary + title fallback, first-published dates, text pipeline + hash v2, Lever content, `/meta` freshness, honest copy, mobile nav, ESLint + vitest | high (ingest + schema) | migration + backfill |
| 2 Job pages | `upgrade/pr2-job-pages` | sanitized descriptions, detail layout, sticky Apply, similar roles, metadata, OG images, JSON-LD, sitemap, robots, loading skeletons | medium (ingest path) | none |
| 3 Design | `upgrade/pr3-design` | type, borders, color, dark mode, motion, landing, feed, companies, canonical industries, hiring velocity | medium (large visual diff) | none |
| 4 Student filters | `upgrade/pr4-student-filters` | term/year, degree, citizenship vs US-person (ITAR) vs clearance, workplace, country; labeled eval set; filters + defaults | medium | migration |
| 5 Coverage | `upgrade/pr5-coverage` | Workday adapter (built, disabled by default), Workable adapter, source evaluation | medium | migration |
| 6 Quality gates | `upgrade/pr6-quality-gates` | web CI (Playwright, axe, Lighthouse), typed API fields, alert gating + fixes | low | none |
| 7 Refresh | `upgrade/pr7-refresh` | cheaper upsert, ingest on GitHub Actions (dispatch-only), atomic run lock, status page, prod benchmark (shipped: status page and benchmark; the upsert, the Actions ingest and the run lock landed in main via #10-#12 instead, with no migration) | medium (touches prod ingest) | none (as shipped) |
| 8 Docs | `upgrade/pr8-docs` | README and handoff notes match the code; every metric traces to `docs/` | low | none |

### PR 1 — Correctness the user can see

- **Pay.** Structured sources first (Ashby `summaryComponents` of type Salary with their
  interval, Lever `salaryRange`, Greenhouse `pay_input_ranges`), then a text parser over the
  plain text: ranges and single values, K suffix, en/em dashes and "to", currency symbols and
  codes, explicit period cues. The period is inferred from magnitude only when unambiguous
  (every amount between 10 and 300 means hourly); otherwise it stays unknown and is not shown.
  New columns `pay_min`, `pay_max`, `pay_currency`, `pay_period`, `pay_source`; `salary_min/max`
  become annualized values used only for sorting. Cards show "$45 to 55/hr".
- **Department.** Generic raw values (Internships, Early Career, University Recruiting,
  "Pipeline (N/A)", empty) fall through to ATS hints (Greenhouse metadata, Ashby team, Lever
  department) and then to the title. New categories: ML & AI, Infrastructure, Hardware, Robotics
  & Autonomy, Quality, Manufacturing. "Other" never renders as a chip.
- **Dates.** Greenhouse `first_published`, Lever `createdAt`, Ashby `publishedAt`; relative
  ages and a "verified … ago" line.
- **Freshness copy** matches reality and is computed from `/meta`.
- **Mobile.** Nav collapses into a sheet; every overflow found at 360/390/414 px is fixed.
- **Verification.** Fixture tests from live payloads; a replayed local ingest proves the hash
  transition (re-embed count reported); a 512 MB container run; backfill dry run on the replica.

### PR 2 — Job pages people can read

At-a-glance panel, sticky Apply (right rail on desktop, bottom bar on mobile), structured
description, similar roles from pgvector (active only, streamed so it never holds up the page),
more at the company. Closed roles are marked closed and not indexed. `generateMetadata`, OG
images, JSON-LD with only known fields (omitted when the posting date is unknown), sitemap and
robots, and loading skeletons for the four main routes.

### PR 3 — Design pass

Playfair for display and job titles only, a sans for UI chrome, no text under 11px. Hairline
borders; the heavy left bar only marks state. Monochrome plus three semantic state tones checked
for WCAG AA in both themes. Dark mode through tokens, following the system setting with a
toggle. No curtain between feed and detail. Landing puts search and live stats in the first
viewport. The feed gets one search bar, four primary filters plus a drawer, a sort (newest,
relevance, pay) and a compact density. Companies get search, sort, pagination and about 20
canonical industries. The hiring-velocity chart excludes first-ingest artifacts and explains
its method.

### PR 4 — Student filters

Rule-based extraction of term and year, degree level and graduation window, US citizenship
required, US-person (ITAR/EAR) required, clearance required, workplace type and country, from the
full raw text at ingest. A labeled set of about 200 real postings (two independent labelers,
adjudicated, split into dev and held-out) measures precision and recall per field in
`docs/extraction_eval.md`. A field reaches the UI only at ≥0.9 held-out precision with enough
positives to mean something. The internship view hides MS/PhD-only and citizenship- or
clearance-required roles by default, behind visible toggles.

### PR 5 — Coverage

Workday: robots.txt allows the job-site API, but Workday's site terms may prohibit automated
access, so the adapter is built and tested but ships with no active tenants; enabling the
verified tenants is one command once the terms question is settled. SmartRecruiters: its API
robots.txt blocks all crawlers except LinkedInBot, so it is not built. Workable: public
endpoints, robots.txt allows them, no scraping clause; built and enabled through the verify
gate, with a takedown contact published. Details in `docs/sources.md`.

### PR 6 — Quality gates

Web CI job: type check, lint, build, unit tests, Playwright smoke (home, feed, job detail,
companies, company detail, mobile nav at 390 px), axe, and a Lighthouse budget on the feed
(LCP ≤ 2.5 s, CLS ≤ 0.1). *As built (PR 6): CI enforces CLS ≤ 0.1 and LCP ≤ 3.5 s as a
regression guard and reports the 2.5 s goal, which the feed does not meet yet (2.74–3.02 s
locally, median of 3, simulated mobile throttling).* The remaining `as any` casts go. Email alert controls and claims are
hidden until `RESEND_API_KEY` is configured; alert emails get escaping and a lighter query.

### PR 7 — Faster, honest refresh

First make re-ingest cheap (unchanged rows no longer rewrite their TOASTed description). Then
run ingest on GitHub Actions (free for public repos) with a dispatch-only workflow, an atomic run
lock, and a budget report against Neon's free limits (100 CU-hours a month; running out suspends
the database). The schedule is enabled only with the maintainer's go-ahead. A public `/status`
page shows recent runs, failing boards and freshness. The production search benchmark runs on
the Render box through a protected endpoint. *As built: the status page and the benchmark shipped
in the combined PR 3-8. The cheaper upsert, the Actions ingest (scheduled twice a day, on
once the `NEON_DATABASE_URL` secret exists) and the run lock (an open run younger than two
hours blocks a new one, `app/ingest/runlock.py`) landed in main through #10-#12, with no
migration, so PR 7's versions were dropped.*

### PR 8 — Docs

README and handoff notes match the code (company count, ingest schedule, new fields, removed
extension). Every README metric links to a file in `docs/`.

## How every PR is verified

- `pytest` green, including database-backed tests.
- `npx tsc --noEmit`, `npm run lint`, `npm run build` clean in `web/`.
- Before and after screenshots at 1440 px and 390 px (headless), committed under
  `docs/screenshots/upgrade/`.
- No horizontal scroll at 360, 390 or 414 px on any touched route.
- New or changed logic ships with tests; extraction and parsing use real posting text saved as
  fixtures.
- An independent review of the PR diff before it opens.

## Neon runbook (maintainer)

When merging a PR that carries a migration:

1. Pause ingest (`gh workflow disable ingest` and any external trigger) and confirm no run is
   open: `SELECT id, started_at FROM ingest_runs WHERE finished_at IS NULL;`
2. Take a Neon backup branch.
3. `cd api && CHRONICLE_ALLOW_REMOTE_DB=1 DATABASE_URL=<neon> python -m alembic upgrade head`
4. Run the PR's backfill if it has one: dry run first, then `--apply`.
5. Merge (merge commit), delete the branch, wait for both deploys.
6. Re-enable ingest and watch the next run.

Rollback: revert the merge. Migrations are additive, so older code runs on the newer schema.
Keep ingest paused until the revert deploys.

## Metrics reported at the end

| Metric | Before | After |
|---|---|---|
| Pay accuracy on intern roles | old parser on a labeled intern set | new parser, same set |
| Share of roles in "Other" | 50.8% of 500 sampled intern roles (live API, 2026-09-25) | same measure after the fix |
| Mobile overflow (360/390/414 px) | nav renders 439 px wide at 390 px | measured per route |
| Lighthouse (feed, mobile) | production, median of 3 | preview, median of 3 |
| Full-refresh cycle time | ~4–5 days (600 s runs, ~65 boards each) | measured after the Actions schedule is enabled |
