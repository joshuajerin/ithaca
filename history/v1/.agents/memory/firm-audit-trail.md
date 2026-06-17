---
name: Firm-wide audit trail
description: How the unified user-attributed append-only audit log is built on top of the compliance audit plumbing.
---

# Firm-wide audit trail

The pre-trade compliance audit table (`compliance_audit`) was generalized into a
unified firm-scoped, user-attributed, append-only audit log. It is NOT a new
table — the same `compliance_store` plumbing carries every category.

**Categories** (the `category` column groups entries): `compliance` (pre-trade
gate decisions), `trade` (rebalances), `strategy` (create/transition), `config`
(compliance config changes), `dashboard`, `alert`, `feature` (build/delete),
`auth` (signup/login/login_failed/logout/permission_denied), `admin` (firm
settings). `append_audit(category=...)` defaults to `compliance` so the existing
gate calls keep working unchanged.

**Actor attribution is automatic.** `tenant.set_current_actor(...)` is called in
`require_identity` right after `set_current_firm`, so every write (even the deep
pre-trade gate) attributes to the acting user via `tenant.current_actor()` with
no plumbing. The contextvar copies into the sync threadpool the same way firm
does. No resolvable actor → recorded as `system` (e.g. worker-scheduled
rebalances, which run `strategy.rebalance` directly, not the HTTP endpoint).

**Public auth router has no identity context**, so `_audit_auth(...)` in main.py
passes `firm_id` + `actor_*` explicitly. A failed login is only audited when the
email maps to a known user (otherwise there is no firm to scope it to).

**Append-only is enforced by absence**: there is deliberately NO HTTP path to
clear/edit the trail. The old `DELETE /api/compliance/audit` endpoint was
removed; `compliance_store.clear_audit()` remains for test setup only.

**Compliance panel** now shows only gate decisions: `build_compliance` calls
`list_audit(40, category="compliance")`. The full firm-wide log lives behind the
admin-only `GET /api/audit` (require_role("admin"), filters user/category/action/
since/until) which also returns `actors` + `categories` facets for the viewer
dropdowns. Frontend: `AuditLogModal.tsx` raw-fetches `/api/audit` (no codegen),
gated in Terminal header by `identity?.user.role === "admin"`.

**Why:** keeps one storage/contract for all consequential actions and preserves
the pre-trade gate behavior while making the whole system answer "who did what,
when". Test: `tests/test_audit.py` (standalone, https TestClient, create a
non-admin via `auth_store.create_user` to exercise permission_denied + isolation).
