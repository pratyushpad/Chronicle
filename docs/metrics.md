# Metrics and where they come from

Every number the README or the site states traces to a file or command here. Live
production numbers (open roles, boards re-checked, recent runs) are not copied into docs,
because they change daily: they come from the API (`GET /meta`, `GET /status`) and are
shown on the site and at `/status`.

## Upgrade before/after (September 2026, PR 1–8)

"Replica" means a local database built by replaying recorded board payloads through the
real ingest code (`tools/upgrade/`). The PR 1 replica held about 45k rows from a full
recording. PR 2–8 were built in a sandbox that could not reach the job boards, so their
replica is the 119 committed real intern postings (`tools/upgrade/build_fixture_replay.py`).

| Metric | Before | After | Source |
|---|---|---|---|
| Correct pay, intern postings that state pay | 3/80 (3.8%) | 77/80 (96.2%) | [`pay_eval.md`](pay_eval.md) (PR 1) |
| Correct pay, hourly intern postings | 0/65 | 62/65 | [`pay_eval.md`](pay_eval.md) (PR 1) |
| Intern roles in "Other" or no department | 50.8% (500 live, 2026-09-25); 47.6% on the 45k replica | 3.8% on the replica | [`UPGRADE_HANDOFF.md`](UPGRADE_HANDOFF.md), `replica_metrics.py` (PR 1) |
| All roles in "Other" or no department | 24.2% on the replica | 7.6% on the replica | same (PR 1) |
| Mobile horizontal overflow at 360/390/414 px | every route 443 px wide (658 px signed in) | 0 on every audited route, PR 1–7 | `tools/upgrade/web/shots.mjs` reports in `screenshots/upgrade/pr*/` |
| Cards hidden under reduced motion | 20 of 20 | 0 | same harness (`rm_hidden`) |
| Lighthouse, intern feed, mobile | production: perf 88, LCP 3.75 s, CLS 0; PR 2 local build: perf 88, a11y 96, LCP 3.92 s | PR 3 local: perf 96, a11y 100, LCP 2.74 s; PR 6 CI (GitHub runner, median of 5): perf 94, a11y 100, LCP 3.02 s, CLS 0 | `tools/upgrade/web/lh.mjs`, `lh-budget.mjs`, the `e2e` CI job (PR 3, PR 6) |
| LCP goal (plan: ≤ 2.5 s) | not met | **not met yet**: CI enforces ≤ 3.5 s as a regression guard and reports the gap | [`UPGRADE_PLAN.md`](UPGRADE_PLAN.md) PR 6 note |
| Student filters shipped (held-out precision ≥ 0.9) | none | term 0.98, degree levels 0.98, country 1.00; citizenship, clearance, MS/PhD-only and workplace not yet | [`extraction_eval.md`](extraction_eval.md) (PR 4) |
| Stored description size (compressed), fixture replica | 388,624 bytes (plain text) | 415,984 bytes (sanitized HTML subset, +7.0%) | PR 2 description |
| Description TOAST growth over 3 unchanged re-ingest passes | 464 KB → 1,808 KB (3.9×) | 464 KB → 464 KB (0%) | PR 7 description, `api/tests/test_run_lock_db.py` |
| Full-refresh cycle | about two weeks (twice-daily 10-minute runs on Render; README) | **not measured yet**: needs the Actions ingest scheduled (PR 7 stop point) | `.github/workflows/ingest.yml`, `/status` |

## Other measured claims

| Claim | Source |
|---|---|
| For You ranking: hybrid recall@50 0.71 → 0.96, MRR 0.80 → 0.98, NDCG@10 0.58 → 0.81 over the rule baseline (24 synthetic personas, bootstrap 95% CIs) | [`eval_results.md`](eval_results.md) |
| Search latency p95 19 ms (20.5k real rows) and 28 ms (50k synthetic), local hardware | [`bench_results.md`](bench_results.md); for production, run `POST /admin/bench` on the Render box (PR 7) |
| Registry size: 605 boards in the seed (596 active) | `api/companies.seed.json` |
