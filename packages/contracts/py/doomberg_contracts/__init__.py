"""Doomberg v2 shared contracts.

The JSON-Schema files in ``packages/contracts/schema`` are the single source of truth.
The pydantic models under ``doomberg_contracts.generated`` are GENERATED from them by
``scripts/codegen.sh`` and verified in CI by ``scripts/check_drift.sh``. Do not hand-edit
generated code.
"""

from .generated import (
    AuthPrincipal,
    ProvenanceEnvelope,
    StrategySpec,
    TenantContext,
    TraceEvent,
)

__all__ = [
    "AuthPrincipal",
    "ProvenanceEnvelope",
    "StrategySpec",
    "TenantContext",
    "TraceEvent",
]
