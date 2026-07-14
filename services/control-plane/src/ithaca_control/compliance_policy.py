"""Tenant compliance configuration shared by REST, promotion, paper, and execution gates."""

from __future__ import annotations

import math
import os
import re
from typing import Any, Iterable

from ithaca_core.engine.compliance import DEFAULT_LIMITS

from .gate import DEFAULT_RESTRICTED

LIMIT_BOUNDS: dict[str, tuple[float, float]] = {
    "maxPositionPct": (0.01, 100.0),
    "maxNetPct": (0.01, 1_000.0),
    "maxLeverage": (0.01, 10.0),
    "maxConcentrationPct": (0.01, 100.0),
}
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")


def normalize_symbol(value: str) -> str:
    symbol = str(value).strip().upper()
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("symbol must be 1-15 uppercase letters, digits, dots, or hyphens")
    return symbol


def normalize_symbols(values: Iterable[str], *, limit: int = 500) -> list[str]:
    normalized: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol not in normalized:
            normalized.append(symbol)
        if len(normalized) > limit:
            raise ValueError(f"symbol list cannot exceed {limit} names")
    return sorted(normalized)


def normalize_limits(values: dict[str, Any]) -> dict[str, float]:
    unknown = sorted(set(values) - set(LIMIT_BOUNDS))
    if unknown:
        raise ValueError("unknown compliance limit(s): " + ", ".join(unknown))
    if set(values) != set(LIMIT_BOUNDS):
        missing = sorted(set(LIMIT_BOUNDS) - set(values))
        raise ValueError("missing compliance limit(s): " + ", ".join(missing))
    normalized: dict[str, float] = {}
    for key, (minimum, maximum) in LIMIT_BOUNDS.items():
        try:
            value = float(values[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric") from exc
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}")
        normalized[key] = value
    return normalized


def effective_compliance_policy(platform: Any, tenant_id: str) -> dict[str, Any]:
    store = getattr(platform, "compliance_policies", None)
    row = store.get(str(tenant_id)) if store is not None else None
    if row is None:
        return {
            "limits": dict(DEFAULT_LIMITS),
            "restricted": list(DEFAULT_RESTRICTED),
            "watch": [],
            "configured": False,
            "limits_enforced": False,
            "version": 0,
            "updated_at": None,
            "updated_by": None,
            "available": store is not None,
        }
    return {
        "limits": normalize_limits(row["limits"]),
        "restricted": normalize_symbols(row["restricted"]),
        "watch": normalize_symbols(row["watch"]),
        "configured": True,
        "limits_enforced": bool(row["limits_enforced"]),
        "version": int(row["version"]),
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
        "available": True,
    }


def effective_execution_control(platform: Any, tenant_id: str) -> dict[str, Any]:
    if os.environ.get("ITHACA_EXECUTION_KILL_SWITCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "enabled": True,
            "source": "environment",
            "reason": "ITHACA_EXECUTION_KILL_SWITCH is active",
        }
    controls = getattr(platform, "execution_controls", None)
    if controls is None:
        return {
            "enabled": True,
            "source": "missing_control_store",
            "reason": "execution control store is unavailable",
        }
    return controls.get_effective(str(tenant_id))
