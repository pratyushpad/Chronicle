"""Extension bearer-token helpers.

The browser extension authenticates with a per-user bearer token. We store only
the sha256 hash (`User.extension_token_hash`); the plaintext is shown to the user
exactly once at issue time and never persisted. No external crypto deps — token
is high-entropy so a plain sha256 (not a slow KDF) is appropriate.
"""
import hashlib
import hmac
import secrets

# Prefix makes tokens self-identifying in logs/support without revealing entropy.
_TOKEN_PREFIX = "chr_"


def generate_extension_token() -> str:
    """A fresh opaque token to hand to the extension (shown once)."""
    return _TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """sha256 hex of the token — this is what we store."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, token_hash: str | None) -> bool:
    """Constant-time compare of a presented token against a stored hash."""
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_token(token), token_hash)
