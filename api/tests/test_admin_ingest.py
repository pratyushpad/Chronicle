"""Auth on the ingest trigger. The trigger must never run unauthenticated: missing/wrong
secret → 401, unset server secret → 500. DB-free (the guard rejects before the endpoint
body/DB), tested against a minimal app so main's startup seeding doesn't require a DB."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.admin import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_ingest_401_without_secret(client, monkeypatch):
    monkeypatch.setenv("INGEST_SECRET", "s3cret")
    assert client.post("/admin/ingest").status_code == 401


def test_ingest_401_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("INGEST_SECRET", "s3cret")
    r = client.post("/admin/ingest", headers={"X-Ingest-Secret": "nope"})
    assert r.status_code == 401


def test_ingest_500_when_secret_unset(client, monkeypatch):
    monkeypatch.delenv("INGEST_SECRET", raising=False)
    r = client.post("/admin/ingest", headers={"X-Ingest-Secret": "anything"})
    assert r.status_code == 500
