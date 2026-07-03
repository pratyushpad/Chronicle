# Candidate batches — registry expansion

Batch files (`batchN.json`) are lists of `{name, ats, slug, industry}` fed to the verify gate:

```
python -m app.ingest.verify_and_add_companies candidates/batchN.json           # dry-run
python -m app.ingest.verify_and_add_companies candidates/batchN.json --commit   # persist (prod)
```

## How these batches were built (provenance)

Every company in a committed batch was **live-probed and confirmed to have ≥1 open role** before
being written here (pre-filtered to actives), so a `--commit` produces ~zero quarantine and keeps
`companies.seed.json` clean.

- **`_probe.py`** — reusable harness. Takes a raw pool `[{name, ats, slug|"auto"}]`, dedups against
  `companies.seed.json` + every existing `batch*.json`, live-probes each slug against its ATS
  (Greenhouse/Lever/Ashby), and writes only confirmed-active companies out. `ats:"auto"` tries all
  three and keeps the first with jobs.
- **batch2–batch4** (this session): sourced by cross-referencing a curated list of well-known tech
  companies against live ATS boards (validated via the public
  [job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) token lists), then
  live-probing. Ordered most-substantial-first (by open-role count).

## Quality note

The aggregator token lists (~15.9k slugs across the three ATSes) are an **all-industry** index, so
bulk-adding by job-count alone pulls in non-tech SMBs, staffing/services firms, brand duplicates
(`doordashusa`), and mislabeled boards. Batches here are therefore **curated to recognizable tech
companies** rather than filled to a round number from the raw index. To extend: add well-known
company names to a raw pool and run them through `_probe.py`; review the output before committing.
