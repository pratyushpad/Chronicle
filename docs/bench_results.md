# Search Latency Benchmark

Measured with `api/scripts/bench_search.py` on 2026-07-12 against a real ingested corpus
(221 companies, ~20.5k active jobs, all embedded), then re-run with synthetic rows to test
at ~1000-company scale. Hybrid mode = pgvector cosine arm + full-text arm, RRF-fused.

| corpus | mode | n | p50 | p95 | max |
|---|---|---|---|---|---|
| 20,499 real jobs | hybrid | 50 | 15 ms | **19 ms** | 81 ms |
| 50,000 synthetic | hybrid | 50 | 25 ms | **28 ms** | 50 ms |

Both are well inside the harness's 400 ms p95 budget. The pgvector HNSW cosine index keeps
the vector arm sub-linear as the corpus grows (20k → 50k barely moves p95).

**Caveat (honest):** these were measured on local hardware, which is faster than the Render
free tier (~0.5 vCPU, 512 MB). Production p95 will be higher — the number to trust for prod
is one measured against Neon from the Render box, not this local figure. This documents the
methodology and the local baseline; re-run on prod for the deployed number.
