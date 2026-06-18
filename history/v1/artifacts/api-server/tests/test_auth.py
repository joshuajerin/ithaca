"""Auth / identity foundation test.

Exercises the firms+users+sessions identity layer end to end through the real
ASGI stack:

    python artifacts/api-server/tests/test_auth.py   # standalone
    pytest artifacts/api-server/tests/test_auth.py    # if pytest installed

It verifies the password crypto round-trips, and that signup -> current-user ->
protected-request -> logout behaves correctly, including that:
  * anonymous requests to a protected route are rejected with 401,
  * firm signup creates a firm + first admin and sets the session cookie,
  * a valid session resolves {user, firm, role} and unlocks the protected API,
  * duplicate email signup is rejected (409),
  * logout invalidates the session,
  * login with the right password works and the wrong password is rejected.

The session cookie is marked ``secure`` (correct for the https proxy/preview),
so the ``TestClient`` is pointed at an ``https://`` base URL — otherwise the
browser cookie jar would hold the cookie but never send it back over plain http
and every authed probe would spuriously 401.
"""
from __future__ import annotations

import os
import sys
import uuid

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)


def test_password_hash_round_trips():
    """A hashed password verifies against the original and rejects wrong input."""
    from app import auth

    hash_hex, salt_hex = auth.hash_password("password123")
    assert hash_hex != "password123", "password must not be stored in plaintext"
    assert auth.verify_password("password123", hash_hex, salt_hex) is True
    assert auth.verify_password("nope", hash_hex, salt_hex) is False
    # Distinct salts -> distinct hashes for the same password.
    other_hash, other_salt = auth.hash_password("password123")
    assert (hash_hex, salt_hex) != (other_hash, other_salt)


def test_session_token_hash_is_stable_and_opaque():
    """Token hashing is deterministic (lookup) but not the raw token (storage)."""
    from app import auth

    token = auth.new_session_token()
    assert token, "token must be non-empty"
    digest = auth.hash_token(token)
    assert digest != token, "stored token must be a hash, not the raw secret"
    assert digest == auth.hash_token(token), "hash must be deterministic for lookup"


def test_auth_flow_round_trip():
    """signup -> user -> protected -> dup -> logout -> login covers the contract."""
    from fastapi.testclient import TestClient

    from app import ai, auth, worker
    from app.main import app

    async def _noop_worker(*_args, **_kwargs):
        return None

    original_ai_available = ai.ai_available
    original_worker_start = worker.start
    original_worker_stop = worker.stop
    ai.ai_available = lambda: False  # type: ignore[assignment]
    worker.start = _noop_worker  # type: ignore[assignment]
    worker.stop = _noop_worker  # type: ignore[assignment]

    # The session cookie is ``secure``; use https so the TestClient jar replays it.
    email = f"founder-{uuid.uuid4().hex[:12]}@example.com"
    try:
        with TestClient(app, base_url="https://testserver") as client:
            # Public health route answers without a session.
            assert client.get("/api/healthz").status_code == 200

            # Protected route is rejected before login.
            anon = client.post(
                "/api/orchestrate",
                json={"query": "What is a Sortino ratio?", "sessionId": "default"},
            )
            assert anon.status_code == 401, (
                f"protected route must reject anon, got {anon.status_code}"
            )

            # Firm signup creates firm + first admin and sets the cookie.
            signup = client.post(
                "/api/auth/signup",
                json={
                    "firmName": "Helix Capital",
                    "name": "Dana Vega",
                    "email": email,
                    "password": "password123",
                },
            )
            assert signup.status_code == 200, (
                f"signup returned {signup.status_code}: {signup.text[:300]}"
            )
            body = signup.json()
            assert body["user"]["role"] == "admin", "first user must be firm admin"
            assert body["user"]["email"] == email
            assert body["firm"]["name"] == "Helix Capital"
            assert auth.COOKIE_NAME in client.cookies, "signup must set the session cookie"

            # A valid session resolves {user, firm, role}.
            me = client.get("/api/auth/user")
            assert me.status_code == 200, f"current-user failed: {me.text[:200]}"
            assert me.json()["firm"]["name"] == "Helix Capital"

            # Protected route now unlocked.
            authed = client.post(
                "/api/orchestrate",
                json={"query": "What is a Sortino ratio?", "sessionId": "default"},
            )
            assert authed.status_code == 200, (
                f"authed protected route failed: {authed.status_code}"
            )

            # Duplicate email is rejected.
            dup = client.post(
                "/api/auth/signup",
                json={
                    "firmName": "Other",
                    "name": "Someone",
                    "email": email,
                    "password": "password123",
                },
            )
            assert dup.status_code == 409, f"duplicate email must 409, got {dup.status_code}"

            # Logout invalidates the session.
            assert client.post("/api/auth/logout").status_code == 200
            assert client.get("/api/auth/user").status_code == 401, (
                "session must be dead after logout"
            )

            # Login with the right password works; wrong password is rejected.
            good = client.post(
                "/api/auth/login", json={"email": email, "password": "password123"}
            )
            assert good.status_code == 200, f"login failed: {good.text[:200]}"
            assert good.json()["user"]["role"] == "admin"

            bad = client.post(
                "/api/auth/login", json={"email": email, "password": "wrong"}
            )
            assert bad.status_code == 401, f"wrong password must 401, got {bad.status_code}"
    finally:
        ai.ai_available = original_ai_available  # type: ignore[assignment]
        worker.start = original_worker_start  # type: ignore[assignment]
        worker.stop = original_worker_stop  # type: ignore[assignment]


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
