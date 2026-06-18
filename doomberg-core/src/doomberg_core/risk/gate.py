"""The runtime risk gate — the money-path boundary, not a lint.

v1's optimizer could return a book at ~311% gross while reporting ``optimal`` because the
final projection re-asserted net + box but NOT the gross (L1) constraint. Here the
gross-L1 re-check runs on EVERY emitted weight row, after per-name clamping, and refuses
to emit a breaching book. ``attest`` is the read; ``project_feasible`` is the enforcement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["RiskLimits", "Attestation", "attest", "project_feasible"]

_TOL = 1e-9


@dataclass(frozen=True)
class RiskLimits:
    max_gross: float
    max_net: float
    max_name_pct: float

    @classmethod
    def from_spec(cls, risk: dict) -> "RiskLimits":
        return cls(
            max_gross=float(risk["max_gross"]),
            max_net=float(risk["max_net"]),
            max_name_pct=float(risk["max_name_pct"]),
        )


@dataclass
class Attestation:
    ok: bool
    gross: float
    net: float
    max_name: float
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "gross": round(self.gross, 6),
            "net": round(self.net, 6),
            "maxName": round(self.max_name, 6),
            "violations": list(self.violations),
        }


def attest(weights: np.ndarray, limits: RiskLimits) -> Attestation:
    """Read-only check of a single weight row against the hard limits."""
    w = np.asarray(weights, dtype=float)
    gross = float(np.sum(np.abs(w)))
    net = float(np.sum(w))
    max_name = float(np.max(np.abs(w))) if w.size else 0.0
    violations: list[str] = []
    if gross > limits.max_gross + _TOL:
        violations.append(f"gross {gross:.4f} > max_gross {limits.max_gross:.4f}")
    if abs(net) > limits.max_net + _TOL:
        violations.append(f"net {net:.4f} > max_net {limits.max_net:.4f}")
    if max_name > limits.max_name_pct + _TOL:
        violations.append(f"max_name {max_name:.4f} > max_name_pct {limits.max_name_pct:.4f}")
    return Attestation(ok=not violations, gross=gross, net=net, max_name=max_name, violations=violations)


def project_feasible(weights: np.ndarray, limits: RiskLimits) -> tuple[np.ndarray, Attestation]:
    """Project a weight row onto the feasible set, then RE-ATTEST.

    Order: clamp each |w_i| to max_name_pct (sign preserved) -> scale to satisfy gross (L1)
    -> scale to satisfy net. The final attest is on the projected book, so a breach can
    never be reported as feasible (the v1 bug). Returns the (possibly relaxed) book plus
    its attestation; callers must check ``att.ok`` before trusting it.
    """
    w = np.asarray(weights, dtype=float).copy()

    # 1) per-name box
    cap = limits.max_name_pct
    np.clip(w, -cap, cap, out=w)

    # 2) gross (L1) ball — THE re-check v1 omitted
    gross = float(np.sum(np.abs(w)))
    if gross > limits.max_gross + _TOL and gross > 0:
        w *= limits.max_gross / gross

    # 3) net — only meaningful for long/short; scaling the whole vector preserves the
    # gross feasibility achieved above (|net| <= gross, so a net-driven down-scale keeps gross ok).
    net = float(np.sum(w))
    if abs(net) > limits.max_net + _TOL and abs(net) > 0:
        w *= limits.max_net / abs(net)

    return w, attest(w, limits)
