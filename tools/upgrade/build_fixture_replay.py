"""Build a replay directory (record_boards.py layout) from committed real postings, for
environments that can't reach the job boards: CI's e2e job and network-restricted build
sandboxes. Uses the 119 labeled intern postings (api/tests/fixtures/pay_eval), grouped
into one board per company, keyed by each company's real registry slug.

  cd api && python ../tools/upgrade/build_fixture_replay.py <out_dir>
Prints the --only list for replay_ingest.py.
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

FIX = Path(__file__).resolve().parents[2] / "api" / "tests" / "fixtures"


def main() -> None:
    out = Path(sys.argv[1])
    boards: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for line in gzip.open(FIX / "pay_eval" / "intern_pay_labeled.jsonl.gz", "rt"):
        row = json.loads(line)
        raw = json.loads(row["raw"]) if isinstance(row["raw"], str) else row["raw"]
        boards[(row["ats"], row["company_slug"])][str(raw.get("id"))] = raw
    for (ats, slug), jobs in boards.items():
        items = list(jobs.values())
        payload = {"greenhouse": {"jobs": items, "meta": {"total": len(items)}},
                   "ashby": {"jobs": items, "apiVersion": "1"}}.get(ats, items)
        (out / ats).mkdir(parents=True, exist_ok=True)
        (out / ats / f"{slug}.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    print(",".join(f"{ats}:{slug}" for ats, slug in sorted(boards)))


if __name__ == "__main__":
    main()
