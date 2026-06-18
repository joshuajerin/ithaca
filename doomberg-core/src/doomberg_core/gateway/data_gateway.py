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

import numpy as np

from ..sources import prices as _prices

__all__ = ["DataGateway", "PricePanel"]

_SOURCE = "yahoo-chart"
_PIT = "false"  # Yahoo is restated + survivorship-biased; not point-in-time. Honest by default.


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(data, *, source, as_of, coverage, cost_class, credits, freshness="live",
              partial=False, warnings=None) -> dict:
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
            "cache_hit": False,
        },
        "partial": partial,
        "warnings": warnings or [],
    }


class PricePanel:
    """An aligned close-price matrix for a universe: dates (T) x symbols (N)."""

    __slots__ = ("dates", "closes", "symbols", "missing")

    def __init__(self, dates: list[str], closes: np.ndarray, symbols: list[str], missing: list[str]):
        self.dates = dates
        self.closes = closes
        self.symbols = symbols
        self.missing = missing


class DataGateway:
    """Stateless facade. ``fetch`` is injectable so tests run without network."""

    def __init__(self, fetch_history=_prices.fetch_price_history):
        self._fetch = fetch_history

    # ---- agent-facing tool ------------------------------------------------------------
    def get_ohlcv(self, symbol: str, range_: str = "6mo", interval: str = "1d",
                  as_of: str | None = None) -> dict:
        """Single-symbol OHLCV, wrapped in a provenance envelope (the market.get_ohlcv tool)."""
        try:
            raw = self._fetch(symbol, range_, interval)
        except Exception as exc:  # honest failure, not silent mock
            return _envelope(
                None, source=_SOURCE, as_of=_now_iso(),
                coverage={"requested": 1, "resolved": 0, "missing": [symbol.upper()]},
                cost_class="network", credits=1, freshness="mock", partial=True,
                warnings=[{"code": "UPSTREAM_ERROR", "scope": symbol.upper(), "detail": str(exc)[:200]}],
            )
        points = raw.get("points") or []
        if as_of:
            points = [p for p in points if p["d"] <= as_of]
        data = {"symbol": symbol.upper(), "points": points, "quote": raw.get("quote") or {}}
        as_of_ts = (raw.get("quote") or {}).get("asOf")
        return _envelope(
            data, source=_SOURCE, as_of=as_of_ts or _now_iso(),
            coverage={"requested": 1, "resolved": 1 if points else 0,
                      "missing": [] if points else [symbol.upper()]},
            cost_class="network", credits=1, partial=not points,
        )

    # ---- worker/backtest-facing -------------------------------------------------------
    def price_panel(self, symbols: list[str], range_: str = "1y", interval: str = "1d",
                    as_of: str | None = None) -> tuple[PricePanel, dict]:
        """Aligned close matrix over the common trading days of ``symbols``.

        Missing symbols are REPORTED in coverage, never imputed. Returns (PricePanel, provenance).
        """
        per_symbol: dict[str, dict[str, float]] = {}
        missing: list[str] = []
        for sym in symbols:
            su = sym.upper()
            try:
                raw = self._fetch(sym, range_, interval)
            except Exception:
                missing.append(su)
                continue
            pts = raw.get("points") or []
            if as_of:
                pts = [p for p in pts if p["d"] <= as_of]
            closes = {p["d"]: float(p["c"]) for p in pts if p.get("c") is not None}
            if closes:
                per_symbol[su] = closes
            else:
                missing.append(su)

        resolved = list(per_symbol.keys())
        if not resolved:
            panel = PricePanel([], np.zeros((0, 0)), [], missing)
            prov = _envelope(
                None, source=_SOURCE, as_of=as_of or _now_iso(),
                coverage={"requested": len(symbols), "resolved": 0, "missing": missing},
                cost_class="network", credits=len(symbols), freshness="mock", partial=True,
                warnings=[{"code": "PARTIAL_COVERAGE", "scope": None,
                           "detail": "no symbols resolved"}],
            )
            return panel, prov

        common = set.intersection(*(set(per_symbol[s]) for s in resolved))
        dates = sorted(common)
        closes = np.array([[per_symbol[s][d] for s in resolved] for d in dates], dtype=float)

        warnings = []
        if missing:
            warnings.append({"code": "PARTIAL_COVERAGE", "scope": ",".join(missing),
                             "detail": "symbols dropped (no overlapping data)"})
        prov = _envelope(
            {"dates": len(dates), "symbols": resolved},
            source=_SOURCE, as_of=as_of or _now_iso(),
            coverage={"requested": len(symbols), "resolved": len(resolved), "missing": missing},
            cost_class="network", credits=len(symbols), partial=bool(missing), warnings=warnings,
        )
        return PricePanel(dates, closes, resolved, missing), prov
