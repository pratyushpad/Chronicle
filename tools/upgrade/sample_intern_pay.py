"""Sample real intern postings from the recorded payloads for a blind pay-labeling set.

  python sample_intern_pay.py <replay_dir> <out.jsonl> [n=100] [seed=7]
Stratified: every posting with structured pay or a '$/£/€ + digit' token is a candidate for the
"pay stated?" half; the rest fill the "no pay" half. Text is readable (block breaks kept) so a
labeler can read it like a human would. No network.
"""
import gzip
import html
import json
import random
import re
import sys
from pathlib import Path

from selectolax.parser import HTMLParser

INTERN = re.compile(r"\bintern(ship)?s?\b|\bco-?op\b", re.I)
MONEY = re.compile(r"[$£€]\s?\d|\b\d[\d,.]*\s?(?:USD|CAD|GBP|EUR)\b")
BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol", "table", "section"}


def readable(h: str | None) -> str:
    if not h:
        return ""
    tree = HTMLParser(h)
    for t in tree.css("script, style, noscript, template"):
        t.decompose()
    out = []
    def walk(n):
        for c in n.iter(include_text=True):
            if c.tag == "-text":
                out.append(c.text_content)
            else:
                if c.tag in BLOCK:
                    out.append("\n")
                walk(c)
                if c.tag in BLOCK:
                    out.append("\n")
    root = tree.body or tree.root
    walk(root)
    txt = "".join(out)
    txt = re.sub(r"[ \t\r\f\v]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def rows(replay: Path):
    for f in sorted(replay.glob("*/*.json.gz")):
        ats, slug = f.parent.name, f.name[:-8]
        data = json.loads(gzip.decompress(f.read_bytes()))
        jobs = data if isinstance(data, list) else data.get("jobs", [])
        for j in jobs:
            if ats == "greenhouse":
                title = j.get("title", ""); body = html.unescape(j.get("content") or "")
                struct = j.get("pay_input_ranges") or None
                loc = (j.get("location") or {}).get("name")
            elif ats == "lever":
                title = j.get("text", "")
                body = (j.get("description") or "") + "".join(
                    f"<h3>{html.escape(l.get('text',''))}</h3><ul>{l.get('content','')}</ul>" for l in (j.get("lists") or [])
                ) + (j.get("additional") or "")
                struct = j.get("salaryRange") or None
                loc = (j.get("categories") or {}).get("location")
            else:
                title = j.get("title", ""); body = j.get("descriptionHtml") or ""
                comp = j.get("compensation") or {}
                struct = {"summary": comp.get("compensationTierSummary"),
                          "components": comp.get("summaryComponents")} if comp.get("summaryComponents") else None
                loc = j.get("location")
            if not INTERN.search(title):
                continue
            text = readable(body)
            yield {"id": f"{ats}:{slug}:{j.get('id')}", "ats": ats, "company_slug": slug, "title": title,
                   "location": loc, "structured_pay": struct, "text": text[:12000],
                   "_has_money": bool(struct) or bool(MONEY.search(text))}


def main():
    replay, out = Path(sys.argv[1]), Path(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    rng = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 7)
    allrows = list(rows(replay))
    money = [r for r in allrows if r["_has_money"]]
    nomoney = [r for r in allrows if not r["_has_money"]]
    # cap per company so one board can't dominate
    def capped(xs, k, per=4):
        rng.shuffle(xs); seen = {}; picked = []
        for r in xs:
            c = r["company_slug"]
            if seen.get(c, 0) < per:
                picked.append(r); seen[c] = seen.get(c, 0) + 1
            if len(picked) >= k:
                break
        return picked
    sample = capped(money, int(n * 0.7)) + capped(nomoney, n - int(n * 0.7))
    rng.shuffle(sample)
    with out.open("w") as fh:
        for r in sample:
            r.pop("_has_money", None)
            fh.write(json.dumps(r) + "\n")
    print(f"intern postings: {len(allrows)} (money-like {len(money)}); sampled {len(sample)} -> {out}")


if __name__ == "__main__":
    main()
