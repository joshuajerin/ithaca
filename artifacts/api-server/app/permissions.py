"""Role-based permission matrix — the single source of truth for *who may do what*.

The auth foundation gives every user a role (``admin``/``trader``/``analyst``/
``read-only``); this module turns that role into concrete, enforceable
authorization. It is intentionally pure data + tiny helpers (no FastAPI, no DB),
so the same matrix can drive:

  * server-side enforcement (``main.require_permission`` raises 403 when the
    caller's role is below an action's minimum), and
  * UI gating (the current user's allowed actions are shipped in the identity
    payload so the terminal can hide/disable buttons it knows will fail).

Roles are strictly ranked. An action declares the *minimum* role that may
perform it; any role at or above that rank is allowed. To change the policy,
edit ``ACTIONS`` (or ``ROLE_RANK``) here and nowhere else.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Strict role hierarchy: a higher rank can do everything a lower rank can.
#   read-only  < analyst < trader < admin
ROLE_RANK: Dict[str, int] = {
    "read-only": 0,
    "analyst": 1,
    "trader": 2,
    "admin": 3,
}

# Fallback rank for an unknown/missing role — treated as the most restricted, so
# a malformed role can never accidentally unlock a privileged action.
_UNKNOWN_RANK = -1

# Every sensitive (mutating / privileged) action, mapped to the minimum role
# that may perform it and a human-readable label used in 403 messages and UI
# tooltips. The tiers follow the product contract:
#   * read-only — view everything, mutate nothing (appears in no action below)
#   * analyst   — build & save research artifacts (dashboards, DCF, watchlist, alerts)
#   * trader    — additionally manage strategies, paper trades & rebalances
#   * admin     — additionally change firm settings, compliance limits & the platform
ACTIONS: Dict[str, Tuple[str, str]] = {
    # --- analyst: research & personal-workspace mutations ---
    "dashboard.save": ("analyst", "save dashboards"),
    "dashboard.delete": ("analyst", "delete saved dashboards"),
    "watchlist.edit": ("analyst", "edit the watchlist"),
    "dcf.save": ("analyst", "save DCF models"),
    "alert.manage": ("analyst", "manage alert rules"),
    # --- trader: strategy lifecycle, paper trading & rebalancing ---
    "strategy.manage": ("trader", "create or manage strategies"),
    "strategy.trade": ("trader", "place paper trades or rebalance"),
    "template.use": ("trader", "clone or save strategy templates"),
    # --- admin: firm settings, compliance config & platform changes ---
    "compliance.config": ("admin", "change compliance limits or settings"),
    "feature.build": ("admin", "build or remove platform features"),
    "user.manage": ("admin", "manage team members, roles & invitations"),
    "firm.manage": ("admin", "edit firm profile & view billing"),
}


def normalize_role(role: str | None) -> str:
    return (role or "").strip().lower()


def _rank(role: str | None) -> int:
    return ROLE_RANK.get(normalize_role(role), _UNKNOWN_RANK)


def meets(role: str | None, min_role: str) -> bool:
    """True when ``role`` is at or above ``min_role`` in the hierarchy."""
    return _rank(role) >= ROLE_RANK.get(normalize_role(min_role), _UNKNOWN_RANK + 1)


def min_role_for(action: str) -> str | None:
    entry = ACTIONS.get(action)
    return entry[0] if entry else None


def label_for(action: str) -> str:
    entry = ACTIONS.get(action)
    return entry[1] if entry else action


def can(role: str | None, action: str) -> bool:
    """True when a user with ``role`` may perform ``action``.

    Unknown actions are denied by default (fail closed) so a typo in an
    ``@require_permission`` call can never silently allow everyone through.
    """
    min_role = min_role_for(action)
    if min_role is None:
        return False
    return meets(role, min_role)


def allowed_actions(role: str | None) -> List[str]:
    """Every action key a user with ``role`` is permitted to perform.

    Shipped in the identity payload so the frontend can gate UI affordances
    against the exact same matrix the server enforces."""
    return [action for action in ACTIONS if can(role, action)]


def denial_message(role: str | None, action: str) -> str:
    """A clear, human-readable reason an action was refused (used in 403s)."""
    min_role = min_role_for(action)
    label = label_for(action)
    shown_role = normalize_role(role) or "your role"
    if min_role is None:
        return f"Action '{action}' is not permitted."
    return (
        f"Your role ({shown_role}) is not permitted to {label}. "
        f"Requires {min_role} or higher."
    )
