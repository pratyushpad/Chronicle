"""Read-only metrics over a LOCAL Chronicle database (schema-tolerant across branches).

  python replica_metrics.py postgresql://chronicle:chronicle@127.0.0.1:5434/chronicle [label]
Prints one JSON object. Refuses non-local hosts.
"""
import json
import sys
from urllib.parse import urlparse

import psycopg2

INTERN = "(j.experience_level = 'Internship' OR j.title ~* '\\mintern(ship)?s?\\M')"


def main():
    url = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    if urlparse(url).hostname not in {"127.0.0.1", "localhost"}:
        sys.exit("refusing non-local host")
    conn = psycopg2.connect(url, options="-c default_transaction_read_only=on")
    cur = conn.cursor()

    def one(sql, *a):
        cur.execute(sql, a)
        return cur.fetchone()[0]

    def rows(sql, *a):
        cur.execute(sql, a)
        return cur.fetchall()

    cols = {r[0] for r in rows("select column_name from information_schema.columns where table_name='jobs'")}
    m = {"label": label}
    m["companies_active"] = one("select count(*) from companies where active")
    m["jobs_total"] = one("select count(*) from jobs")
    m["jobs_active"] = one("select count(*) from jobs where is_active")
    m["roles_active_distinct"] = one("select count(distinct dedup_key) from jobs where is_active")
    m["active_embedding_null"] = one("select count(*) from jobs where is_active and embedding is null")
    m["hash_versions"] = dict(rows(
        "select case when content_hash is null then 'null' when content_hash like 'v%%' "
        "then left(content_hash,2) else 'legacy' end, count(*) from jobs group by 1"))

    def dept_dist(where):
        r = rows(f"select coalesce(j.department,'<null>'), count(distinct j.dedup_key) from jobs j "
                 f"where j.is_active and {where} group by 1 order by 2 desc")
        total = sum(c for _, c in r) or 1
        other = sum(c for d, c in r if d in ("Other", "<null>"))
        return {"total": total, "other_or_null": other, "share": round(other / total, 4), "top": r[:25]}

    m["dept_all"] = dept_dist("true")
    m["dept_intern"] = dept_dist(INTERN)

    m["intern_roles"] = one(f"select count(distinct j.dedup_key) from jobs j where j.is_active and {INTERN}")
    m["intern_with_salary"] = one(
        f"select count(distinct j.dedup_key) from jobs j where j.is_active and {INTERN} and j.salary_min is not null")
    if "pay_period" in cols:
        m["pay_period_dist"] = dict(rows("select coalesce(pay_period,'<null>'), count(*) from jobs where is_active group by 1"))
        m["pay_source_dist"] = dict(rows("select coalesce(pay_source,'<null>'), count(*) from jobs where is_active group by 1"))
        m["intern_pay_period"] = dict(rows(
            f"select coalesce(j.pay_period,'<null>'), count(*) from jobs j where j.is_active and {INTERN} group by 1"))
    m["posted_at_null_share"] = float(one(
        "select round(avg((posted_at is null)::int)::numeric, 4) from jobs where is_active") or 0)
    m["posted_after_first_seen_share"] = float(one(
        "select round(avg((posted_at > first_seen_at + interval '1 day')::int)::numeric, 4) "
        "from jobs where is_active and posted_at is not null") or 0)
    m["storage"] = {
        "db": one("select pg_size_pretty(pg_database_size(current_database()))"),
        "jobs_total": one("select pg_size_pretty(pg_total_relation_size('jobs'))"),
        "jobs_toast": one("select pg_size_pretty(coalesce(pg_total_relation_size(reltoastrelid),0)) from pg_class where relname='jobs'"),
        "desc_column_bytes": int(one("select coalesce(sum(pg_column_size(description_text)),0) from jobs")),
    }
    st = rows("select n_tup_ins, n_tup_upd, n_tup_hot_upd, n_dead_tup from pg_stat_user_tables where relname='jobs'")
    if st:
        m["tuple_stats"] = dict(zip(["ins", "upd", "hot_upd", "dead"], st[0]))
    print(json.dumps(m, default=str))


if __name__ == "__main__":
    main()
