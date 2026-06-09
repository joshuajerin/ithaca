"""Security-hardening tests.

Runnable two ways:
    python artifacts/api-server/tests/test_security.py   # standalone
    pytest artifacts/api-server/tests/test_security.py    # if pytest installed

Covers the controls added by the security-hardening pass:
  * the sliding-window rate limiter (unit-level, via ``security._check``),
  * the CORS allow-list builder (never a wildcard),
  * security headers on every response (incl. anonymous + error responses),
  * the request body-size cap (413),
  * code-execution containment: the AI feature-builder endpoints require the
    ``admin`` role and honour the per-firm code-execution kill-switch.

The session cookie is ``secure``; the TestClient is pointed at an ``https`` base
URL so its cookie jar replays the cookie on later requests.
"""
from __future__ import annotations

import os
import sys
import uuid

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)


def test_rate_limiter_allows_then_blocks():
    """The core check permits ``limit`` hits then raises 429 with Retry-After."""
    from fastapi import HTTPException

    from app import security

    security.reset_rate_limits()
    bucket, ip, limit, window = "unit-test", "1.2.3.4", 3, 60.0
    for _ in range(limit):
        security._check(bucket, ip, limit, window)  # under the limit -> ok
    try:
        security._check(bucket, ip, limit, window)  # one over -> blocked
        raise AssertionError("expected the rate limiter to raise on the 4th hit")
    except HTTPException as exc:
        assert exc.status_code == 429, f"expected 429, got {exc.status_code}"
        assert "Retry-After" in (exc.headers or {}), "429 must carry Retry-After"
    # A different IP has its own budget.
    security._check(bucket, "9.9.9.9", limit, window)
    security.reset_rate_limits()


def test_allowed_origins_is_never_wildcard():
    """The CORS allow-list is an explicit origin list, never ``*``."""
    from app import security

    prev_domains = os.environ.get("REPLIT_DOMAINS")
    prev_dev = os.environ.get("REPLIT_DEV_DOMAIN")
    try:
        os.environ["REPLIT_DOMAINS"] = "app.example.com, other.example.com"
        os.environ.pop("REPLIT_DEV_DOMAIN", None)
        origins = security.allowed_origins()
        assert "*" not in origins, "CORS must never allow a wildcard origin"
        assert "https://app.example.com" in origins
        assert "https://other.example.com" in origins
    finally:
        if prev_domains is None:
            os.environ.pop("REPLIT_DOMAINS", None)
        else:
            os.environ["REPLIT_DOMAINS"] = prev_domains
        if prev_dev is not None:
            os.environ["REPLIT_DEV_DOMAIN"] = prev_dev


def _client():
    from fastapi.testclient import TestClient

    from app import ai, worker
    from app.main import app

    async def _noop_worker(*_a, **_k):
        return None

    ai.ai_available = lambda: False  # type: ignore[assignment]
    worker.start = _noop_worker  # type: ignore[assignment]
    worker.stop = _noop_worker  # type: ignore[assignment]
    return TestClient(app, base_url="https://testserver")


def test_security_headers_on_every_response():
    """HSTS / nosniff / frame-deny / CSP are present, even on a 401."""
    with _client() as client:
        # Anonymous, rejected request still gets the headers (middleware wraps all).
        resp = client.get("/api/skills")
        assert resp.status_code == 401
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "max-age" in (resp.headers.get("Strict-Transport-Security") or "")
        assert "default-src 'none'" in (resp.headers.get("Content-Security-Policy") or "")
        assert resp.headers.get("Referrer-Policy") == "no-referrer"


def test_body_size_limit_rejects_oversized_request():
    """A request whose Content-Length exceeds the cap is rejected with 413."""
    from app import security

    with _client() as client:
        big = "x" * (security.MAX_BODY_BYTES + 1)
        resp = client.post("/api/auth/login", content=big,
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 413, f"expected 413, got {resp.status_code}"


def test_feature_building_requires_admin_and_firm_toggle():
    """Code-execution endpoints enforce admin role + the per-firm kill-switch."""
    from app import auth, auth_store, firm_settings

    with _client() as client:
        # First user of a firm is an admin.
        email = f"sec-{uuid.uuid4().hex[:12]}@example.com"
        signup = client.post(
            "/api/auth/signup",
            json={"firmName": "Sec Co", "name": "Admin", "email": email,
                  "password": "password123"},
        )
        assert signup.status_code == 200, signup.text[:200]
        firm_id = signup.json()["firm"]["id"]

        # Admin can read settings and sees it manageable + enabled by default.
        s = client.get("/api/firm/settings")
        assert s.status_code == 200
        assert s.json()["codegenEnabled"] is True
        assert s.json()["canManage"] is True

        # Admin disables the code-execution kill-switch -> feature build is 403.
        off = client.post("/api/firm/settings", json={"codegenEnabled": False})
        assert off.status_code == 200 and off.json()["codegenEnabled"] is False
        blocked = client.post("/api/feature-request", json={"description": "a gauge"})
        assert blocked.status_code == 403, (
            f"disabled firm must block builds, got {blocked.status_code}"
        )

        # Re-enable; now a non-admin user of the same firm must be refused by role.
        client.post("/api/firm/settings", json={"codegenEnabled": True})
        # Create a non-admin user directly in the store and log in as them.
        pw_hash, pw_salt = auth.hash_password("password123")
        analyst_email = f"analyst-{uuid.uuid4().hex[:12]}@example.com"
        auth_store.create_user(
            firm_id=firm_id, email=analyst_email, name="Analyst",
            role="analyst", password_hash=pw_hash, password_salt=pw_salt,
        )
        client.post("/api/auth/logout")
        login = client.post(
            "/api/auth/login", json={"email": analyst_email, "password": "password123"}
        )
        assert login.status_code == 200 and login.json()["user"]["role"] == "analyst"

        # Analyst can read settings but cannot manage or build.
        s2 = client.get("/api/firm/settings")
        assert s2.status_code == 200 and s2.json()["canManage"] is False
        assert client.post("/api/firm/settings", json={"codegenEnabled": False}).status_code == 403
        assert client.post("/api/feature-request", json={"description": "x"}).status_code == 403
        assert client.delete("/api/features/anything").status_code == 403

    firm_settings.reset_for_tests()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
