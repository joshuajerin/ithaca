"""Firm-wide audit trail test.

Exercises the unified, user-attributed, append-only audit log end to end through
the real ASGI stack:

    python artifacts/api-server/tests/test_audit.py   # standalone
    pytest artifacts/api-server/tests/test_audit.py    # if pytest installed

It verifies that:
  * consequential actions are recorded and attributed to the acting user,
  * the admin-only GET /api/audit returns entries + actor/category facets,
  * filters (category, user) narrow the result set,
  * a non-admin is refused (403) AND the denied attempt is itself audited,
  * the audit trail is firm-scoped (one firm never sees another's entries),
  * there is NO HTTP path to clear or edit the trail (append-only contract).

The session cookie is ``secure`` so the TestClient is pointed at https — see
test_auth.py for the rationale.
"""
from __future__ import annotations

import os
import sys
import uuid

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)


def _silence_worker_and_ai():
    """Return (restore_fn) after stubbing the background worker + AI so the app
    boots deterministically inside the TestClient lifespan."""
    from app import ai, worker

    async def _noop(*_a, **_k):
        return None

    orig = (ai.ai_available, worker.start, worker.stop)
    ai.ai_available = lambda: False  # type: ignore[assignment]
    worker.start = _noop  # type: ignore[assignment]
    worker.stop = _noop  # type: ignore[assignment]

    def restore():
        ai.ai_available, worker.start, worker.stop = orig  # type: ignore[assignment]

    return restore


def _signup(client, firm_name="Helix Capital"):
    email = f"founder-{uuid.uuid4().hex[:12]}@example.com"
    res = client.post(
        "/api/auth/signup",
        json={"firmName": firm_name, "name": "Dana Vega", "email": email, "password": "password123"},
    )
    assert res.status_code == 200, f"signup failed: {res.text[:300]}"
    return email, res.json()


def test_audit_trail_end_to_end():
    from fastapi.testclient import TestClient

    from app import auth, auth_store
    from app.main import app

    restore = _silence_worker_and_ai()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            # --- signup writes an attributed auth entry ---------------------
            email, body = _signup(client)
            firm_id = body["firm"]["id"]
            admin_name = body["user"]["name"]

            # A consequential config change while authenticated.
            sym = f"ZZ{uuid.uuid4().hex[:3].upper()}"
            r = client.post("/api/compliance/restricted", json={"symbol": sym})
            assert r.status_code == 200, f"restrict add failed: {r.text[:200]}"

            # --- admin can read the firm-wide trail ------------------------
            audit = client.get("/api/audit")
            assert audit.status_code == 200, f"audit fetch failed: {audit.text[:200]}"
            payload = audit.json()
            entries = payload["entries"]
            assert entries, "expected at least the signup + config entries"

            cats = {e["category"] for e in entries}
            assert "auth" in cats, f"signup should be audited, saw {cats}"
            assert "config" in cats, f"config change should be audited, saw {cats}"

            # Every entry is attributed to a real person (not unattributed).
            assert all(e["actorName"] for e in entries), "entries must name an actor"
            signup_entry = next(e for e in entries if e["action"] == "signup")
            assert signup_entry["actorName"] == admin_name

            config_entry = next(e for e in entries if e["category"] == "config")
            assert config_entry["actorName"] == admin_name, "config change must attribute to admin"
            assert sym in (config_entry.get("target") or ""), "config target should be the symbol"

            # Facets are populated for the viewer's dropdowns.
            assert any(a["name"] == admin_name for a in payload["actors"])
            assert "auth" in payload["categories"] and "config" in payload["categories"]

            # --- filters narrow the set ------------------------------------
            only_config = client.get("/api/audit", params={"category": "config"}).json()["entries"]
            assert only_config, "category filter should still return the config entry"
            assert all(e["category"] == "config" for e in only_config)

            by_user = client.get(
                "/api/audit", params={"user": body["user"]["id"]}
            ).json()["entries"]
            assert by_user and all(e["actorUserId"] == body["user"]["id"] for e in by_user)

            # --- the trail is append-only: no clear/edit endpoint ----------
            killed = client.delete("/api/compliance/audit")
            assert killed.status_code in (404, 405), (
                f"audit must not be clearable over HTTP, got {killed.status_code}"
            )

            # --- a non-admin is refused AND the denial is audited ----------
            pw_hash, pw_salt = auth.hash_password("password123")
            analyst_email = f"analyst-{uuid.uuid4().hex[:10]}@example.com"
            analyst = auth_store.create_user(
                firm_id, analyst_email, "Lee Analyst", "analyst", pw_hash, pw_salt
            )
            client.post("/api/auth/logout")
            login = client.post(
                "/api/auth/login", json={"email": analyst_email, "password": "password123"}
            )
            assert login.status_code == 200

            denied = client.get("/api/audit")
            assert denied.status_code == 403, f"non-admin must be refused, got {denied.status_code}"

            # Back in as the admin: the denied attempt is on the trail.
            client.post("/api/auth/logout")
            client.post("/api/auth/login", json={"email": email, "password": "password123"})
            after = client.get("/api/audit").json()["entries"]
            denials = [e for e in after if e["action"] == "permission_denied"]
            assert denials, "the refused admin-only access must be audited"
            assert denials[0]["actorName"] == "Lee Analyst"
            assert denials[0]["decision"] == "blocked"

            # --- isolation: a second firm sees only its own entries --------
            client.post("/api/auth/logout")
            _signup(client, firm_name="Rival Partners")
            rival_audit = client.get("/api/audit").json()["entries"]
            assert all(e["category"] != "config" or sym not in (e.get("target") or "")
                       for e in rival_audit), "rival firm must not see Helix's config change"
            rival_actors = {a["name"] for a in client.get("/api/audit").json()["actors"]}
            assert "Lee Analyst" not in rival_actors, "actor facet must be firm-scoped"
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
