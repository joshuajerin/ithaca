"""Resilience helpers shared by the key-less upstream data sources.

Yahoo's public chart/RSS endpoints and yfinance are unauthenticated and will
throttle (HTTP 429) or briefly 403 under load. The raw adapters used to fail a
whole ingest cycle on the first transient throttle. This module adds the three
things they lacked:

  - per-request retry with exponential backoff + jitter on 429/403/5xx and
    transient network errors;
  - a per-source circuit breaker so a source that keeps throttling backs off for
    a cooldown window (growing each time it re-opens) instead of being hammered
    every cycle;
  - throttle events logged distinctly (``terminal.sources.throttle``) from hard,
    non-throttle failures so they can be told apart in the logs.

Two entry points:
  - ``request(...)`` for the httpx-based GET sources (chart endpoint, RSS feeds),
    where throttling is detected from the HTTP status code;
  - ``guard(...)`` for yfinance, which does its own HTTP, where throttling is
    inferred from the raised exception.

Both raise ``CircuitOpenError`` when the source is cooling down and
``ThrottleError`` when retries are exhausted by throttling. Both subclass
``Exception`` so existing best-effort callers keep skipping/falling back as before.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, TypeVar

import httpx

log = logging.getLogger("terminal.sources")
# Dedicated child logger so throttle events can be filtered/silenced apart from
# hard failures, which surface on the callers' own loggers.
throttle_log = logging.getLogger("terminal.sources.throttle")

T = TypeVar("T")

# Retry/backoff knobs. Delays grow 0.8s, 1.6s, 3.2s ... capped, with +/- jitter
# so concurrent symbols don't retry in lockstep and re-trip the limit together.
_MAX_ATTEMPTS = 3
_BASE_BACKOFF = 0.8
_MAX_BACKOFF = 8.0
_JITTER = 0.4  # fraction of the computed delay, applied as +/-

# Circuit-breaker knobs. After this many consecutive throttled calls the breaker
# opens for a cooldown that doubles on each successive re-open (capped), and any
# clean success resets it.
_FAIL_THRESHOLD = 3
_BASE_COOLDOWN = 30.0
_MAX_COOLDOWN = 300.0

_THROTTLE_MARKERS = (
    "429", "too many requests", "rate limit", "rate-limit", "ratelimit",
    "throttle", "503", "502", "temporarily unavailable",
)


class ThrottleError(Exception):
    """Raised when a source throttled us (429/403/5xx) and retries were exhausted."""


class CircuitOpenError(Exception):
    """Raised when a source is in its cooldown window and the call is skipped."""


def _is_throttle_status(code: int) -> bool:
    return code == 429 or code == 403 or 500 <= code < 600


def _looks_throttled(exc: Exception) -> bool:
    if isinstance(exc, ThrottleError):
        return True
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "toomanyrequests" in name:
        return True
    text = str(exc).lower()
    return any(m in text for m in _THROTTLE_MARKERS)


class _Breaker:
    """Per-source circuit breaker.

    Thread-safe because the worker drives every source call through
    ``asyncio.to_thread``, so several threads can touch one breaker at once.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._consecutive = 0
        self._open_until = 0.0
        self._opens = 0  # successive re-opens, drives the exponential cooldown

    def check(self) -> None:
        with self._lock:
            remaining = self._open_until - time.monotonic()
        if remaining > 0:
            raise CircuitOpenError(
                f"{self.name} cooling down for {remaining:.0f}s more"
            )

    def on_success(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0
            self._opens = 0

    def on_throttle(self) -> float:
        """Record a throttled call; open the breaker once the threshold is hit.

        Returns the cooldown in seconds if this call opened the breaker, else 0.
        """
        with self._lock:
            self._consecutive += 1
            if self._consecutive < _FAIL_THRESHOLD:
                return 0.0
            self._opens += 1
            cooldown = min(_BASE_COOLDOWN * (2 ** (self._opens - 1)), _MAX_COOLDOWN)
            self._open_until = time.monotonic() + cooldown
            self._consecutive = 0
            return cooldown


_breakers: dict[str, _Breaker] = {}
_breakers_lock = threading.Lock()


def _breaker(name: str) -> _Breaker:
    with _breakers_lock:
        b = _breakers.get(name)
        if b is None:
            b = _Breaker(name)
            _breakers[name] = b
        return b


def _backoff(attempt: int) -> None:
    delay = min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF)
    delay += random.uniform(-_JITTER, _JITTER) * delay
    time.sleep(max(0.0, delay))


