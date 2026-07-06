import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.db import get_session  # noqa: E402
from app.ingest.registry import seed_companies_if_empty  # noqa: E402
from app.routers.jobs import router as jobs_router  # noqa: E402
from app.routers.users import router as users_router  # noqa: E402
from app.routers.saved import router as saved_router  # noqa: E402
from app.routers.applications import router as apps_router  # noqa: E402
from app.routers.recommendations import router as recs_router  # noqa: E402
from app.routers.notifications import router as notif_router  # noqa: E402
from app.routers.extension import router as extension_router  # noqa: E402
from app.routers.interactions import router as interactions_router  # noqa: E402

app = FastAPI(title="Chronicle API", version="2.0.0")

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
    # The extension's origin (chrome-extension://<id>) isn't known until it's loaded.
    # Real auth is per-request (bearer token), so origin isn't the security boundary here.
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(users_router)
app.include_router(saved_router)
app.include_router(apps_router)
app.include_router(recs_router)
app.include_router(notif_router)
app.include_router(extension_router)
app.include_router(interactions_router)


@app.on_event("startup")
def startup() -> None:
    session = get_session()
    try:
        seed_companies_if_empty(session)
    finally:
        session.close()
