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

app = FastAPI(title="Folio API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],
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


@app.on_event("startup")
def startup() -> None:
    session = get_session()
    try:
        seed_companies_if_empty(session)
    finally:
        session.close()