def _open_and_raise(breaker: _Breaker, source: str, last_exc: Exception) -> None:
    cooldown = breaker.on_throttle()
    if cooldown:
        throttle_log.warning(
            "circuit opened for %s: cooling down %.0fs after repeated throttling",
            source, cooldown,
        )
    if isinstance(last_exc, ThrottleError):
        raise last_exc
    raise ThrottleError(
        f"{source} throttled, exhausted {_MAX_ATTEMPTS} attempts: {last_exc}"
    ) from last_exc


def request(
    source: str,
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: Optional[httpx.Timeout] = None,
    follow_redirects: bool = False,
) -> httpx.Response:
    """GET ``url`` with retry/backoff on throttles and a per-source breaker.

    Raises ``CircuitOpenError`` if the source is cooling down, ``ThrottleError``
    if every attempt was throttled, or the underlying httpx error / non-throttle
    ``HTTPStatusError`` for hard failures (those are not retried and do not trip
    the breaker).
    """
    breaker = _breaker(source)
    breaker.check()

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with httpx.Client(timeout=timeout, headers=headers,
                              follow_redirects=follow_redirects) as client:
                resp = client.get(url, params=params)
            if _is_throttle_status(resp.status_code):
                last_exc = ThrottleError(f"{source} HTTP {resp.status_code}")
                throttle_log.warning(
                    "throttled by %s: HTTP %s (attempt %d/%d)",
                    source, resp.status_code, attempt + 1, _MAX_ATTEMPTS,
                )
                if attempt + 1 < _MAX_ATTEMPTS:
                    _backoff(attempt)
                continue
            resp.raise_for_status()
            breaker.on_success()
            return resp
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            # Transient network failures: retry like a throttle, count toward cooldown.
            last_exc = exc
            throttle_log.warning(
                "network error from %s: %s (attempt %d/%d)",
                source, exc, attempt + 1, _MAX_ATTEMPTS,
            )
            if attempt + 1 < _MAX_ATTEMPTS:
                _backoff(attempt)
            continue
        except httpx.HTTPStatusError:
            # Non-throttle HTTP error (e.g. 404): hard failure, propagate as-is.
            raise

    _open_and_raise(breaker, source, last_exc or ThrottleError(source))


@contextmanager
def stream(
    source: str,
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: Optional[httpx.Timeout] = None,
    follow_redirects: bool = True,
) -> Iterator[httpx.Response]:
    """Open a streaming GET, breaker-guarded, yielding the live ``httpx.Response``.

    For very large downloads (e.g. multi-GB IEX HIST captures) the body is read
    incrementally by the caller via ``resp.iter_bytes(...)``, so we deliberately
    do NOT retry mid-stream — a connection drop part-way is surfaced as a normal
    exception for the caller to abandon and retry from scratch. The per-source
    breaker still applies so a source that keeps failing connection setup backs
    off like any other.
    """
    breaker = _breaker(source)
    breaker.check()
    try:
        with httpx.Client(timeout=timeout, headers=headers,
                          follow_redirects=follow_redirects) as client:
            with client.stream("GET", url, params=params) as resp:
                if _is_throttle_status(resp.status_code):
                    cooldown = breaker.on_throttle()
                    if cooldown:
                        throttle_log.warning(
                            "circuit opened for %s: cooling down %.0fs (stream HTTP %s)",
                            source, cooldown, resp.status_code,
                        )
                    raise ThrottleError(f"{source} HTTP {resp.status_code}")
                resp.raise_for_status()
                breaker.on_success()
                yield resp
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        breaker.on_throttle()
        raise ThrottleError(f"{source} stream failed: {exc}") from exc


def guard(source: str, fn: Callable[..., T], *args) -> T:
    """Run a blocking callable with the same breaker + throttle-aware retry.

    For yfinance, which does its own HTTP, so throttling is inferred from the
    raised exception rather than a status code. Non-throttle exceptions (e.g. a
    symbol that genuinely has no data) propagate immediately without retrying or
    tripping the breaker, so one bad symbol never cools down the whole source.
    """
    breaker = _breaker(source)
    breaker.check()

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = fn(*args)
            breaker.on_success()
            return result
        except Exception as exc:  # noqa: BLE001
            if not _looks_throttled(exc):
                raise
            last_exc = exc
            throttle_log.warning(
                "throttled by %s: %s (attempt %d/%d)",
                source, exc, attempt + 1, _MAX_ATTEMPTS,
            )
            if attempt + 1 < _MAX_ATTEMPTS:
                _backoff(attempt)

    _open_and_raise(breaker, source, last_exc or ThrottleError(source))
