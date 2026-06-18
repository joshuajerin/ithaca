"""Firm Admin Console test.

Exercises the multi-tenant admin surface end to end through the real ASGI stack:

    python artifacts/api-server/tests/test_admin.py   # standalone
    pytest artifacts/api-server/tests/test_admin.py    # if pytest installed

It verifies, against a freshly signed-up firm whose first user is the admin:
  * /admin/members returns the firm roster + billing/seat view,
  * inviting a teammate yields a one-time token whose invitation previews,
  * accepting the invite creates the user inside the SAME firm and signs them in,
  * a non-admin (the invited trader) is denied at every /admin route (403),
  * deactivating a user kills their session and blocks future requests (401),
  * the last active admin cannot be demoted, deactivated, removed, nor can an
    admin act on their own account,
  * editing firm name, risk limits and the kill switch all persist,
  * firms are isolated: one firm's admin cannot touch another firm's user,
  * every admin action lands in the firm-scoped audit trail.

The session cookie is ``secure``; the TestClient uses an https base URL so the
cookie jar replays it (otherwise every authed probe spuriously 401s).
"""
from __future__ import annotations

import os
import sys
import uuid

_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)


def _stub_runtime():
    """Disable AI + background worker so the app boots deterministically in tests."""
    from app import ai, worker

    async def _noop_worker(*_args, **_kwargs):
        return None

    originals = (ai.ai_available, worker.start, worker.stop)
    ai.ai_available = lambda: False  # type: ignore[assignment]
    worker.start = _noop_worker  # type: ignore[assignment]
    worker.stop = _noop_worker  # type: ignore[assignment]

    def restore():
        ai.ai_available, worker.start, worker.stop = originals  # type: ignore[assignment]

    return restore


def _signup(client, firm: str, email: str):
    res = client.post(
        "/api/auth/signup",
        json={"firmName": firm, "name": "Admin One", "email": email, "password": "password123"},
    )
    assert res.status_code == 200, f"signup failed: {res.text[:300]}"
    return res.json()


