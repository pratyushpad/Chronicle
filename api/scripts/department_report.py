"""Department before/after report (read-only).

    python -m scripts.department_report [--db URL]

Recomputes every active role's department with the current normalize_department() from
the stored department_raw + title (ATS hints aren't stored, so ingest can do slightly
better than this) and prints the distribution plus the "Other"/unset share for all roles
and for internships, next to what is stored now. Opens a read-only transaction, so it is
safe to point at any database; it writes nothing.
"""
import argparse
import collections
import os

from sqlalchemy import create_engine, text

from app.ingest.normalize import normalize_department

_INTERN_SQL = "(experience_level = 'Internship' OR title ~* '\\mintern(ship)?s?\\M')"


def _share(counter: collections.Counter) -> tuple[int, int, float]:
    total = sum(counter.values())
    other = counter.get("Other", 0) + counter.get(None, 0)
    return other, total, (other / total if total else 0.0)


def report(url: str) -> dict:
    eng = create_engine(url)
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        rows = conn.execute(text(
            f"SELECT DISTINCT ON (dedup_key) dedup_key, department, department_raw, title, {_INTERN_SQL} AS intern "
            "FROM jobs WHERE is_active ORDER BY dedup_key, id"
        )).all()
    out = {}
    for scope, keep in (("all", lambda r: True), ("intern", lambda r: r.intern)):
        before, after = collections.Counter(), collections.Counter()
        for r in rows:
            if not keep(r):
                continue
            before[r.department] += 1
            after[normalize_department(r.department_raw, r.title)] += 1
        out[scope] = {"before": _share(before), "after": _share(after),
                      "after_top": after.most_common(25)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()
    res = report(args.db)
    for scope, r in res.items():
        (bo, bt, bs), (ao, at, as_) = r["before"], r["after"]
        print(f"[{scope}] Other/unset: before {bo}/{bt} = {bs:.1%}  after {ao}/{at} = {as_:.1%}")
        print("   after:", ", ".join(f"{d or '<none>'} {n}" for d, n in r["after_top"]))


if __name__ == "__main__":
    main()
