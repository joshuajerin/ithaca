---
name: Firm Admin Console
description: Multi-tenant admin self-service surface (users/invites/limits/firm/billing) and its server-side guards.
---

# Firm Admin Console

Admin-only self-service area, firm-scoped, server-authoritative (`require_role("admin")`).
Routes live in main.py and return plain dicts (no openapi codegen); the frontend uses raw
`fetch("/api/admin/*")` (AdminConsoleModal), same precedent as FeatureRequestModal.

## Invariants that bit us / must hold
- **Deactivation is enforced in TWO places, not one.** `require_identity` rejects an existing
  session of a deactivated user (401), but `/auth/login` must ALSO reject re-login — otherwise a
  deactivated user just logs back in. Login returns **403 "Your account has been deactivated."**
  (distinct from 401 bad-credentials) and the check reads `user.get("active", True)`.
- **Last-active-admin guard** on role-change / deactivate / remove: never let a firm reach zero
  active admins (`count_active_admins(firm_id) <= 1` → 400).
- **Self guards**: an admin cannot demote / deactivate / remove their own account (400).
- **Firm isolation**: `_require_member` asserts the target user belongs to the actor's firm →
  cross-firm action returns **404** (not 403), so you can't probe other firms' user ids.
- Deactivating a user calls `delete_user_sessions` to kick them immediately.

## Invitations
- One-time token: raw via `auth.new_session_token()`, stored as `auth.hash_token(token)`. The
  invite link is `?invite=<rawtoken>` on the terminal path.
- Public `GET /auth/invitation?token=` previews {firmName,email,role}; `POST /auth/accept-invite`
  creates the user in the inviting firm, sets the session cookie, audits via `_admin_audit_system`
  (no admin actor). After accept the token is consumed → preview/accept again is 404.
- AuthScreen splits into LoginScreen vs AcceptInviteScreen (chosen by `?invite=` in the URL);
  useAuth.acceptInvite posts raw (not in generated client) and reuses the AuthIdentity shape.

## Reuse
- Risk limits / kill switch / audit reuse `compliance_store` (get_config/set_limits/
  set_kill_switch/list_audit) + `engine.compliance.LIMIT_DEFS/DEFAULT_LIMITS`. Admin actions are
  audited through `compliance_store.append_audit(decision="ok")` via `_admin_audit`.
- Billing is read-only: plan/seats on the firms row; seatsUsed = active members.

## Test
- tests/test_admin.py is standalone (no pytest); stub ai.ai_available=False + worker.start/stop;
  THREE TestClients (admin/invitee/other) at `base_url="https://testserver"` (secure cookie).
  Run with the MAX_PATH env wrapper. Not wired into any registered validation by design.
