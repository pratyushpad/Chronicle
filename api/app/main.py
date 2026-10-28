import logging
import os

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError as PoolTimeoutError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.db import get_session  # noqa: E402
from app.ingest.registry import seed_companies_if_empty  # noqa: E402
from app.routers.jobs import router as jobs_router  # noqa: E402
from app.routers.users import router as users_router  # noqa: E402
from app.routers.saved import router as saved_router  # noqa: E402
from app.routers.applications import router as apps_router  # noqa: E402
from app.routers.recommendations import router as recs_router  # noqa: E402
from app.routers.notifications import router as notif_router  # noqa: E402
from app.routers.interactions import router as interactions_router  # noqa: E402
from app.routers.admin import router as admin_router  # noqa: E402

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seeding is a convenience for empty databases. If the database is unreachable at boot
    # (for example a suspended free-tier compute), start anyway so /health passes and the
    # deploy goes live; data routes recover on their own once the database is back.
    session = get_session()
    try:
        seed_companies_if_empty(session)
    except Exception as exc:  # noqa: BLE001 - never block startup on the seed step
        logging.getLogger(__name__).warning("startup seed skipped: %s", type(exc).__name__)
    finally:
        session.close()
    yield


app = FastAPI(title="Chronicle API", version="2.0.0", lifespan=lifespan)

# Comma-separated allowlist; prod sets CORS_ORIGINS=https://chronicles-weld.vercel.app
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:3002"
    ).split(",")
    if o.strip() and o.strip() != "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # browsers cache the preflight for a day instead of re-asking per request
)


async def _db_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Database down, suspended (Neon free quota) or timing out: answer 503 with Retry-After
    instead of a raw 500 and a traceback, so clients and the web app's fetch retry logic treat
    it as temporary and crawlers do not treat pages as broken."""
    logging.getLogger(__name__).warning("database unavailable: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
        headers={"Retry-After": "60"},
    )


app.add_exception_handler(OperationalError, _db_unavailable)
app.add_exception_handler(InterfaceError, _db_unavailable)
app.add_exception_handler(PoolTimeoutError, _db_unavailable)


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline hardening headers. This is a JSON API served on its own origin, so
    DENY-ing framing and forcing HTTPS can't break the Next.js frontend."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
    )
    return response

@app.get("/health")
async def health() -> dict:
    """Cheap, DB-free liveness probe for the external keep-warm pinger (cron-job.org).
    Deliberately touches nothing so hitting it every ~5 min wakes the Render instance
    without any query load. async so it runs on the event loop and still answers when every
    threadpool worker is stuck waiting on a slow database."""
    return {"status": "ok"}


app.include_router(jobs_router)
app.include_router(users_router)
app.include_router(saved_router)
app.include_router(apps_router)
app.include_router(recs_router)
app.include_router(notif_router)
app.include_router(interactions_router)
app.include_router(admin_router)
