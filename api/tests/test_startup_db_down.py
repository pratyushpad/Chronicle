"""The API must boot and pass /health even when the database is unreachable."""
from fastapi.testclient import TestClient

import app.main as main


def test_boots_when_seed_step_fails(monkeypatch):
    def boom(_session):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(main, "seed_companies_if_empty", boom)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
