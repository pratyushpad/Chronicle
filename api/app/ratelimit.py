"""Small in-process, per-client rate limiter for the expensive public endpoints.

The API runs as one process on one Render instance, so an in-memory sliding window is
enough (no Redis). It guards semantic and hybrid search, the only public paths that run
the embedder: each costs 90 to 550 ms of API CPU on 0.5 CPU, so a single scripted client
used to saturate the instance at about 5.8 req/s.

Client identity: Render's proxy appends the connecting address to X-Forwarded-For, so the
RIGHTMOST entry is the one a caller cannot forge. Without the header (local runs, tests)
the socket peer is used. Server-side renders on Vercel arrive from Vercel's egress IPs and
share those buckets, which is acceptable: it caps total SSR search load as well.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request


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
    def __init__(self, limit: int, window_seconds: float, max_keys: int = 10_000):
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Record a hit for key. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self.max_keys:
                    self._hits.clear()  # crude bound on memory under an IP-rotating flood
                q = self._hits[key] = deque()
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                oldest = q[0] if q else now
                return False, max(1, int(self.window - (now - oldest)) + 1)
            q.append(now)
            return True, 0

    def check(self, request: Request | None, scope: str) -> None:
        ok, retry = self.allow(f"{scope}:{client_id(request)}")
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
search_limiter = SlidingWindowLimiter(
    limit=int(os.getenv("SEARCH_RATE_LIMIT_PER_MIN", "30")), window_seconds=60.0
)
