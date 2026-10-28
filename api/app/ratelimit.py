"""Small in-process, per-client rate limiter for the expensive public endpoints.

The API runs as one process on one Render instance, so an in-memory sliding window is
enough (no Redis). It guards semantic and hybrid search, the only public paths that run
the embedder: each costs 90 to 550 ms of API CPU on 0.5 CPU, so a single scripted client
used to saturate the instance at about 5.8 req/s.

Client identity: Render's proxy appends the connecting address to X-Forwarded-For, so the
RIGHTMOST entry is the one a caller cannot forge. Without the header (local runs, tests)
the socket peer is used. Server-side renders on Vercel arrive from Vercel's egress IPs and
would share those buckets and turn a per-client limit into a site-wide one, so requests
that prove they come from our own web server (see is_trusted_server) use a separate, higher
shared bucket. They are not exempt, because anyone can make the web server render a search.
Browsers and other direct callers keep the per-client limit.
"""
from __future__ import annotations

import hmac
import hashlib
import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request


SERVICE_HEADER = "x-internal-service"
_SERVICE_LABEL = b"chronicle-ratelimit-exempt-v1"


def service_key(secret: str) -> str:
    """Static value the web sends in X-Internal-Service. Derived from INTERNAL_API_SECRET
    (so the secret itself never travels on public fetches) and constant, so it does not
    change the Next.js fetch cache key the way a per-request timestamped token would.
    Mirror of web/src/lib/internal-service.ts."""
    return hmac.new(secret.encode("utf-8"), _SERVICE_LABEL, hashlib.sha256).hexdigest()


def is_trusted_server(request: Request | None) -> bool:
    """True when the request carries the server-to-server key. Fails closed: with no
    INTERNAL_API_SECRET configured nobody is exempt."""
    if request is None:
        return False
    secret = os.environ.get("INTERNAL_API_SECRET")
    got = request.headers.get(SERVICE_HEADER)
    if not secret or not got:
        return False
    return hmac.compare_digest(service_key(secret), got)


def client_id(request: Request | None) -> str:
    if request is None:
        return "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        last = fwd.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_seconds: float, max_keys: int = 10_000, server_limit: int | None = None
    ):
        self.limit = limit
        self.server_limit = server_limit if server_limit is not None else limit * 4
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None, limit: int | None = None) -> tuple[bool, int]:
        """Record a hit for key. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        limit = self.limit if limit is None else limit
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self.max_keys:
                    self._hits.clear()  # crude bound on memory under an IP-rotating flood
                q = self._hits[key] = deque()
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= limit:
                oldest = q[0] if q else now
                return False, max(1, int(self.window - (now - oldest)) + 1)
            q.append(now)
            return True, 0

    def check(self, request: Request | None, scope: str) -> None:
        # Our own server renders are not exempt: anyone can make Vercel render
        # /jobs?q=...&mode=hybrid, so they share one higher bucket instead of none.
        if is_trusted_server(request):
            key, limit = f"{scope}:web-server", self.server_limit
        else:
            key, limit = f"{scope}:{client_id(request)}", self.limit
        ok, retry = self.allow(key, limit=limit)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail="Too many search requests, slow down",
                headers={"Retry-After": str(retry)},
            )

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# 30 semantic/hybrid searches per minute per client. A person typing in the search box
# sends far fewer (the client debounces); a bot at 30/min costs at most about 0.5 s of
# API CPU per second, leaving the instance responsive.
# Server renders from our own web app share one bucket of 120/min (all real users who
# search through the site together), so a bot driving Vercel renders is capped too.
search_limiter = SlidingWindowLimiter(
    limit=int(os.getenv("SEARCH_RATE_LIMIT_PER_MIN", "30")),
    window_seconds=60.0,
    server_limit=int(os.getenv("SEARCH_RATE_LIMIT_WEB_PER_MIN", "120")),
)
