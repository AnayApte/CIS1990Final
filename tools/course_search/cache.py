"""
Simple in-memory cache with optional TTL.

Keyed by arbitrary strings. Used to avoid re-fetching the full course list
(5800+ entries) and per-course details on repeated calls within a session.
"""

import time


class Cache:
    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, tuple[float, object]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str):
        """Return cached value or None if missing / expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value) -> None:
        self._store[key] = (time.time() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# Module-level singletons used by course_search.py
_course_list_cache = Cache(ttl_seconds=600)   # full course list — expensive to fetch
_detail_cache = Cache(ttl_seconds=300)         # per-course detail
