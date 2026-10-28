"""Small in-process TTL cache for anonymous public GETs.

Neon bills compute for every second the database is awake and egress for every byte a
query returns. Crawlers and shared feed pages repeat the same few requests, so the answer
to an identical anonymous request is kept for a short time instead of being recomputed.

Deliberately not shared between processes and never used for per-user responses: callers
only cache requests that carry no credentials (see `is_anonymous`).
"""
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable

TTL_MIN_S, TTL_MAX_S = 60, 300
DEFAULT_TTL_S = 120
DEFAULT_MAX_ENTRIES = 256


def configured_ttl() -> int:
    """JOBS_CACHE_TTL_S clamped to 60..300 s; 0 turns the cache off."""
    raw = int(os.environ.get("JOBS_CACHE_TTL_S", DEFAULT_TTL_S))
    return 0 if raw <= 0 else max(TTL_MIN_S, min(TTL_MAX_S, raw))


class TTLCache:
    """Thread-safe, size-bounded (least recently used evicted), per-entry expiry."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, clock: Callable[[], float] = time.monotonic):
        self._max = max_entries
        self._clock = clock
        self._data: "OrderedDict[Hashable, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable, ttl: float) -> Any | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            stored_at, value = hit
            if self._clock() - stored_at >= ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._data[key] = (self._clock(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


# Parameters whose default value means "not set": dropped from the key so /jobs and
# /jobs?page=1&page_size=20&mode=keyword share one entry.
_DEFAULTS = {"page": "1", "page_size": "20", "mode": "keyword", "since_last_run": "false"}


def normalized_key(path: str, query_items: list[tuple[str, str]]) -> tuple:
    """Order-, case- and default-insensitive key for a GET: names lowercased, values
    stripped, empty values and default values dropped, then sorted. Values keep their case
    (a search for "ML" is not "ml" to the matcher's caller, and the cost of a miss is one query)."""
    items = []
    for name, value in query_items:
        name, value = name.strip().lower(), value.strip()
        if not value or _DEFAULTS.get(name) == value.lower():
            continue
        items.append((name, value))
    return (path, tuple(sorted(items)))


def is_anonymous(headers) -> bool:
    """False when the request carries any credential, so it is never cached or served from
    cache (the response might one day differ per user)."""
    return not (headers.get("authorization") or headers.get("cookie") or headers.get("x-user-token"))
