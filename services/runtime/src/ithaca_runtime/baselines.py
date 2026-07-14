"""Trigger baseline resolution for percent-move policies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

__all__ = ["BaselineResolver"]


def _parse_time(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        n = float(value)
        if n > 10_000_000_000:
            n = n / 1000.0
        return datetime.fromtimestamp(n, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return default


def _first_number(container: Any, names: tuple[str, ...]) -> float | None:
    if not isinstance(container, dict):
        return None
    for name in names:
        value = container.get(name)
        if value is None:
            continue
        try:
            out = float(value)
        except (TypeError, ValueError):
            continue
        if out == out and out > 0:
            return out
    return None


def _dig_quote(quote: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for container in (
        quote,
        quote.get("raw"),
        (quote.get("raw") or {}).get("data") if isinstance(quote.get("raw"), dict) else None,
        (quote.get("raw") or {}).get("quote") if isinstance(quote.get("raw"), dict) else None,
        ((quote.get("raw") or {}).get("data") or {}).get("quote")
        if isinstance((quote.get("raw") or {}).get("data"), dict)
        else None,
    ):
        value = _first_number(container, names)
        if value is not None:
            return value
    return None


class BaselineResolver:
    """Resolve the reference price for a trigger condition.

    Provider-supplied baselines are preferred for ``previous_close`` and ``session_open``.
    Snapshot baselines are durable and captured on first evaluation, which makes a trigger
    stable across worker restarts without running agent code.
    """

    def __init__(self, platform: Any) -> None:
        self.platform = platform

    def resolve(
        self,
        *,
        tenant_id: str,
        trigger_id: str,
        policy: dict[str, Any],
        quote: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        baseline = (policy.get("when") or {}).get("baseline")
        if not baseline:
            return None
        if not isinstance(baseline, dict):
            raise ValueError("when.baseline must be an object")
        kind = str(baseline.get("type") or "").strip().lower()
        if not kind:
            return None
        symbol = str(quote.get("symbol") or baseline.get("symbol") or "").upper()
        event_time = _parse_time(quote.get("event_time"), default=now)
        trading_day = str(baseline.get("trading_day") or event_time.date().isoformat())

        if kind == "previous_close":
            price = _dig_quote(
                quote,
                (
                    "previous_close",
                    "previousClose",
                    "prev_close",
                    "prevClose",
                    "regularMarketPreviousClose",
                ),
            )
            if price is None:
                raise ValueError("previous_close baseline requires provider quote previous_close")
            return {
                "type": kind,
                "price": price,
                "time": str(baseline.get("time") or event_time.isoformat()),
                "trading_day": trading_day,
            }

        if kind == "session_open":
            price = _dig_quote(quote, ("session_open", "sessionOpen", "open", "regularMarketOpen"))
            if price is None:
                raise ValueError("session_open baseline requires provider quote open")
            return {
                "type": kind,
                "price": price,
                "time": str(baseline.get("time") or event_time.isoformat()),
                "trading_day": trading_day,
            }

        if kind == "fixed_price":
            price = baseline.get("price")
            if price is None:
                raise ValueError("fixed_price baseline requires baseline.price")
            return {
                "type": kind,
                "price": float(price),
                "time": str(baseline.get("time") or event_time.isoformat()),
                "trading_day": trading_day,
            }

        if kind == "last_firing":
            latest = self.platform.triggers.latest_firing(tenant_id, trigger_id)
            if latest is None:
                fallback = baseline.get("fallback_price") or baseline.get("price")
                if fallback is None:
                    raise ValueError("last_firing baseline requires a previous firing or fallback_price")
                return {
                    "type": kind,
                    "price": float(fallback),
                    "time": str(baseline.get("time") or event_time.isoformat()),
                    "trading_day": trading_day,
                }
            ctx = (latest.get("payload") or {}).get("context") or {}
            price = ctx.get("price")
            if price is None:
                raise ValueError("last_firing baseline could not read prior firing price")
            return {
                "type": kind,
                "price": float(price),
                "time": str(latest.get("event_time") or event_time.isoformat()),
                "trading_day": trading_day,
            }

        if kind in {"snapshot", "snapshot_on_activation"}:
            baseline_key = f"{kind}:{symbol}"
            existing = getattr(self.platform, "baselines", None)
            if existing is None:
                raise ValueError("snapshot baseline requires platform.baselines")
            row = self.platform.baselines.get(tenant_id, trigger_id, baseline_key)
            if row is None:
                row = self.platform.baselines.upsert(
                    tenant_id,
                    trigger_id,
                    baseline_key=baseline_key,
                    baseline_type=kind,
                    symbol=symbol,
                    price=float(quote["price"]),
                    baseline_time=event_time.isoformat(),
                    trading_day=trading_day,
                    payload={"source": "first_evaluation"},
                )
            return {
                "type": row["type"],
                "price": float(row["price"]),
                "time": row["time"],
                "trading_day": row["trading_day"],
            }

        if kind == "rolling_window":
            raise ValueError("rolling_window baseline is not implemented in v1")
        raise ValueError(f"unsupported baseline type: {kind}")
