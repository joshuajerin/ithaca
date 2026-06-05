"""Tiny thread-safe in-process TTL cache.

Used to bound repeated upstream calls within a session (notably intraday OHLCV
fetches, which are pulled live per request rather than persisted). This is a
best-effort cache only: a miss simply re-fetches, and nothing here ever
substitutes synthetic data for a real result.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Optional[Any]:
    with _lock:
        item = _store.get(key)
        if not item:
            return None
        expires, value = item
        if expires < time.time():
            _store.pop(key, None)
            return None
        return value


def put(key: str, value: Any, ttl: float) -> None:
    with _lock:
        _store[key] = (time.time() + ttl, value)


def cached(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    """Return the cached value for `key`, or compute + store it via `producer`.

    `producer` exceptions propagate (and are not cached), so an upstream failure
    is surfaced to the caller to handle as a clean unavailable state.
    """
    hit = get(key)
    if hit is not None:
        return hit
    value = producer()
    if value is not None:
        put(key, value, ttl)
    return value
