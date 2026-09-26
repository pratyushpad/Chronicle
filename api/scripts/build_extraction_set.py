"""Build the student-filter evaluation set from committed real postings (PR 4).

Sources: the 119 labeled intern postings (tests/fixtures/pay_eval) plus the PR 1 board
fixtures. Each row carries what a labeler needs (title, location, the ATS's own
workplace/country fields, and the posting's plain text) and a fixed split: about 40% dev
(used to write and tune the rules), the rest held out (scored once, never tuned on).

  cd api && .venv/bin/python -m scripts.build_extraction_set
"""
import gzip
import hashlib
import json
import re
from pathlib import Path

from app.ingest.adapters.ashby import AshbyAdapter
from app.ingest.adapters.greenhouse import GreenhouseAdapter
from app.ingest.adapters.lever import LeverAdapter
from app.ingest.normalize import plain_text

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIX / "extraction_eval" / "postings.jsonl.gz"
PARSERS = {"greenhouse": GreenhouseAdapter.parse, "lever": LeverAdapter.parse, "ashby": AshbyAdapter.parse}


def _ats_hints(ats: str, raw: dict) -> dict:
    """The ATS's own structured workplace/country fields, when it has any."""
    if ats == "lever":
        return {"workplaceType": raw.get("workplaceType"), "country": raw.get("country")}
    if ats == "ashby":
        addr = ((raw.get("address") or {}).get("postalAddress") or {})
        return {"workplaceType": raw.get("workplaceType"), "isRemote": raw.get("isRemote"),
                "country": addr.get("addressCountry")}
    return {}


def _rows():
    for line in gzip.open(FIX / "pay_eval" / "intern_pay_labeled.jsonl.gz", "rt"):
        r = json.loads(line)
        raw = json.loads(r["raw"]) if isinstance(r["raw"], str) else r["raw"]
        yield r["id"], r["ats"], r["company_slug"], raw
    # The PR 1 Greenhouse fixture mixes several companies' boards: key each posting by its
    # own company_name, not the first board's slug.
    gh = json.loads((FIX / "pr1_greenhouse.json").read_text())["jobs"]
    for raw in gh:
        slug = re.sub(r"[^a-z0-9]+", "", (raw.get("company_name") or "unknown").lower())
        yield f"greenhouse:{slug}:{raw['id']}", "greenhouse", slug, raw
    for raw in json.loads((FIX / "pr1_lever.json").read_text()):
        yield f"lever:pr1:{raw['id']}", "lever", "pr1", raw
    for raw in json.loads((FIX / "pr1_ashby.json").read_text())["jobs"]:
        yield f"ashby:pr1:{raw['id']}", "ashby", "pr1", raw


def main() -> None:
    seen, out = set(), []
    for pid, ats, slug, raw in _rows():
        if pid in seen:
            continue
        seen.add(pid)
        job = PARSERS[ats](raw)
        text = plain_text(job.description_html) or ""
        split = "dev" if int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 10 < 4 else "heldout"
        out.append({"id": pid, "ats": ats, "company": slug, "title": job.title, "location": job.location,
                    "ats_hints": _ats_hints(ats, raw), "split": split, "text": text})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt") as f:
        for row in sorted(out, key=lambda r: r["id"]):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    dev = sum(r["split"] == "dev" for r in out)
    print(json.dumps({"postings": len(out), "dev": dev, "heldout": len(out) - dev}))


if __name__ == "__main__":
    main()
