"""The Data Gateway facade — the ONE entry to market data for both the agent and worker paths.

Wraps the ported ``sources/`` adapters and stamps the mandatory provenance envelope on every
result. The only difference between the agent path and the worker path is the ``as_of``
truncation parameter (point-in-time): the worker passes ``as_of = bar_i``, the agent passes
``as_of = now``. Point-in-time is a per-source CAPABILITY (the ``pit`` flag) — the gateway
cannot manufacture it. Free Yahoo data is ``pit='false'`` (restated, survivorship-biased), so
backtests built on it are honestly labeled and scoped to price/technical strategies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

import numpy as np

from ..sources import prices as _prices

__all__ = ["DataGateway", "PricePanel"]

_SOURCE = "yahoo-chart"
_PIT = "false"  # Yahoo is restated + survivorship-biased; not point-in-time. Honest by default.


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(data, *, source, as_of, coverage, cost_class, credits, freshness="live",
              partial=False, warnings=None, cache_hit=False) -> dict:
    """Build a ProvenanceEnvelope dict. Shape matches packages/contracts provenance schema."""
    return {
        "data": data,
        "provenance": {
            "source": source,
            "as_of": as_of or _now_iso(),
            "freshness": freshness,
            "stale_age_sec": 0,
            "pit": _PIT,
            "coverage": coverage,
            "cost": {"class": cost_class, "credits": credits},
            "cache_hit": bool(cache_hit),
        },
        "partial": partial,
        "warnings": warnings or [],
    }


def _date_key(point: dict) -> str | None:
    raw = point.get("d") or point.get("t") or point.get("date")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return value[:10]


def _num(value, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if isfinite(out) else default


def _clean_ohlcv(points: list[dict], *, as_of: str | None = None) -> tuple[list[dict], dict]:
    """Normalize, validate, de-duplicate, and sort OHLCV bars.

    The cache stores this cleaned shape only. We keep the operation deterministic:
    duplicate dates resolve to the last valid raw bar in provider order, and the
    final list is strictly ascending by date.
    """
    latest = (as_of or "")[:10] if as_of else None
    raw_count = len(points or [])
    by_date: dict[str, dict] = {}
    raw_dates: list[str] = []
    dropped = 0
    duplicate_writes = 0

    for point in points or []:
        date = _date_key(point)
        if date is None:
            dropped += 1
            continue
        raw_dates.append(date)
        if latest and date > latest:
            dropped += 1
            continue
        close = _num(point.get("c") if "c" in point else point.get("close"))
        if close is None or close <= 0:
            dropped += 1
            continue
        if date in by_date:
            duplicate_writes += 1
        open_ = _num(point.get("o") if "o" in point else point.get("open"), close) or close
        high = _num(point.get("h") if "h" in point else point.get("high"), close) or close
        low = _num(point.get("l") if "l" in point else point.get("low"), close) or close
        volume = _num(point.get("v") if "v" in point else point.get("volume"), 0.0) or 0.0
        by_date[date] = {
            "d": date,
            "o": float(open_ if open_ > 0 else close),
            "h": float(high if high > 0 else close),
            "l": float(low if low > 0 else close),
            "c": float(close),
            "v": float(max(0.0, volume)),
        }

    dates = sorted(by_date)
    clean = [by_date[d] for d in dates]
    sorted_input = raw_dates == sorted(raw_dates)
    quality = {
        "raw": raw_count,
        "clean": len(clean),
        "dropped": dropped,
        "deduped": duplicate_writes,
        "sorted": True,
        "input_sorted": sorted_input,
    }
    return clean, quality


class PricePanel:
    """An aligned close-price matrix for a universe: dates (T) x symbols (N)."""

    __slots__ = ("dates", "closes", "symbols", "missing", "quality")

    def __init__(
        self,
        dates: list[str],
        closes: np.ndarray,
        symbols: list[str],
        missing: list[str],
        quality: dict[str, dict] | None = None,
    ):
        self.dates = dates
        self.closes = closes
        self.symbols = symbols
        self.missing = missing
        self.quality = quality or {}


class DataGateway:
    """Stateless facade. ``fetch`` is injectable so tests run without network."""

    def __init__(self, fetch_history=_prices.fetch_price_history):
        self._fetch = fetch_history
        self._ohlcv_cache: dict[tuple[str, str, str, str], dict] = {}

    def _history(self, symbol: str, range_: str, interval: str, as_of: str | None = None) -> tuple[list[dict], dict, bool, dict]:
        su = symbol.upper()
        cache_key = (su, range_, interval, as_of or "")
        cached = self._ohlcv_cache.get(cache_key)
        if cached is not None:
            return list(cached["points"]), dict(cached["quality"]), True, dict(cached.get("quote") or {})

        raw = self._fetch(symbol, range_, interval)
        points, quality = _clean_ohlcv(raw.get("points") or [], as_of=as_of)
        quote = raw.get("quote") or {}
        self._ohlcv_cache[cache_key] = {"points": points, "quality": quality, "quote": quote}
        return list(points), dict(quality), False, dict(quote)

    # ---- agent-facing tool ------------------------------------------------------------
    def get_ohlcv(self, symbol: str, range_: str = "6mo", interval: str = "1d",
                  as_of: str | None = None) -> dict:
        """Single-symbol OHLCV, wrapped in a provenance envelope (the market.get_ohlcv tool)."""
        try:
            points, quality, cache_hit, quote = self._history(symbol, range_, interval, as_of)
        except Exception as exc:  # honest failure, not silent mock
            return _envelope(
                None, source=_SOURCE, as_of=_now_iso(),
                coverage={"requested": 1, "resolved": 0, "missing": [symbol.upper()]},
                cost_class="network", credits=1, freshness="mock", partial=True,
                warnings=[{"code": "UPSTREAM_ERROR", "scope": symbol.upper(), "detail": str(exc)[:200]}],
            )
        data = {"symbol": symbol.upper(), "points": points, "quote": quote, "quality": quality}
        warnings = []
        if quality["dropped"] or quality["deduped"] or not quality["input_sorted"]:
            warnings.append({
                "code": "OHLCV_CLEANED",
                "scope": symbol.upper(),
                "detail": (
                    f"cleaned {quality['raw']} raw bars to {quality['clean']} bars "
                    f"(dropped {quality['dropped']}, deduped {quality['deduped']})"
                ),
            })
        return _envelope(
            data, source=_SOURCE, as_of=quote.get("asOf") or _now_iso(),
            coverage={"requested": 1, "resolved": 1 if points else 0,
                      "missing": [] if points else [symbol.upper()]},
            cost_class="network", credits=1, partial=not points, warnings=warnings,
            cache_hit=cache_hit,
        )

    # ---- worker/backtest-facing -------------------------------------------------------
    def price_panel(self, symbols: list[str], range_: str = "1y", interval: str = "1d",
                    as_of: str | None = None) -> tuple[PricePanel, dict]:
        """Aligned close matrix over the common trading days of ``symbols``.

        Missing symbols are REPORTED in coverage, never imputed. Returns (PricePanel, provenance).
        """
        per_symbol: dict[str, dict[str, float]] = {}
        quality_by_symbol: dict[str, dict] = {}
        cache_flags: list[bool] = []
        missing: list[str] = []
        warnings: list[dict] = []
        for sym in symbols:
            su = sym.upper()
            try:
                pts, quality, cache_hit, _quote = self._history(sym, range_, interval, as_of)
            except Exception as exc:
                missing.append(su)
                warnings.append({"code": "UPSTREAM_ERROR", "scope": su, "detail": str(exc)[:200]})
                continue
            cache_flags.append(cache_hit)
            quality_by_symbol[su] = quality
            if quality["dropped"] or quality["deduped"] or not quality["input_sorted"]:
                warnings.append({
                    "code": "OHLCV_CLEANED",
                    "scope": su,
                    "detail": (
                        f"cleaned {quality['raw']} raw bars to {quality['clean']} bars "
                        f"(dropped {quality['dropped']}, deduped {quality['deduped']})"
                    ),
                })
            closes = {p["d"]: float(p["c"]) for p in pts if p.get("c") is not None}
            if closes:
                per_symbol[su] = closes
            else:
                missing.append(su)

        resolved = list(per_symbol.keys())
        if not resolved:
            panel = PricePanel([], np.zeros((0, 0)), [], missing, quality_by_symbol)
            prov = _envelope(
                {"cleaning": quality_by_symbol}, source=_SOURCE, as_of=as_of or _now_iso(),
                coverage={"requested": len(symbols), "resolved": 0, "missing": missing},
                cost_class="network", credits=len(symbols), freshness="mock", partial=True,
                warnings=warnings + [{"code": "PARTIAL_COVERAGE", "scope": None,
                                      "detail": "no symbols resolved"}],
                cache_hit=bool(cache_flags) and all(cache_flags),
            )
            return panel, prov

        common = set.intersection(*(set(per_symbol[s]) for s in resolved))
        dates = sorted(common)
        closes = np.array([[per_symbol[s][d] for s in resolved] for d in dates], dtype=float)

        if missing:
            warnings.append({"code": "PARTIAL_COVERAGE", "scope": ",".join(missing),
                             "detail": "symbols dropped (no overlapping data)"})
        prov = _envelope(
            {"dates": len(dates), "symbols": resolved, "cleaning": quality_by_symbol},
            source=_SOURCE, as_of=as_of or _now_iso(),
            coverage={"requested": len(symbols), "resolved": len(resolved), "missing": missing},
            cost_class="network", credits=len(symbols), partial=bool(missing), warnings=warnings,
            cache_hit=bool(cache_flags) and all(cache_flags),
        )
        return PricePanel(dates, closes, resolved, missing, quality_by_symbol), prov
