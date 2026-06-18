"""The paper money path: apply a proposed book delta — the control plane's SINGLE writer.

The runtime's ``run_paper_tick`` is stateless and only *proposes* a target book. This is the
one place the book is actually written, and it re-runs the hard gate on the proposed target
BEFORE writing (defense in depth — never trust a proposal blindly):

1. The run must be a ``live`` paper deployment for the tenant.
2. Restricted-name check on the target book (hard block).
3. Gross-L1 risk re-attestation via ``doomberg_core.risk`` (the same kernel the gate and the
   backtest use — no duplicated math; the v1 311%-gross bug cannot recur).
4. Only on pass: ``BookStore.apply`` under the optimistic version guard, then emit a ``fill``
   (``applied=true``). On a block we emit a ``denial`` and write nothing.

``make_applier(platform)`` returns a ``(tenant_id, run_id, proposal) -> result`` callable that
the runtime ``PaperScheduler`` injects — keeping the runtime decoupled from the control plane
while this code stays the authoritative writer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import numpy as np

from doomberg_core.risk import RiskLimits, attest

from .gate import DEFAULT_RESTRICTED

__all__ = ["apply_paper_delta", "make_applier"]

_SYSTEM_ACTOR = {"kind": "system", "id": "doomberg_control"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(platform: Any, *, tenant_id: str, run_id: str, type: str, data: dict[str, Any]) -> int:
    event = {
        "run_id": str(run_id),
        "seq": 0,  # store-assigned
        "ts": _now_iso(),
        "type": type,
        "tenant_id": str(tenant_id),
        "actor": dict(_SYSTEM_ACTOR),
        "data": data,
    }
    return platform.trace.append(event)


def apply_paper_delta(
    platform: Any,
    tenant_id: str,
    run_id: str,
    proposal: dict[str, Any],
    *,
    capital: float = 100_000.0,
    restricted: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Apply a paper-tick ``proposal`` to the book under the gate. Returns a result dict."""
    tenant_id, run_id = str(tenant_id), str(run_id)
    run = platform.runs.get(tenant_id, run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id}")
    if run.get("kind") != "paper" or run.get("state") != "live":
        # Not an applicable deployment; audit and refuse to touch the money path.
        _emit(platform, tenant_id=tenant_id, run_id=run_id, type="denial",
              data={"action": "apply_delta", "reason": "run is not a live paper deployment",
                    "kind": run.get("kind"), "state": run.get("state")})
        return {"applied": False, "reason": "not_live_paper"}

    spec = run.get("spec") or {}
    target = {str(s).upper(): float(w) for s, w in (proposal.get("targetWeights") or {}).items()}
    marks = {str(s).upper(): float(m) for s, m in (proposal.get("marks") or {}).items()}

    # (2) restricted names in the target book -> hard block.
    rset = {s.strip().upper() for s in (restricted if restricted is not None else DEFAULT_RESTRICTED)}
    hits = sorted(s for s in target if s in rset)
    if hits:
        _emit(platform, tenant_id=tenant_id, run_id=run_id, type="denial",
              data={"action": "apply_delta", "reason": "restricted name(s) in target book",
                    "restricted": hits})
        return {"applied": False, "reason": "restricted", "restricted": hits}

    # (3) gross-L1 re-attestation on the proposed target (the realized book that would trade).
    syms = sorted(target)
    weights = np.array([target[s] for s in syms], dtype=float)
    limits = RiskLimits.from_spec(spec.get("risk") or {})
    att = attest(weights, limits)
    if not att.ok:
        _emit(platform, tenant_id=tenant_id, run_id=run_id, type="denial",
              data={"action": "apply_delta", "reason": "risk attestation failed",
                    "attestation": att.to_dict()})
        return {"applied": False, "reason": "risk", "attestation": att.to_dict()}

    # (4) write the book under the optimistic guard, then audit the applied fill.
    book = platform.books.ensure(tenant_id, run_id, capital=capital)
    deltas = {
        s: round(target.get(s, 0.0) - float(book["weights"].get(s, 0.0)), 6)
        for s in sorted(set(target) | set(book["weights"]))
    }
    deltas = {s: d for s, d in deltas.items() if abs(d) > 1e-9}
    updated = platform.books.apply(
        tenant_id, run_id, target_weights=target, marks=marks, expect=book["version"],
    )
    _emit(platform, tenant_id=tenant_id, run_id=run_id, type="fill",
          data={"applied": True, "deltas": deltas, "targetWeights": target,
                "previousWeights": book["weights"], "marks": marks,
                "attestation": att.to_dict(), "bookVersion": updated["version"]})
    return {"applied": True, "deltas": deltas, "book": updated, "attestation": att.to_dict()}


def make_applier(
    platform: Any, *, capital: float = 100_000.0, restricted: Iterable[str] | None = None
) -> Callable[[str, str, dict[str, Any]], dict[str, Any]]:
    """Return the ``(tenant_id, run_id, proposal) -> result`` applier for the scheduler."""
    def _apply(tenant_id: str, run_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        return apply_paper_delta(platform, tenant_id, run_id, proposal,
                                 capital=capital, restricted=restricted)
    return _apply
