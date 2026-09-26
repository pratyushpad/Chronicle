"""Record every active board's raw ATS payload once, so all later ingests can replay
identical bytes (deterministic before/after, one polite network pass).

Politeness: concurrency 3 (same as the prod runner), one retry after 2s, a per-host
minimum gap between request starts. Writes replay/<ats>/<slug>.json.gz + manifest.json.

Usage: python record_boards.py <companies.seed.json> <out_dir> [--only ats:slug,...]
"""
import asyncio
import gzip
import json
import sys
import time
from pathlib import Path

import httpx

URLS = {
    # Superset of params any branch's adapter will request; replay keys on (ats, slug).
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true&pay_transparency=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
}
CONCURRENCY = 3
HOST_GAP_S = 0.5  # min spacing between request starts to the same host

_last_start: dict[str, float] = {}
_host_locks: dict[str, asyncio.Lock] = {}


async def _polite_wait(host: str) -> None:
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        wait = _last_start.get(host, 0) + HOST_GAP_S - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_start[host] = time.monotonic()


async def fetch_one(client, sem, ats, slug, out_dir: Path):
    url = URLS[ats].format(slug=slug)
    host = httpx.URL(url).host
    dest = out_dir / ats / f"{slug}.json.gz"
    rec = {"ats": ats, "slug": slug, "url": url}
    async with sem:
        for attempt in range(2):
            await _polite_wait(host)
            t0 = time.monotonic()
            try:
                r = await client.get(url, timeout=90)
                rec.update(status=r.status_code, bytes=len(r.content), secs=round(time.monotonic() - t0, 2))
                if r.status_code == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(gzip.compress(r.content, compresslevel=6))
                    return rec
                if r.status_code < 500 and r.status_code != 429:
                    return rec  # 404 etc: deterministic, don't retry
            except Exception as exc:  # noqa: BLE001
                rec.update(status=None, error=f"{type(exc).__name__}: {exc}"[:300])
            if attempt == 0:
                await asyncio.sleep(2 if rec.get("status") != 429 else 30)
    return rec


async def main():
    seed_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    seed = json.loads(seed_path.read_text())
    targets = [
        (e["ats"], e["slug"]) for e in seed
        if e.get("active", True) and e["ats"] in URLS and (only is None or f"{e['ats']}:{e['slug']}" in only)
    ]
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": "Chronicle-dev-recorder/1.0 (+https://github.com/pratyushpad/Chronicle)"}
    t0 = time.monotonic()
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        results = await asyncio.gather(*(fetch_one(client, sem, a, s, out_dir) for a, s in targets))
    manifest = {"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    ok = sum(1 for r in results if r.get("status") == 200)
    total_bytes = sum(r.get("bytes", 0) for r in results)
    print(f"recorded {ok}/{len(results)} boards, {total_bytes/1e6:.1f} MB raw, {time.monotonic()-t0:.0f}s")
    bad = [r for r in results if r.get("status") != 200]
    for r in bad[:40]:
        print("  FAIL", r["ats"], r["slug"], r.get("status"), r.get("error", ""))


if __name__ == "__main__":
    asyncio.run(main())
