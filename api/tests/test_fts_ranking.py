"""Full-text ranking weight test.

Proves the Job.search_tsv weighting makes a title match outrank a body-only match, so
`_keyword_search` / the hybrid lexical arm return relevance, not substring hits. Postgres
only (tsvector is Postgres-specific), so it skips cleanly where DATABASE_URL points at no
reachable Postgres — the CI/local job with a real DB exercises it. Hermetic: a temp table
using the exact app.models.JOB_SEARCH_TSV_SQL expression, rolled back automatically.
"""
import os

import pytest
from sqlalchemy import create_engine, text

from app.models import JOB_SEARCH_TSV_SQL


def _pg_engine():
    url = os.environ.get("DATABASE_URL", "")
    if "postgres" not in url:
        return None
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception:
        return None


@pytest.mark.skipif(_pg_engine() is None, reason="no reachable Postgres for FTS test")
def test_title_match_outranks_description_match():
    eng = _pg_engine()
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TEMP TABLE _fts_probe ("
                "  title text, department text, location_normalized text, description_text text,"
                f"  search_tsv tsvector GENERATED ALWAYS AS ({JOB_SEARCH_TSV_SQL}) STORED"
                ") ON COMMIT DROP"
            )
        )
        # A: "kubernetes" only in the title (weight A). B: only in the body (weight D).
        conn.execute(
            text(
                "INSERT INTO _fts_probe (title, department, location_normalized, description_text)"
                " VALUES"
                " ('Kubernetes Platform Engineer', 'Engineering', 'Remote', 'Work on internal tooling.'),"
                " ('Backend Engineer', 'Engineering', 'Remote', 'Operate services on kubernetes clusters daily.')"
            )
        )
        rows = conn.execute(
            text(
                "SELECT title, ts_rank_cd(search_tsv, websearch_to_tsquery('english', 'kubernetes')) AS r"
                " FROM _fts_probe ORDER BY r DESC"
            )
        ).all()

    assert len(rows) == 2
    # Title match ranks first; both match (proves it's ranking, not just filtering).
    assert rows[0].title == "Kubernetes Platform Engineer"
    assert rows[0].r > rows[1].r > 0
