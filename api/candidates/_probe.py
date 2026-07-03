"""Reusable probe — turn a raw candidate pool into a clean, live-confirmed batch.

Usage (from api/):
    python candidates/_probe.py <raw_pool.json> <out_batch.json>

Reads a raw pool of [{name, ats, slug, industry?}], dedups against
companies.seed.json AND every existing candidates/batch*.json, live-probes each
slug against its ATS, and writes ONLY companies that return >=1 job to
<out_batch.json>. Prints the active/empty/404/seeded split so a weak pool is
visible before anything is committed. Never touches the DB.

`ats` may be one of greenhouse|lever|ashby, or "auto" to try all three and keep
the first that returns jobs (useful when the company is known but its ATS isn't).
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # put api/ on sys.path

from app.models import ATSSource  # noqa: E402
from app.ingest.runner import _ADAPTERS  # noqa: E402

_API_DIR = Path(__file__).resolve().parent.parent
_SEED = _API_DIR / "companies.seed.json"
_CAND_DIR = _API_DIR / "candidates"
_CONCURRENCY = 6
_TIMEOUT = 12
_AUTO_ORDER = [ATSSource.greenhouse, ATSSource.lever, ATSSource.ashby]


def _existing_keys(exclude: Path) -> set[tuple[str, str]]:
    """(ats, slug) already in the seed or any other prepared batch."""
    keys = {(e["ats"], e["slug"]) for e in json.loads(_SEED.read_text())}
    for f in _CAND_DIR.glob("batch*.json"):
        if f.resolve() == exclude.resolve():
            continue
        for e in json.loads(f.read_text()):
            keys.add((e["ats"], e["slug"]))
    return keys


async def _fetch(ats: ATSSource, slug: str, client, sem) -> tuple[str, int]:
    """Return (status, job_count) for one ATS/slug."""
    async with sem:
        await asyncio.sleep(0.15)  # polite pacing to avoid ATS 429s
        try:
            jobs = await _ADAPTERS[ats].fetch(slug, client)
        except httpx.HTTPStatusError as e:
            return ("http404" if e.response.status_code == 404 else "err", 0)
        except Exception:
            return ("err", 0)
    return ("active", len(jobs)) if len(jobs) >= 1 else ("empty", 0)


async def _probe_one(cand: dict, client, sem) -> dict:
    raw_ats = (cand.get("ats") or "auto").lower()
    tries = _AUTO_ORDER if raw_ats == "auto" else None
    if tries is None:
        try:
            tries = [ATSSource(raw_ats)]
        except ValueError:
            return {**cand, "_status": "bad_ats", "_jobs": 0}
    for ats in tries:
        status, n = await _fetch(ats, cand["slug"], client, sem)
        if status == "active":
            return {**cand, "ats": ats.value, "_status": "active", "_jobs": n}
        last = status
    return {**cand, "_status": last, "_jobs": 0}


async def _run(pool: list[dict], existing: set[tuple[str, str]]):
    seen: set[tuple[str, str]] = set()
    uniq: list[dict] = []
    dropped_known = 0
    for c in pool:
        # For explicit-ats candidates we can dedup up front; "auto" is deduped after probe.
        k = (c.get("ats", "auto"), c["slug"])
        if k in seen:
            continue
        seen.add(k)
        if c.get("ats", "auto") != "auto" and (c["ats"], c["slug"]) in existing:
            dropped_known += 1
            continue
        uniq.append(c)
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": "ChronicleBot/1.0"}) as client:
        results = await asyncio.gather(*(_probe_one(c, client, sem) for c in uniq))
    return uniq, results, dropped_known


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python candidates/_probe.py <raw_pool.json> <out_batch.json>")
        raise SystemExit(2)
    raw_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    pool = json.loads(raw_path.read_text())
    existing = _existing_keys(exclude=out_path)

    uniq, results, dropped_known = asyncio.run(_run(pool, existing))

    # Keep confirmed actives; drop any that resolved to an already-known (ats, slug)
    # (matters for "auto" candidates whose real ATS wasn't known up front).
    actives, post_dropped = [], 0
    seen_active: set[tuple[str, str]] = set()
    for r in sorted(results, key=lambda r: -r["_jobs"]):
        if r["_status"] != "active":
            continue
        key = (r["ats"], r["slug"])
        if key in existing or key in seen_active:
            post_dropped += 1
            continue
        seen_active.add(key)
        actives.append({"name": r["name"], "ats": r["ats"], "slug": r["slug"], "industry": r.get("industry")})

    out_path.write_text(json.dumps(actives, indent=2) + "\n")

    c = Counter(r["_status"] for r in results)
    probed = len(uniq)
    print(f"raw={len(pool)}  dropped_known={dropped_known + post_dropped}  probed={probed}")
    print(f"  active={c['active']}  empty={c['empty']}  http404={c['http404']}  err={c['err']}  bad_ats={c['bad_ats']}")
    print(f"  hit_rate={c['active'] / max(1, probed):.0%}")
    print(f"wrote {len(actives)} confirmed-active -> {out_path}")


if __name__ == "__main__":
    main()
