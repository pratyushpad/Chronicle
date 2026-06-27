import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ATSSource, Company

_SEED_FILE = Path(__file__).parent.parent.parent / "companies.seed.json"


def seed_companies_if_empty(session: Session) -> None:
    """Upsert all seed companies — runs on every startup so new companies are added."""
    data = json.loads(_SEED_FILE.read_text())
    for entry in data:
        stmt = (
            insert(Company)
            .values(
                name=entry["name"],
                ats=ATSSource(entry["ats"]),
                slug=entry["slug"],
                careers_url=entry.get("careers_url"),
                industry=entry.get("industry"),
                active=entry.get("active", True),
            )
            .on_conflict_do_update(
                constraint="companies_ats_slug_key",
                set_={
                    "name": entry["name"],
                    "careers_url": entry.get("careers_url"),
                    "industry": entry.get("industry"),
                    "active": entry.get("active", True),
                },
            )
        )
        session.execute(stmt)
    session.commit()


def load_active_companies(session: Session) -> list[Company]:
    return list(session.execute(select(Company).where(Company.active == True)).scalars())
