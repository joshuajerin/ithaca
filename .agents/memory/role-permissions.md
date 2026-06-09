---
name: Role-based permissions enforcement
description: How sensitive-action authorization works — single authoritative matrix, server-enforced via a dependency, UI gated for convenience only.
---

# Role-based permissions

The permission matrix lives in ONE authoritative place: `app/permissions.py`.
- `ROLE_RANK`: read-only(0) < analyst(1) < trader(2) < admin(3).
- `ACTIONS`: maps `action_key -> (min_role, label)`.
- Helpers `can/meets/min_role_for/label_for/allowed_actions/denial_message` all
  **fail closed** — unknown role or unknown action returns False / not-allowed.

**Why a single matrix:** the task required defining permissions in exactly one
place so server enforcement and UI gating can never drift.

## Server is authoritative
`main.py` has a `require_permission(action)` dependency factory. Sensitive routes
declare `dependencies=[Depends(require_permission("<action>"))]`. It re-uses
`require_identity` (FastAPI caches it per-request, so the session resolves once)
and raises 403 with `permissions.denial_message(...)` on violation — even for
direct/hand-crafted API calls that bypass the UI.

## Tier assignments (judgment calls baked into ACTIONS)
- analyst: dashboard.save/delete, watchlist.edit, dcf.save, alert.manage
- trader: + strategy.manage, strategy.trade, template.use
- admin: + compliance.config, feature.build

`feature.build` is admin-only — a deliberate choice (self-building features mutate
server code at runtime), not spelled out in the task's role tiers.

## Client surface
`AuthIdentity` now carries `permissions: string[]` (the caller's allowed action
keys), populated in `Identity.to_payload` AND the manual signup/login dict returns
(all three paths). Frontend `useAuth()` exposes `can(action)` from
`identity.permissions`; UI hides/disables affordances with tooltips. **UI gating is
convenience only** — never the security boundary.

**How to apply:** to gate a new sensitive route, add the action to
`permissions.ACTIONS` (server + client both read it), attach
`require_permission(...)` to the route, and gate the UI control with `can(...)`.
The smoke script (`scripts/smoke-api.sh`) now signs up first because the business
API is session-protected.
