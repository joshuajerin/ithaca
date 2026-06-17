"""Provenance envelope + small shaping helpers shared across the skill catalog.

The envelope here is the lightweight skill-result shape mandated by the data-layer contract:

    {"data": ..., "provenance": {"source": "doomberg-v1-archive", "freshness": <ts|None>,
     "pit": <bool>}, "warnings": [...]}

``source`` is always ``doomberg-v1-archive`` (the imported v1 reference data). ``freshness`` is the
max ``updated_at`` / ``fetched_at`` of the rows actually used (None when nothing resolved). ``pit``
is True only for the point-in-time fundamentals skill.
"""
from __future__ import annotations

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


def envelope(
    data: Any,
    *,
    freshness: str | None = None,
    pit: bool = False,
    warnings: list[dict] | None = None,
) -> dict:
    """Wrap a skill payload in the canonical archive provenance envelope."""
    return {
        "data": data,
        "provenance": {"source": SOURCE, "freshness": freshness, "pit": pit},
        "warnings": warnings or [],
    }


def computed_envelope(
    data: Any,
    *,
    freshness: str | None = None,
    inputs: str | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    """Wrap a pure-math (COMPUTED) skill payload.

    ``source`` is ``"computed"`` — the math is real but no archive row is being
    presented as live market data. ``pit`` is always False. ``inputs`` documents where
    the numbers came from (``"agent"`` for agent-supplied S/K/sigma/etc., or
    ``"doomberg-v1-archive"`` when the computation ran on real archive series). When a
    computation reads archive series, pass that table's ``freshness`` through so the
    provenance still carries the data's age.
    """
    prov = {"source": COMPUTED, "freshness": freshness, "pit": False}
    if inputs:
        prov["inputs"] = inputs
    return {"data": data, "provenance": prov, "warnings": warnings or []}


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
