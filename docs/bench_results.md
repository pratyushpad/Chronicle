# Search Latency Benchmark

Measured with `api/scripts/bench_search.py` on 2026-07-12 against a real ingested corpus
(221 companies, ~20.5k active jobs, all embedded), then re-run with synthetic rows to test
at ~1000-company scale.

**What is timed.** Each sample is one query, from embedding the query text to having both
candidate lists back: the int8 MiniLM query embedding, a pgvector cosine top-200 (HNSW
index), and, in `hybrid` mode, a second top-200 query that matches the query's first word in
job titles (`title ILIKE`, newest first). It does **not** time the production `/jobs`
handler: no Postgres full-text ranking, no RRF fusion, no filters and no response
serialization. Treat it as the cost of the retrieval queries, not as end-to-end search
latency. `POST /admin/bench` times the real handler (in process, with the intern filter) on
whatever database it runs against.

| corpus | mode | n | p50 | p95 | max |
|---|---|---|---|---|---|
| 20,499 real jobs | hybrid | 50 | 15 ms | **19 ms** | 81 ms |
| 50,000 synthetic | hybrid | 50 | 25 ms | **28 ms** | 50 ms |

Both are well inside the harness's 400 ms p95 budget. The pgvector HNSW cosine index keeps
the vector arm sub-linear as the corpus grows (20k → 50k barely moves p95).

**Caveat (honest):** these were measured on local hardware, which is faster than the Render
free tier (~0.5 vCPU, 512 MB). Production p95 will be higher: the number to trust for prod
is one measured against Neon from the Render box, not this local figure. This documents the
methodology and the local baseline; re-run on prod for the deployed number.
