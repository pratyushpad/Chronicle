"""Endpoint-level hardening: security headers + bounded recommendations limit.

These use FastAPI's TestClient without triggering startup (no `with` block), so no
database connection is made. The recommendations test overrides get_current_user with
a profile-less user, which returns [] before any DB query runs.
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.routers import recommendations
from app.routers.users import get_current_user


def test_security_headers_present_on_every_response():
    client = TestClient(app)
    resp = client.get("/definitely-not-a-real-route")
    assert resp.status_code == 404
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "max-age=" in resp.headers["Strict-Transport-Security"]


def _client_with_profileless_user() -> TestClient:
    fake_user = MagicMock()
    fake_user.profile = None  # get_recommendations returns [] before touching the DB
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[recommendations._db] = lambda: MagicMock()
    return TestClient(app)


def test_recommendations_limit_upper_bound_rejected():
    client = _client_with_profileless_user()
    try:
        assert client.get("/users/me/recommendations?limit=99999").status_code == 422
        assert client.get("/users/me/recommendations?limit=0").status_code == 422
        ok = client.get("/users/me/recommendations?limit=30")
        assert ok.status_code == 200
        assert ok.json() == []
    finally:
        app.dependency_overrides.clear()
