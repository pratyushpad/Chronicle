"""Pay accuracy on real internship postings: the pre-PR-1 parser vs. the current ingest path.

    python -m scripts.eval_pay [--details]

Ground truth: tests/fixtures/pay_eval/intern_pay_labeled.jsonl.gz — 120 intern postings
sampled from the 2026-09-25 recording of every active board (70% with a money-like token,
30% without; at most 4 per company), each with the raw ATS job object and a label made by
an annotator who never saw either parser: whether base pay is stated, min, max, currency,
period (hour/day/week/month/year, or "unclear" when a careful reader can't tell).

Scoring a posting:
  * no pay stated → correct iff nothing is shown (no invented pay);
  * period "unclear" → correct iff nothing is shown (we never guess a period);
  * otherwise → correct iff the shown min, max, currency AND period all match the label.
The legacy side is the salary Chronicle displayed before PR 1: `extract_salary` over the old
`strip_html` text (structured ATS pay was ignored), always rendered as annual "$Xk" USD.
"""
import argparse
import gzip
import html
import json
import re
from pathlib import Path

from selectolax.parser import HTMLParser

from app.ingest.adapters.ashby import AshbyAdapter
from app.ingest.adapters.greenhouse import GreenhouseAdapter
from app.ingest.adapters.lever import LeverAdapter
from app.ingest.normalize import plain_text
from app.ingest.pay import resolve_pay

FIXTURE = Path(__file__).resolve().parent.parent / "tests/fixtures/pay_eval/intern_pay_labeled.jsonl.gz"
_ADAPTERS = {"greenhouse": GreenhouseAdapter, "lever": LeverAdapter, "ashby": AshbyAdapter}

# ── The pre-PR-1 parser, verbatim from api/app/ingest/normalize.py @ 7c9aa97 ─────────────
_WS = re.compile(r"\s+")
_LEGACY_RANGE = re.compile(
    r"\$\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*\$?\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*[kK]?",
    re.IGNORECASE,
)
_LEGACY_SINGLE = re.compile(r"\$\s*(\d{2,3}(?:,\d{3})?)\s*[kK]", re.IGNORECASE)


def _legacy_strip_html(h: str | None) -> str | None:
    if not h:
        return None
    return _WS.sub(" ", HTMLParser(h).text(separator="\n", strip=True)).strip() or None


def _legacy_k(raw: str) -> int:
    val = float(raw.replace(",", ""))
    return int(val * 1000) if val < 1000 else int(val)


def _legacy_salary(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    m = _LEGACY_RANGE.search(text)
    if m:
        lo, hi = sorted((_legacy_k(m.group(1)), _legacy_k(m.group(2))))
        if 30_000 <= lo <= 1_000_000 and 30_000 <= hi <= 1_000_000:
            return lo, hi
    m = _LEGACY_SINGLE.search(text)
    if m:
        val = _legacy_k(m.group(1))
        if 30_000 <= val <= 1_000_000:
            return val, None
    return None, None


def _legacy_description(ats: str, raw: dict) -> str | None:
    """The HTML the pre-PR-1 adapters handed to strip_html."""
    if ats == "greenhouse":
        return html.unescape(raw["content"]) if raw.get("content") else None
    if ats == "lever":
        return raw.get("description")  # lists/additional were dropped
    return raw.get("descriptionHtml")


def legacy_prediction(ats: str, raw: dict) -> dict | None:
    lo, hi = _legacy_salary(_legacy_strip_html(_legacy_description(ats, raw)))
    if lo is None:
        return None
    return {"min": lo, "max": hi if hi is not None else lo, "currency": "USD", "period": "year"}


def current_prediction(ats: str, raw: dict) -> dict | None:
    job = _ADAPTERS[ats].parse(raw)
    pay = resolve_pay(job.pay, plain_text(job.description_html))
    if pay is None:
        return None
    return {"min": float(pay.min), "max": float(pay.max), "currency": pay.currency, "period": pay.period}


# ── Scoring ───────────────────────────────────────────────────────────────────────────
def _close(a, b) -> bool:
    return abs(float(a) - float(b)) <= 0.005 * max(abs(float(a)), abs(float(b)), 1.0)


def score(label: dict, pred: dict | None) -> tuple[bool, str]:
    if not label["pay_stated"]:
        return (pred is None, "ok" if pred is None else "invented pay")
    if label["period"] == "unclear":
        return (pred is None, "ok (left unshown)" if pred is None else "guessed a period")
    if pred is None:
        return (False, "missed")
    ok = (_close(pred["min"], label["min"]) and _close(pred["max"], label["max"])
          and pred["currency"] == label["currency"] and pred["period"] == label["period"])
    return (ok, "ok" if ok else "wrong amount/currency/period")


def evaluate(rows: list[dict]) -> dict:
    out = {}
    for name, predict in (("before", legacy_prediction), ("after", current_prediction)):
        results = [(r, *score(r["label"], predict(r["ats"], r["raw"]))) for r in rows]
        stated = [x for x in results if x[0]["label"]["pay_stated"] and x[0]["label"]["period"] != "unclear"]
        hourly = [x for x in stated if x[0]["label"]["period"] == "hour"]
        not_stated = [x for x in results if not x[0]["label"]["pay_stated"]]
        out[name] = {
            "overall": (sum(x[1] for x in results), len(results)),
            "pay_stated": (sum(x[1] for x in stated), len(stated)),
            "hourly": (sum(x[1] for x in hourly), len(hourly)),
            "invented_on_not_stated": (sum(1 for x in not_stated if not x[1]), len(not_stated)),
            "misses": [(x[0]["id"], x[0]["title"], x[2]) for x in results if not x[1]],
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true", help="list every posting scored wrong")
    args = ap.parse_args()
    rows = [json.loads(line) for line in gzip.decompress(FIXTURE.read_bytes()).decode().splitlines()]
    res = evaluate(rows)
    pct = lambda t: f"{t[0]}/{t[1]} ({t[0] / t[1]:.1%})" if t[1] else "n/a"
    print("| measure | before (pre-PR-1 parser) | after (current ingest path) |")
    print("|---|---|---|")
    for key, label in (("pay_stated", "correct pay, postings that state pay (period clear)"),
                       ("hourly", "correct pay, hourly postings"),
                       ("overall", "correct result, all postings (incl. correctly showing nothing)")):
        print(f"| {label} | {pct(res['before'][key])} | {pct(res['after'][key])} |")
    print(f"| invented pay on postings that state none | {pct(res['before']['invented_on_not_stated'])} "
          f"| {pct(res['after']['invented_on_not_stated'])} |")
    if args.details:
        for side in ("before", "after"):
            print(f"\n{side} — wrong:")
            for pid, title, why in res[side]["misses"]:
                print(f"  {why:28} {pid:60} {title}")


if __name__ == "__main__":
    main()
