"""ithaca-control-plane — specs, run state machine, compliance gate.

The SINGLE writer of the money path. A thin FastAPI app over ``ithaca_platform`` (the
system-of-record) and ``ithaca_core`` (spec validation + the gross-L1 risk gate). Every
write passes ``tenant_id`` first; no agent/LLM code is executed; audited failures emit a
``denial``/``error`` trace before returning an HTTP error.
"""
from __future__ import annotations

from .app import app, create_app
from .deps import (
    HUMAN_ACTOR_KINDS,
    Ctx,
    Platform,
    get_ctx,
    get_platform,
    require_scope,
    resolve_ctx,
)
from .gate import DEFAULT_RESTRICTED, GateDecision, evaluate_spec_gate

__all__ = [
    "app",
    "create_app",
    "Ctx",
    "Platform",
    "HUMAN_ACTOR_KINDS",
    "get_ctx",
    "get_platform",
    "require_scope",
    "resolve_ctx",
    "GateDecision",
    "evaluate_spec_gate",
    "DEFAULT_RESTRICTED",
]
