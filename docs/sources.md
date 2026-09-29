# Job sources

Chronicle reads each company's own applicant-tracking-system (ATS) board through the
ATS's **public, unauthenticated** job-board endpoint, one polite pass at a time
(concurrency 3, spaced requests per host). This file records which sources are used,
which are not, and why.

## In use

| ATS | Endpoint | Notes |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true&pay_transparency=true` | Public board API. Structured pay (`pay_input_ranges`) and `first_published`. |
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` | Public postings API. `salaryRange`, `workplaceType`, `country`. |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | Public posting API. `compensation`, `publishedAt`, `workplaceType`, address. |

## Not built

### SmartRecruiters: excluded

`api.smartrecruiters.com/robots.txt` is `User-agent: * / Disallow: /`; only LinkedInBot is
allowed. Chronicle respects robots.txt, so there is no SmartRecruiters adapter.

### Workday: planned, blocked on network access (September 2026)

Plan (maintainer decision):
- Workday's job-site API (`{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`) is
  allowed by robots.txt. Workday's site terms may still prohibit automated access.
- So the adapter is to be built and tested with **zero active tenants**.
- The verified tenants go in `api/candidates/workday_tenants.json`, with a one-line enable
  command, once the terms question is settled.

### Workable: planned, blocked on network access (September 2026)

Plan:
- Workable's public endpoints (`apply.workable.com/api/v3/accounts/{account}/jobs`) are
  allowed by robots.txt, and Workable's terms have no scraping clause.
- The adapter is to be built, enabled through the verify gate
  (`app.ingest.verify_and_add_companies`), with a takedown contact published.

### Status of both

- **Neither adapter is built yet.** The session building the upgrade (PR 5) ran in a sandbox
  whose network policy blocks `*.myworkdayjobs.com`, `apply.workable.com` and
  `www.workable.com` (and the Greenhouse/Lever/Ashby APIs).
- The project's rules require every adapter and parser to ship with tests on **real,
  recorded payloads**, and forbid invented data. So the adapters were not written against
  guessed response shapes.
- To finish them, run a session with network access to those hosts. It should:
  1. record one board per ATS into `api/tests/fixtures/`;
  2. confirm robots.txt;
  3. build the adapters against those fixtures.

## Takedown

A company that wants its board removed can open an issue at
https://github.com/pratyushpad/Chronicle/issues; the board is deactivated in the registry
(`companies.active = false`) and drops out of the site at the next ingest.
