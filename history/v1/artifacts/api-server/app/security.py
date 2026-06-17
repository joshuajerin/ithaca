"""Transport- and application-layer security primitives.

This module centralizes the institutional hardening controls that wrap the
FastAPI app:

* :func:`allowed_origins` — derive the CORS allow-list from the Replit-provided
  domain env vars instead of the previous wildcard, so the credentialed API only
  accepts requests from the known terminal origin(s).
* :class:`SecurityHeadersMiddleware` — attach HSTS, anti-sniffing, anti-framing,
  referrer, permissions-policy and a JSON-API content-security-policy to every
  response.
* :class:`BodySizeLimitMiddleware` — reject oversized request bodies with 413
  before they reach a handler.
* :func:`rate_limit` — a per-client, per-bucket sliding-window rate limiter
  exposed as a FastAPI dependency, used on auth + expensive AI endpoints.

The rate limiter and size limit are in-process (single-node) controls. They are
defense-in-depth for cost/abuse, not a substitute for an edge WAF; this is called
out in ``SECURITY.md``.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

# --------------------------------------------------------------------------- #
# CORS allow-list
# --------------------------------------------------------------------------- #
def allowed_origins() -> List[str]:
    """Build the CORS origin allow-list from the Replit domain env vars.

    The terminal and this API are served same-origin behind the path-based
    proxy, so browsers do not normally trigger a CORS preflight. We still pin an
    explicit allow-list (never ``*``) so that ``allow_credentials=True`` is safe
    and any genuinely cross-origin caller is rejected by the browser.

    ``REPLIT_DOMAINS`` may be a comma-separated list; ``REPLIT_DEV_DOMAIN`` is the
    single dev preview host. Bare hostnames are promoted to ``https://`` origins.
    """
    raw: List[str] = []
    domains = os.environ.get("REPLIT_DOMAINS", "")
    if domains:
        raw.extend(part.strip() for part in domains.split(",") if part.strip())
    dev = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    if dev:
        raw.append(dev)

    origins: List[str] = []
    for entry in raw:
        if entry.startswith("http://") or entry.startswith("https://"):
            origin = entry.rstrip("/")
        else:
            origin = f"https://{entry.rstrip('/')}"
        if origin not in origins:
            origins.append(origin)
    return origins


# --------------------------------------------------------------------------- #
# Security headers
# --------------------------------------------------------------------------- #
# A JSON API never renders HTML, loads scripts, or is framed, so the strictest
# CSP is appropriate: deny everything and forbid framing. (The terminal SPA is a
# separate artifact with its own document; this policy applies to API responses.)
_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_HSTS = "max-age=63072000; includeSubDomains; preload"
_PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=(), payment=()"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach transport/anti-sniffing/anti-framing headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        headers = response.headers
        headers.setdefault("Strict-Transport-Security", _HSTS)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Content-Security-Policy", _CSP)
        return response


# --------------------------------------------------------------------------- #
# Request body size limit
# --------------------------------------------------------------------------- #
# Generous enough for a short base64 voice clip on /transcribe, tight enough to
# reject a body-bomb. Applied to every request via Content-Length.
MAX_BODY_BYTES = int(os.environ.get("TERMINAL_MAX_BODY_BYTES", str(16 * 1024 * 1024)))


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body exceeds :data:`MAX_BODY_BYTES`."""

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length"}
                )
        return await call_next(request)


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
# (bucket, client_ip) -> monotonic timestamps of recent hits within the window.
_hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Behind the Replit proxy the real client is the
    first hop of ``X-Forwarded-For``; fall back to the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else "unknown"


def _rate_disabled() -> bool:
    """Disable limiting under the test runner and via an explicit override.

    Standalone single-file test runs stay well under any limit, but a combined
    ``pytest`` session signs up/queries many times from one synthetic client IP;
    ``PYTEST_CURRENT_TEST`` lets those pass without weakening production limits.
    """
    return bool(
        os.environ.get("TERMINAL_RATELIMIT_DISABLED") == "1"
        or os.environ.get("PYTEST_CURRENT_TEST")
    )


def _check(bucket: str, ip: str, limit: int, window: float) -> None:
    """Core sliding-window check. Raises 429 when the limit is exceeded.

    Kept separate from the dependency wrapper (which honours the test/override
    disable) so it can be unit-tested deterministically.
    """
    key = (bucket, ip)
    now = time.monotonic()
    cutoff = now - window
    with _lock:
        dq = _hits[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            retry = max(1, int(window - (now - dq[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail="Too many requests — slow down and try again shortly.",
                headers={"Retry-After": str(retry)},
            )
        dq.append(now)


def rate_limit(bucket: str, limit: int, window: float = 60.0):
    """Return a FastAPI dependency enforcing ``limit`` hits per ``window`` seconds
    per client IP for the named ``bucket``."""

    def dependency(request: Request) -> None:
        if _rate_disabled():
            return
        _check(bucket, _client_ip(request), limit, window)

    return dependency


def reset_rate_limits() -> None:
    """Clear all rate-limit state (test helper)."""
    with _lock:
        _hits.clear()