def test_admin_console_end_to_end():
    from fastapi.testclient import TestClient

    from app import auth
    from app.main import app

    restore = _stub_runtime()
    admin_email = f"admin-{uuid.uuid4().hex[:12]}@example.com"
    try:
        with TestClient(app, base_url="https://testserver") as admin, \
                TestClient(app, base_url="https://testserver") as invitee, \
                TestClient(app, base_url="https://testserver") as other:

            # --- firm + admin --------------------------------------------------
            me = _signup(admin, "Helix Capital", admin_email)
            assert me["user"]["role"] == "admin"
            admin_id = me["user"]["id"]

            # --- members + billing view ---------------------------------------
            members = admin.get("/api/admin/members")
            assert members.status_code == 200, members.text[:300]
            mp = members.json()
            assert mp["billing"]["seatsUsed"] == 1
            assert mp["selfId"] == admin_id
            assert any(m["id"] == admin_id and m["role"] == "admin" for m in mp["members"])
            assert "admin" in mp["roles"] and "read-only" in mp["roles"]

            # --- invite a teammate --------------------------------------------
            invite_email = f"trader-{uuid.uuid4().hex[:12]}@example.com"
            inv = admin.post(
                "/api/admin/invitations",
                json={"email": invite_email, "name": "Trader Two", "role": "trader"},
            )
            assert inv.status_code == 200, inv.text[:300]
            token = inv.json()["inviteToken"]
            assert token
            assert inv.json()["members"]["billing"]["pendingInvites"] == 1

            # Public preview of the invitation reflects the firm + role.
            prev = invitee.get(f"/api/auth/invitation?token={token}")
            assert prev.status_code == 200, prev.text[:300]
            assert prev.json()["firmName"] == "Helix Capital"
            assert prev.json()["role"] == "trader"
            assert prev.json()["email"] == invite_email

            # --- accept the invite (joins the same firm, signs in) ------------
            acc = invitee.post(
                "/api/auth/accept-invite",
                json={"token": token, "name": "Trader Two", "password": "password123"},
            )
            assert acc.status_code == 200, acc.text[:300]
            invitee_body = acc.json()
            assert invitee_body["user"]["role"] == "trader"
            assert invitee_body["firm"]["name"] == "Helix Capital"
            invitee_id = invitee_body["user"]["id"]
            assert auth.COOKIE_NAME in invitee.cookies, "accept-invite must set a session cookie"

            # The token is one-time: a second accept (or preview) is invalid.
            assert invitee.get(f"/api/auth/invitation?token={token}").status_code == 404

            # Seat count now reflects the joined member.
            assert admin.get("/api/admin/members").json()["billing"]["seatsUsed"] == 2

            # --- non-admin is denied everywhere -------------------------------
            assert invitee.get("/api/admin/members").status_code == 403
            assert invitee.get("/api/admin/limits").status_code == 403
            assert invitee.get("/api/admin/audit").status_code == 403
            assert invitee.post("/api/admin/firm", json={"name": "Hostile"}).status_code == 403
            assert invitee.post(
                "/api/admin/invitations", json={"email": "x@y.com", "role": "trader"}
            ).status_code == 403

            # --- last-admin + self guards -------------------------------------
            # Admin cannot demote themselves (would zero out admins).
            demote = admin.post(f"/api/admin/users/{admin_id}/role", json={"role": "trader"})
            assert demote.status_code == 400, demote.text[:200]
            # Admin cannot deactivate or remove their own account.
            assert admin.post(f"/api/admin/users/{admin_id}/active", json={"active": False}).status_code == 400
            assert admin.delete(f"/api/admin/users/{admin_id}").status_code == 400

            # --- role change on a real member ---------------------------------
            promote = admin.post(f"/api/admin/users/{invitee_id}/role", json={"role": "analyst"})
            assert promote.status_code == 200, promote.text[:200]
            assert any(
                m["id"] == invitee_id and m["role"] == "analyst"
                for m in promote.json()["members"]["members"]
            )

            # --- deactivation kills the session + blocks the user -------------
            # Invitee is live before deactivation.
            assert invitee.get("/api/auth/user").status_code == 200
            deact = admin.post(f"/api/admin/users/{invitee_id}/active", json={"active": False})
            assert deact.status_code == 200, deact.text[:200]
            # Their existing session is now dead, and re-login is refused.
            assert invitee.get("/api/auth/user").status_code == 401, "deactivated session must die"
            relog = invitee.post(
                "/api/auth/login", json={"email": invite_email, "password": "password123"}
            )
            assert relog.status_code == 403, f"deactivated user must not log in, got {relog.status_code}"

            # --- firm isolation -----------------------------------------------
            other_email = f"rival-{uuid.uuid4().hex[:12]}@example.com"
            _signup(other, "Rival LLP", other_email)
            # Rival admin cannot act on Helix's user.
            cross = other.post(f"/api/admin/users/{invitee_id}/role", json={"role": "trader"})
            assert cross.status_code == 404, f"cross-firm action must 404, got {cross.status_code}"

            # --- firm profile edit --------------------------------------------
            ren = admin.post("/api/admin/firm", json={"name": "Helix Capital Partners"})
            assert ren.status_code == 200, ren.text[:200]
            assert ren.json()["firm"]["name"] == "Helix Capital Partners"

            # --- risk limits + kill switch ------------------------------------
            limits = admin.get("/api/admin/limits")
            assert limits.status_code == 200
            assert any(d["key"] == "maxLeverage" for d in limits.json()["defs"])
            setl = admin.post("/api/admin/limits", json={"limits": {"maxLeverage": 1.5}})
            assert setl.status_code == 200, setl.text[:200]
            assert setl.json()["limits"]["maxLeverage"] == 1.5

            kill = admin.post("/api/admin/kill-switch", json={"on": True, "reason": "drill"})
            assert kill.status_code == 200, kill.text[:200]
            assert kill.json()["killSwitch"] is True
            assert admin.get("/api/admin/limits").json()["killSwitch"] is True
            assert admin.post("/api/admin/kill-switch", json={"on": False}).json()["killSwitch"] is False

            # --- audit trail captures the admin actions -----------------------
            audit = admin.get("/api/admin/audit?limit=100")
            assert audit.status_code == 200, audit.text[:200]
            actions = {e["action"] for e in audit.json()["entries"]}
            for expected in {
                "admin.invite",
                "admin.user.role",
                "admin.user.active",
                "admin.firm.update",
                "admin.limits.update",
                "admin.kill_switch",
            }:
                assert expected in actions, f"missing audit action {expected}; saw {sorted(actions)}"
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
