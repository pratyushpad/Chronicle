"""Internal HMAC-signed auth tokens for the Next.js proxy -> API hop.

The web app's server-side route handlers sign a short-lived token asserting
the authenticated user's email; the API verifies the signature and expiry and
derives the user from the verified claim. Replaces the old raw X-User-Email
header, which any caller could forge.

Token format (all bytes ASCII):

    v1.<base64url(JSON {"email": str, "iat": int, "exp": int})>.<hex sig>

where sig = HMAC_SHA256(secret, b"v1." + payload_b64). The version prefix is
inside the signed bytes so it cannot be swapped without invalidating the
signature. Tokens are signed per-request, so the TTL is short (5 minutes)
with +/-60s tolerance for clock skew between Vercel and Render.

Extension Bearer tokens (see security.py) are a separate mechanism and are
unaffected.
"""

import base64
import hashlib
import hmac
import json
import time

TOKEN_VERSION = "v1"
TOKEN_TTL_SECONDS = 300
CLOCK_SKEW_SECONDS = 60


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _signature(secret: str, signed_part: str) -> str:
    return hmac.new(secret.encode("utf-8"), signed_part.encode("ascii"), hashlib.sha256).hexdigest()


def sign_internal_token(email: str, secret: str, now: int | None = None) -> str:
    """Sign a short-lived internal token asserting `email`."""
    if not email or not secret:
        raise ValueError("email and secret are required")
    iat = int(time.time()) if now is None else int(now)
    payload = {"email": email, "iat": iat, "exp": iat + TOKEN_TTL_SECONDS}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signed_part = f"{TOKEN_VERSION}.{payload_b64}"
    return f"{signed_part}.{_signature(secret, signed_part)}"


def verify_internal_token(token: str, secret: str, now: int | None = None) -> str:
    """Verify signature + expiry; return the asserted email.

    Raises ValueError on any failure (malformed, bad signature, expired,
    issued in the future beyond clock skew).
    """
    if not token or not secret:
        raise ValueError("token and secret are required")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_VERSION:
        raise ValueError("malformed token")
    version, payload_b64, sig = parts
    signed_part = f"{version}.{payload_b64}"
    if not hmac.compare_digest(_signature(secret, signed_part), sig):
        raise ValueError("bad signature")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
        email = payload["email"]
        iat = int(payload["iat"])
        exp = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("malformed payload") from exc
    if not isinstance(email, str) or not email:
        raise ValueError("malformed payload")
    ts = int(time.time()) if now is None else int(now)
    if ts > exp + CLOCK_SKEW_SECONDS:
        raise ValueError("token expired")
    if iat > ts + CLOCK_SKEW_SECONDS:
        raise ValueError("token issued in the future")
    return email
