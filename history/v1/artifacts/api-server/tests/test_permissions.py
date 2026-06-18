"""Role-based permissions enforcement test.

The server is the *authoritative* permission boundary: every sensitive/mutating
route declares the action it represents and rejects callers whose role is below
that action's minimum with a 403 — even for direct (UI-bypassing) API calls.
This suite proves both the matrix itself and the live HTTP enforcement:

    python artifacts/api-server/tests/test_permissions.py   # standalone
    pytest artifacts/api-server/tests/test_permissions.py    # if pytest installed

Like the auth suite, the session cookie is ``secure`` so the ``TestClient`` is
pointed at an ``https://`` base URL, and the AI / background worker are stubbed
so the test is deterministic and offline.
"""
from __future__ import annotations

import os
import sys
import uuid

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)


def test_permission_matrix_ranks_and_grants():
    """The matrix is monotonic in rank and fails closed on unknowns."""
    from app import permissions as p

    # read-only can do nothing sensitive; each tier strictly contains the lower.
    ro = set(p.allowed_actions("read-only"))
    an = set(p.allowed_actions("analyst"))
    tr = set(p.allowed_actions("trader"))
    ad = set(p.allowed_actions("admin"))
    assert ro == set(), "read-only must hold no privileged actions"
    assert ro < an < tr < ad, "each role must strictly extend the one below it"

    # Spot-check tier assignments from the authoritative matrix.
    assert p.can("analyst", "dashboard.save")
    assert not p.can("read-only", "dashboard.save")
    assert p.can("trader", "strategy.trade")
    assert not p.can("analyst", "strategy.trade")
    assert p.can("admin", "compliance.config")
    assert not p.can("trader", "compliance.config")
    assert p.can("admin", "feature.build")
    assert not p.can("trader", "feature.build")

    # Fails closed: unknown role or unknown action is never allowed.
    assert not p.can("superuser", "dashboard.save")
    assert not p.can("admin", "does.not.exist")

    # Denial message names the role and the minimum required role.
    msg = p.denial_message("read-only", "dashboard.save")
    assert "read-only" in msg and "analyst" in msg


def _stub_runtime():
    """Disable AI + background worker; return restore callable."""
    from app import ai, worker

    async def _noop_worker(*_args, **_kwargs):
        return None

    saved = (ai.ai_available, worker.start, worker.stop)
    ai.ai_available = lambda: False  # type: ignore[assignment]
    worker.start = _noop_worker  # type: ignore[assignment]
    worker.stop = _noop_worker  # type: ignore[assignment]

    def _restore():
        ai.ai_available, worker.start, worker.stop = saved  # type: ignore[assignment]

    return _restore


def _signup(client, role_label: str):
    """Create a fresh firm + admin and return the signup body."""
    email = f"{role_label}-{uuid.uuid4().hex[:12]}@example.com"
    resp = client.post(
        "/api/auth/signup",
        json={
            "firmName": f"Firm {uuid.uuid4().hex[:6]}",
            "name": "Test User",
            "email": email,
            "password": "password123",
        },
    )
    assert resp.status_code == 200, f"signup failed: {resp.status_code} {resp.text[:200]}"
    return resp.json()


def test_signup_admin_can_perform_privileged_actions():
    """The firm's first user is admin and the API honours every privileged route."""
    from fastapi.testclient import TestClient

    from app import auth
    from app.main import app

    restore = _stub_runtime()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            body = _signup(client, "admin")
            assert body["user"]["role"] == "admin"
            # Permission set is returned to the client and includes admin-only keys.
            perms = set(body.get("permissions") or [])
            assert "compliance.config" in perms and "feature.build" in perms
            assert auth.COOKIE_NAME in client.cookies

            # Admin may save a dashboard (analyst-tier action).
            saved = client.post(
                "/api/dashboards",
                json={
                    "name": f"Layout {uuid.uuid4().hex[:6]}",
                    "panels": [
                        {
                            "id": "p1",
                            "type": "note",
                            "title": "Note",
                            "layout": {"x": 0, "y": 0, "w": 4, "h": 4},
                            "status": "ok",
                            "data": {"text": "hi"},
                        }
                    ],
                },
            )
            assert saved.status_code == 200, (
                f"admin dashboard save should succeed, got {saved.status_code}: {saved.text[:200]}"
            )

            # Admin may add a compliance restriction (admin-tier action).
            comp = client.post("/api/compliance/restricted", json={"symbol": "AAPL"})
            assert comp.status_code == 200, (
                f"admin compliance config should succeed, got {comp.status_code}: {comp.text[:200]}"
            )
    finally:
        restore()


