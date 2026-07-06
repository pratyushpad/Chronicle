import pytest
from fastapi import HTTPException

from app.internal_auth import (
    CLOCK_SKEW_SECONDS,
    TOKEN_TTL_SECONDS,
    sign_internal_token,
    verify_internal_token,
)
from app.routers.users import require_internal_email

SECRET = "test-secret"
NOW = 1_800_000_000


def test_round_trip():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    assert verify_internal_token(token, SECRET, now=NOW) == "alice@example.com"


def test_token_shape():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    version, payload, sig = token.split(".")
    assert version == "v1"
    assert len(sig) == 64  # hex sha256


def test_forged_signature_rejected():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    version, payload, sig = token.split(".")
    forged = f"{version}.{payload}." + ("0" * 64)
    with pytest.raises(ValueError):
        verify_internal_token(forged, SECRET, now=NOW)


def test_wrong_secret_rejected():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    with pytest.raises(ValueError):
        verify_internal_token(token, "other-secret", now=NOW)


def test_tampered_payload_rejected():
    import base64
    import json

    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    version, payload_b64, sig = token.split(".")
    padding = "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    payload["email"] = "victim@example.com"
    tampered_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(ValueError):
        verify_internal_token(f"{version}.{tampered_b64}.{sig}", SECRET, now=NOW)


def test_expired_rejected():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    with pytest.raises(ValueError, match="expired"):
        verify_internal_token(token, SECRET, now=NOW + TOKEN_TTL_SECONDS + CLOCK_SKEW_SECONDS + 1)


def test_expiry_skew_boundary_accepted():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW)
    assert (
        verify_internal_token(token, SECRET, now=NOW + TOKEN_TTL_SECONDS + CLOCK_SKEW_SECONDS)
        == "alice@example.com"
    )


def test_future_issued_rejected():
    token = sign_internal_token("alice@example.com", SECRET, now=NOW + CLOCK_SKEW_SECONDS + 10)
    with pytest.raises(ValueError, match="future"):
        verify_internal_token(token, SECRET, now=NOW)


def test_malformed_tokens_rejected():
    for bad in ["", "v1", "v1.abc", "v2.abc.def", "not-a-token", "v1..", "v1.!!!.sig"]:
        with pytest.raises(ValueError):
            verify_internal_token(bad, SECRET, now=NOW)


def test_dependency_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    with pytest.raises(HTTPException) as exc:
        require_internal_email(None)
    assert exc.value.status_code == 401


def test_dependency_rejects_bad_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    with pytest.raises(HTTPException) as exc:
        require_internal_email("v1.garbage.garbage")
    assert exc.value.status_code == 401


def test_dependency_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    token = sign_internal_token("alice@example.com", SECRET)
    assert require_internal_email(token) == "alice@example.com"


def test_dependency_errors_without_secret(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_internal_email("anything")
    assert exc.value.status_code == 500
