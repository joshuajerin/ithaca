"""Provenance envelope + small shaping helpers shared across the skill catalog."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

SOURCE = "doomberg-v1-archive"
COMPUTED = "computed"

# Columns that carry a row's freshness timestamp, in priority order.
_FRESHNESS_KEYS = ("updated_at", "fetched_at", "filing_date", "as_of", "report_date")

# Warning emitted when the production toolset has no archive wired yet (Stream 1 not synced).
ARCHIVE_UNAVAILABLE = {
    "code": "ARCHIVE_UNAVAILABLE",
    "scope": None,
    "detail": "the v1 archive gateway is not configured on this server",
}


def freshness_of(rows: Iterable[dict] | None) -> str | None:
    """Max freshness timestamp across ``rows`` (None when empty / no timestamps present)."""
    stamps: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in _FRESHNESS_KEYS:
            val = row.get(key)
            if val:
                stamps.append(str(val))
                break
    return max(stamps) if stamps else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_of(ts: str | None) -> str:
    """Return a contract-valid data timestamp.

    Archive rows usually carry `updated_at`/`fetched_at`; when a skill has no resolved rows
    we still need a valid timestamp for the envelope and mark the result partial/stale.
    """
    return str(ts) if ts else _now_iso()


def _pit(pit: bool | str) -> str:
    if isinstance(pit, str):
        return pit
    return "true" if pit else "false"


def _coverage(data: Any) -> dict[str, Any]:
    if data is None:
        return {"requested": 1, "resolved": 0, "missing": []}
    if isinstance(data, list):
        return {"requested": len(data), "resolved": len(data), "missing": []}
    return {"requested": 1, "resolved": 1, "missing": []}


def _cost(source: str) -> dict[str, Any]:
    return {"class": "cheap" if source == COMPUTED else "network", "credits": 0}


def envelope(
    data: Any,
    *,
    freshness: str | None = None,
    pit: bool = False,
    warnings: list[dict] | None = None,
    partial: bool | None = None,
) -> dict:
    """Wrap a skill payload in the canonical archive provenance envelope."""
    resolved_partial = data is None or bool(warnings) if partial is None else bool(partial)
    return {
        "data": data,
        "provenance": {
            "source": SOURCE,
            "as_of": _as_of(freshness),
            "freshness": "stale",
            "stale_age_sec": None,
            "pit": _pit(pit),
            "coverage": _coverage(data),
            "cost": _cost(SOURCE),
            "cache_hit": False,
        },
        "partial": resolved_partial,
        "warnings": warnings or [],
    }


def computed_envelope(
    data: Any,
    *,
    freshness: str | None = None,
    inputs: str | None = None,
    warnings: list[dict] | None = None,
    partial: bool | None = None,
) -> dict:
    """Wrap a pure-math (COMPUTED) skill payload.

    ``source`` is ``"computed"`` — the math is real but no archive row is being
    presented as live market data. ``pit`` is always False. ``inputs`` documents where
    the numbers came from (``"agent"`` for agent-supplied S/K/sigma/etc., or
    ``"doomberg-v1-archive"`` when the computation ran on real archive series). When a
    computation reads archive series, pass that table's ``freshness`` through so the
    provenance still carries the data's age.
    """
    prov = {
        "source": COMPUTED,
        "as_of": _as_of(freshness),
        "freshness": "live" if freshness is None else "stale",
        "stale_age_sec": None,
        "pit": "false",
        "coverage": _coverage(data),
        "cost": _cost(COMPUTED),
        "cache_hit": False,
    }
    if inputs:
        prov["inputs"] = inputs
    resolved_partial = data is None or bool(warnings) if partial is None else bool(partial)
    return {"data": data, "provenance": prov, "partial": resolved_partial,
            "warnings": warnings or []}


def warn(code: str, *, scope: str | None = None, detail: str | None = None) -> dict:
    return {"code": code, "scope": scope, "detail": detail}


# ----------------------------- formatting helpers (ported from v1) -----------------------------
def fmt_usd(n: float | None) -> str:
    if n is None:
        return "—"
    a = abs(n)
    if a >= 1_000_000_000_000:
        return f"${n / 1_000_000_000_000:.2f}T"
    if a >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    if a >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    return f"${n:,.0f}"


_CONSENSUS_LABELS = {
    "strong_buy": "Strong Buy", "buy": "Buy", "moderate_buy": "Moderate Buy",
    "outperform": "Outperform", "overweight": "Overweight", "hold": "Hold",
    "neutral": "Hold", "moderate_sell": "Moderate Sell", "underperform": "Underperform",
    "underweight": "Underweight", "sell": "Sell", "strong_sell": "Strong Sell",
}


def consensus_label(key: str | None, mean: float | None) -> str | None:
    """Human consensus label from a recommendationKey or the 1–5 mean (Yahoo scale)."""
    if key:
        lab = _CONSENSUS_LABELS.get(str(key).strip().lower())
        if lab:
            return lab
    if mean is None:
        return None
    if mean <= 1.5:
        return "Strong Buy"
    if mean <= 2.5:
        return "Buy"
    if mean <= 3.5:
        return "Hold"
    if mean <= 4.5:
        return "Sell"
    return "Strong Sell"


__all__ = [
    "SOURCE", "COMPUTED", "ARCHIVE_UNAVAILABLE", "freshness_of", "envelope",
    "computed_envelope", "warn", "fmt_usd", "consensus_label",
]
