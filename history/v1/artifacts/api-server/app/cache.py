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


# Per-key locks for single-flight. Guarded by `_flight_lock` while we hand out
# the per-key lock itself.
_flight_lock = threading.Lock()
_flights: dict[str, threading.Lock] = {}


def cached_singleflight(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    """Like `cached`, but collapses a concurrent cache miss to a single build.

    On a cold (or expired) key, plain `cached` lets every concurrent caller run
    `producer` at once — a thundering herd that, for an expensive producer (live
    upstream fetches, large payloads), saturates the worker. Here, the first
    caller builds while the others wait on a per-key lock and then read the value
    it just stored. `producer` exceptions still propagate and are not cached.
    """
    hit = get(key)
    if hit is not None:
        return hit
    with _flight_lock:
        kl = _flights.get(key)
        if kl is None:
            kl = threading.Lock()
            _flights[key] = kl
    with kl:
        # Another caller may have populated the key while we waited for the lock.
        hit = get(key)
        if hit is not None:
            return hit
        value = producer()
        if value is not None:
            put(key, value, ttl)
        return value
