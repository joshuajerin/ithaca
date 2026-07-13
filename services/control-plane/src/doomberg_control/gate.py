"""Pre-trade compliance + risk gate — the money-path boundary, not a lint.

Two layers, both HARD blocks on failure:

1. **Compliance** (adapted from v1 ``engine/compliance.py`` — the desk-language restricted
   list / gross cap idea, re-expressed here against the v2 closed ``StrategySpec``). A
   restricted name anywhere in the resulting book is a hard block; watch-list names are a
   soft warning. We do NOT re-import v1.

2. **Risk** — the runtime gross-L1 attestation. This is ``doomberg_core.risk`` (already
   built and tested); we REUSE it and never duplicate the gross/net/per-name math. The
   target book is projected onto the feasible set and RE-ATTESTED, so a breaching book can
   never be reported as feasible (the v1 311%-gross optimizer bug).

The gate is pure and deterministic: given a validated spec it derives a deterministic
design-time target book (the construction the strategy would hold at full gross), then runs
both layers. No IO, no agent code. The caller owns the audit write (a ``denial`` trace event
on block).
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from doomberg_core.risk import RiskLimits, attest, project_feasible
from doomberg_core.engine.compliance import book_metrics, evaluate_limits

__all__ = ["GateDecision", "evaluate_spec_gate", "DEFAULT_RESTRICTED"]

# Firm-level restricted symbols. In production this is tenant/firm config; for local dev a
# small built-in deny list demonstrates the hard block (e.g. sanctioned / non-tradable).
DEFAULT_RESTRICTED: tuple[str, ...] = ("GME", "AMC", "SDNY")


class GateDecision:
    """Structured pass/fail decision over a proposed paper deployment.

    ``ok`` is True only when there are NO hard violations (restricted name, or a post-
    projection risk attestation that still breaches). Warnings (watch-list, relaxed book)
    are reported but do not block.
    """

    def __init__(
        self,
        *,
        ok: bool,
        attestation: dict[str, Any],
        relaxed: bool,
        target_weights: dict[str, float],
        violations: list[str],
        warnings: list[str],
        restricted_hits: list[str],
        watch_hits: list[str] | None = None,
        checks: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
        kill_switch: bool = False,
        kill_reason: str | None = None,
    ) -> None:
        self.ok = ok
        self.attestation = attestation
        self.relaxed = relaxed
        self.target_weights = target_weights
        self.violations = violations
        self.warnings = warnings
        self.restricted_hits = restricted_hits
        self.watch_hits = watch_hits or []
        self.checks = checks or []
        self.metrics = metrics or book_metrics(target_weights)
        self.kill_switch = bool(kill_switch)
        self.kill_reason = kill_reason if kill_switch else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocked": not self.ok,
            "attestation": self.attestation,
            "relaxed": self.relaxed,
            "targetWeights": self.target_weights,
            "violations": self.violations,
            "warnings": self.warnings,
            "restricted": self.restricted_hits,
            "watch": self.watch_hits,
            "checks": self.checks,
            "metrics": self.metrics,
            "killSwitch": self.kill_switch,
            "killReason": self.kill_reason,
            "reason": None if self.ok else "; ".join(self.violations),
        }


def _norm(items: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for it in items or []:
        s = (it or "").strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def _design_time_book(spec: dict[str, Any]) -> tuple[list[str], np.ndarray]:
    """Derive the deterministic design-time target book the strategy would hold.

    v2.0 ships parameterized primitives with cross-sectional weighting. Without running the
    backtest, the gate evaluates the *worst-case admissible* book the construction allows:
    full target gross spread equal-weight across the declared universe. For ``long_only`` the
    weights are positive; otherwise a symmetric long/short split is used. This is a
    pre-attestation — the runtime gate re-checks the realized book per tick.
    """
    symbols = [str(s) for s in spec["universe"]["symbols"]]
    n = len(symbols)
    construction = spec["construction"]
    gross = float(construction["gross"])
    long_only = construction.get("long_only", True)
    if n == 0:
        return symbols, np.zeros(0, dtype=float)
    per = gross / n
    if long_only is False:
        # Alternate signs so |net| < gross while sum|w| == gross (a long/short book).
        signs = np.array([1.0 if i % 2 == 0 else -1.0 for i in range(n)])
        w = signs * per
    else:
        w = np.full(n, per, dtype=float)
    return symbols, w


def evaluate_spec_gate(
    spec: dict[str, Any],
    *,
    restricted: Iterable[str] | None = None,
    watch: Iterable[str] | None = None,
    firm_limits: dict[str, float] | None = None,
    kill_switch: bool = False,
    kill_reason: str | None = None,
) -> GateDecision:
    """Run the full pre-trade gate over a validated StrategySpec.

    Restricted-name hits are a hard block. The risk limits come from the spec's own ``risk``
    block; the target book is projected + re-attested via ``doomberg_core.risk`` (no
    duplicated gross-L1 math). If the projection had to relax the book to stay feasible we
    flag ``relaxed`` (a warning, not a block — the projected book is feasible by construction,
    but the strategy as authored over-reached).
    """
    symbols, weights = _design_time_book(spec)
    sym_upper = [s.upper() for s in symbols]

    restricted_list = _norm(restricted) if restricted is not None else list(DEFAULT_RESTRICTED)
    watch_list = _norm(watch)
    rset = set(restricted_list)
    wset = set(watch_list)
    restricted_hits = [s for s in sym_upper if s in rset]
    watch_hits = [s for s in sym_upper if s in wset]

    limits = RiskLimits.from_spec(spec["risk"])

    # Read the book AS AUTHORED first (did the construction over-reach?), then project.
    as_authored = attest(weights, limits)
    projected_w, projected_att = project_feasible(weights, limits)
    projected_weights = {s: round(float(w), 6) for s, w in zip(symbols, projected_w)}
    relaxed = not as_authored.ok and projected_att.ok

    violations: list[str] = []
    warnings: list[str] = []

    if restricted_hits:
        violations.append("Restricted name(s) in the book: " + ", ".join(restricted_hits))

    # The projected book is the one that would actually trade. If even after projection it
    # breaches (should not happen for a well-formed limit set, but the re-attest is the hard
    # boundary), block.
    if not projected_att.ok:
        violations.extend(projected_att.violations)

    if relaxed:
        warnings.append(
            "Book as authored breaches risk limits and was relaxed to stay feasible: "
            + "; ".join(as_authored.violations)
        )
    if watch_hits:
        warnings.append("Watch-list name(s): " + ", ".join(watch_hits))

    checks = evaluate_limits(projected_weights, firm_limits)
    if firm_limits is not None:
        for check in checks:
            if check["status"] == "breach":
                violations.append(
                    f"Firm {check['label'].lower()} {check['value']:.1f}{check['unit']} "
                    f"exceeds {check['limit']:.1f}{check['unit']}"
                )
            elif check["status"] == "warn":
                warnings.append(
                    f"Firm {check['label'].lower()} at "
                    f"{check['utilization'] * 100:.0f}% of its limit"
                )
    if kill_switch:
        violations.append(
            "Kill switch is engaged" + (f": {kill_reason}" if kill_reason else "")
        )

    ok = not violations
    return GateDecision(
        ok=ok,
        attestation=projected_att.to_dict(),
        relaxed=relaxed,
        target_weights=projected_weights,
        violations=violations,
        warnings=warnings,
        restricted_hits=restricted_hits,
        watch_hits=watch_hits,
        checks=checks,
        metrics=book_metrics(projected_weights),
        kill_switch=kill_switch,
        kill_reason=kill_reason,
    )
