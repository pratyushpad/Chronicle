import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_pre_ping=True,      # drop dead Neon connections before use
    pool_size=10,            # base connections kept open on this (long-running) Render process
    max_overflow=20,         # burst headroom under prefetch fan-out
    pool_recycle=1800,       # recycle every 30 min, under Neon's idle limit
    pool_timeout=30,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    return SessionLocal()
