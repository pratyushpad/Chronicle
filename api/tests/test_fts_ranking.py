"""Full-text ranking test for the functional GIN index (JOB_SEARCH_FTS_EXPR).

Proves the weighting makes a title match outrank a skills(tech_tags) match, and that the
description body is intentionally NOT indexed (so a body-only term doesn't match) — the
storage tradeoff that keeps FTS within Neon's 512 MB free tier. Postgres only; skips where
no reachable Postgres. Hermetic: a temp table + the same functional index, rolled back.
"""
import os

import pytest
from sqlalchemy import create_engine, text

from app.models import JOB_SEARCH_FTS_EXPR


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
def test_title_outranks_department_and_body_is_not_indexed():
    eng = _pg_engine()
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TEMP TABLE _fts_probe ("
                "  title text, department text, location_normalized text, description_text text"
                ") ON COMMIT DROP"
            )
        )
        # Same functional index the migration creates — proves the expression is IMMUTABLE.
        conn.execute(text(f"CREATE INDEX ON _fts_probe USING GIN (({JOB_SEARCH_FTS_EXPR}))"))
        conn.execute(
            text(
                "INSERT INTO _fts_probe (title, department, location_normalized, description_text) VALUES"
                " ('Security Engineer', 'Engineering', 'Remote', 'general work'),"
                " ('Backend Engineer', 'Security', 'Remote', 'general work'),"
                " ('Data Analyst', 'Data', 'NYC', 'we care deeply about security')"
            )
        )
        rows = conn.execute(
            text(
                f"SELECT title, ts_rank_cd(({JOB_SEARCH_FTS_EXPR}),"
                " websearch_to_tsquery('english', 'security')) AS r"
                f" FROM _fts_probe WHERE ({JOB_SEARCH_FTS_EXPR})"
                " @@ websearch_to_tsquery('english', 'security') ORDER BY r DESC"
            )
        ).all()

    titles = [r.title for r in rows]
    # Title (weight A) and department (weight C) rows match; the body-only row does not.
    assert titles == ["Security Engineer", "Backend Engineer"]
    assert rows[0].r > rows[1].r > 0