def test_lower_roles_are_blocked_at_the_api_even_bypassing_the_ui():
    """read-only and analyst get 403 on actions above their tier via direct API calls."""
    from fastapi.testclient import TestClient

    from app import auth, auth_store
    from app.main import app

    restore = _stub_runtime()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            # Bootstrap a firm (admin), then create lower-role users in that firm
            # and drive each one's own session directly against the API.
            admin = _signup(client, "boot")
            firm_id = admin["firm"]["id"]

            def _make_user(role: str):
                email = f"{role}-{uuid.uuid4().hex[:12]}@example.com"
                pw_hash, pw_salt = auth.hash_password("password123")
                auth_store.create_user(
                    firm_id=firm_id,
                    name=f"{role} user",
                    email=email,
                    role=role,
                    password_hash=pw_hash,
                    password_salt=pw_salt,
                )
                return email

            read_only_email = _make_user("read-only")
            analyst_email = _make_user("analyst")

            # Each lower-role user logs in on a clean client (own cookie jar).
            def _client_for(email: str):
                c = TestClient(app, base_url="https://testserver")
                r = c.post("/api/auth/login", json={"email": email, "password": "password123"})
                assert r.status_code == 200, f"login failed for {email}: {r.text[:200]}"
                return c, r.json()

            ro_client, ro_body = _client_for(read_only_email)
            an_client, an_body = _client_for(analyst_email)

            assert ro_body["user"]["role"] == "read-only"
            assert (ro_body.get("permissions") or []) == [], (
                "read-only must receive an empty permission set"
            )
            assert "dashboard.save" in (an_body.get("permissions") or [])

            dashboard_payload = {
                "name": "Blocked Layout",
                "panels": [
                    {
                        "id": "p1",
                        "type": "note",
                        "title": "Note",
                        "layout": {"x": 0, "y": 0, "w": 4, "h": 4},
                        "status": "ok",
                        "data": {"text": "hi"},
                    }
                ],
            }

            # read-only is blocked from an analyst-tier action (dashboard save).
            ro_save = ro_client.post("/api/dashboards", json=dashboard_payload)
            assert ro_save.status_code == 403, (
                f"read-only dashboard save must 403, got {ro_save.status_code}: {ro_save.text[:200]}"
            )

            # read-only is blocked from a watchlist edit too.
            ro_watch = ro_client.post("/api/watchlist", json={"symbol": "AAPL"})
            assert ro_watch.status_code == 403, (
                f"read-only watchlist edit must 403, got {ro_watch.status_code}"
            )

            # analyst CAN save a dashboard (their tier) ...
            an_save = an_client.post("/api/dashboards", json=dashboard_payload)
            assert an_save.status_code == 200, (
                f"analyst dashboard save should succeed, got {an_save.status_code}: {an_save.text[:200]}"
            )

            # ... but analyst is blocked from a trader-tier action (create strategy) ...
            an_strat = an_client.post(
                "/api/strategies",
                json={"name": "S", "signal": "momentum", "symbols": ["AAPL"]},
            )
            assert an_strat.status_code == 403, (
                f"analyst strategy create must 403, got {an_strat.status_code}: {an_strat.text[:200]}"
            )

            # ... and from an admin-tier action (compliance config + build feature).
            an_comp = an_client.post("/api/compliance/restricted", json={"symbol": "AAPL"})
            assert an_comp.status_code == 403, (
                f"analyst compliance config must 403, got {an_comp.status_code}"
            )
            an_feat = an_client.post("/api/feature-request", json={"description": "x"})
            assert an_feat.status_code == 403, (
                f"analyst feature build must 403, got {an_feat.status_code}"
            )

            ro_client.close()
            an_client.close()
    finally:
        restore()


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
