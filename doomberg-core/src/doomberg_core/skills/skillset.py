"""The Skill catalog over the v1 archive.

``SkillSet(archive)`` exposes one method per agent-callable tool in the contract's catalog. Each
method reads ONLY through the :class:`ArchiveGateway` (``self.archive``), reshapes the rows using
the v1 ``build_*`` shaping logic, and returns the provenance envelope. Args are declarative dicts
(``params``) — no agent code runs. ``SKILLS`` maps the canonical MCP tool name to the method name,
exactly like ``api.TOOLS`` does for the core data tools (kept SEPARATE to avoid conflicts).

If ``archive is None`` (the production server before Stream 1 is synced), every skill returns a
clear ``ARCHIVE_UNAVAILABLE`` warning with ``data=None`` rather than crashing.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

import numpy as np

from .. import engine
from . import compute
from .archive import ArchiveGateway
from .extended_skills import ExtendedSkills
from .short_skills import ShortSkills
from .macro_extended import MacroExtendedSkills
from .financials_skills import FinancialsSkills
from .congress_extended_skills import CongressExtendedSkills
from .envelope import (
    ARCHIVE_UNAVAILABLE,
    computed_envelope,
    consensus_label,
    envelope,
    fmt_usd,
    freshness_of,
    warn,
)

__all__ = ["SkillSet", "SKILLS"]

# Default style-factor descriptors for the multi-factor risk/optimizer skills, derived
# from archive fundamentals. Market = beta; Size = -log(mcap); Value = earnings yield
# (eps/price); Momentum = trailing return; Quality = net margin.
_FACTOR_NAMES = ["Market", "Size", "Value", "Momentum", "Quality"]

# When a COMPUTED skill runs its math over REAL archive series (not agent-supplied scalars),
# its provenance records where the numbers came from so the result stays honest.
ARCHIVE_INPUTS = "doomberg-v1-archive"

# Open-market discretionary insider codes: P = buy, S = sell. Option exercises (M/X) and grants
# are reported but excluded from the directional net-buy/sell signal.
_INSIDER_BUY = "P"
_INSIDER_SELL = "S"
_INSIDER_OPTION = {"M", "X"}

_CONGRESS_LARGE_THRESHOLD = 100_000.0
_CONGRESS_CLUSTER_MIN = 2


def _f(v: Any) -> float | None:
    """Best-effort float (None-safe)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def _req_float(params: dict, *names: str) -> float:
    """Required positive-or-any float from the first present key in ``names``."""
    for n in names:
        v = _f(params.get(n))
        if v is not None:
            return v
    raise ValueError(f"missing required numeric parameter (one of {names!r}).")


class SkillSet:
    """Declarative, archive-backed skills. ``archive`` is duck-typed to ``ArchiveGateway``."""

    def __init__(self, archive: ArchiveGateway | None):
        self.archive = archive
        self._ext = ExtendedSkills(archive)
        self._short = ShortSkills(archive)
        self._macro = MacroExtendedSkills(archive)
        self._fin = FinancialsSkills(archive)
        self._cong_ext = CongressExtendedSkills(archive)

    # ----------------------------- gate -----------------------------
    def _unavailable(self) -> dict:
        return envelope(None, freshness=None, pit=False, warnings=[dict(ARCHIVE_UNAVAILABLE)])

    def _computed_unavailable(self) -> dict:
        """ARCHIVE_UNAVAILABLE gate for a COMPUTED skill that reads archive series."""
        return computed_envelope(None, freshness=None, inputs=ARCHIVE_INPUTS,
                                 warnings=[dict(ARCHIVE_UNAVAILABLE)])

    @property
    def available(self) -> bool:
        return self.archive is not None

    # ============================== market.* ==============================
    def market_news(self, params: dict) -> dict:
        """Recent headlines for a ticker / sector (build_news), real news rows only."""
        if not self.available:
            return self._unavailable()
        ticker = (params.get("ticker") or params.get("symbol") or "").strip().upper() or None
        sector = (params.get("sector") or params.get("scope") or "").strip() or None
        limit = _i(params.get("limit"), 50, 1, 200)
        rows = self.archive.news(ticker=ticker, sector=sector, limit=limit)
        items = []
        for r in rows:
            items.append({
                "id": r.get("id"),
                "headline": r.get("headline"),
                "source": r.get("source"),
                "summary": r.get("summary"),
                "url": r.get("url"),
                "publishedAt": r.get("published_at"),
                "sentiment": r.get("sentiment"),
                "tickers": r.get("tickers") or [],
                "sector": r.get("sector"),
            })
        pos = sum(1 for i in items if i.get("sentiment") == "positive")
        neg = sum(1 for i in items if i.get("sentiment") == "negative")
        scope = ticker or sector or "Markets"
        as_of = max((i["publishedAt"] for i in items if i.get("publishedAt")), default=None)
        data = {
            "scope": scope,
            "items": items,
            "count": len(items),
            "sentimentMix": {"positive": pos, "negative": neg, "neutral": len(items) - pos - neg},
            "asOf": as_of,
        }
        return envelope(data, freshness=freshness_of(rows))

    def market_screener(self, params: dict) -> dict:
        """Ranked equity screen over the tracked universe (build_screener): fundamentals
        joined with a trailing 1Y price return from the archive ohlcv panel."""
        if not self.available:
            return self._unavailable()
        sector = (params.get("sector") or params.get("scope") or "").strip() or None
        limit = _i(params.get("limit"), 100, 1, 500)
        rows_f, syms = self._universe_fundamentals(sector)
        rets = self._trailing_returns(syms)
        out = []
        for c in rows_f:
            sym = (c.get("symbol") or "").upper()
            out.append({
                "symbol": sym,
                "name": c.get("name") or sym,
                "price": _f(c.get("price")),
                "changePct": _f(c.get("change_pct")),
                "ret1Y": rets.get(sym),
                "marketCap": _f(c.get("market_cap")),
                "peRatio": _f(c.get("pe_ratio")),
                "volume": _f(c.get("volume")),
                "sector": c.get("sector"),
            })
        out.sort(key=lambda r: (r["marketCap"] or 0.0), reverse=True)
        out = out[:limit]
        title = f"{sector} Screener" if sector else "Market Screener"
        data = {"title": title, "rows": out, "count": len(out)}
        return envelope(data, freshness=freshness_of(rows_f))

    def market_movers(self, params: dict) -> dict:
        """Heatmap-style movers (build_heatmap): cells with the 1D move + trailing 1Y return."""
        if not self.available:
            return self._unavailable()
        sector = (params.get("sector") or params.get("scope") or "").strip() or None
        limit = _i(params.get("limit"), 100, 1, 500)
        rows_f, syms = self._universe_fundamentals(sector)
        rets = self._trailing_returns(syms)
        cells = []
        for c in rows_f:
            sym = (c.get("symbol") or "").upper()
            cells.append({
                "symbol": sym,
                "name": c.get("name") or sym,
                "changePct": _f(c.get("change_pct")),
                "ret1Y": rets.get(sym),
                "marketCap": _f(c.get("market_cap")),
                "sector": c.get("sector"),
            })
        cells.sort(key=lambda x: (x["marketCap"] or 0.0), reverse=True)
        cells = cells[:limit]
        ranked = sorted([c for c in cells if c["changePct"] is not None],
                        key=lambda c: c["changePct"], reverse=True)
        title = f"{sector} Heatmap" if sector else "Market Overview"
        data = {
            "title": title,
            "cells": cells,
            "gainers": ranked[:5],
            "losers": ranked[-5:][::-1] if len(ranked) >= 5 else ranked[::-1],
        }
        return envelope(data, freshness=freshness_of(rows_f))

    def _universe_fundamentals(self, sector: str | None) -> tuple[list[dict], list[str]]:
        """Fundamentals rows for the tracked universe, optionally filtered to one sector."""
        uni = self.archive.universe(tracked_only=True)
        if sector:
            sl = sector.strip().lower()
            uni = [u for u in uni if (u.get("sector") or "").lower() == sl]
        syms = [(u.get("symbol") or "").upper() for u in uni if u.get("symbol")]
        rows = self.archive.fundamentals(syms) if syms else []
        return rows, syms

    def _trailing_returns(self, symbols: list[str]) -> dict[str, float | None]:
        """Trailing return over the archive's available daily closes for each symbol."""
        out: dict[str, float | None] = {}
        for sym in symbols:
            bars = self.archive.ohlcv(sym)
            closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]
            if len(closes) >= 2 and closes[0]:
                out[sym] = round((closes[-1] - closes[0]) / closes[0] * 100.0, 2)
            else:
                out[sym] = None
        return out

    # ---- shared archive-series helpers used by the COMPUTED skills ----
    def _closes(self, symbol: str, start: str | None = None) -> list[float]:
        bars = self.archive.ohlcv(symbol, start=start)
        return [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]

    def _points(self, symbol: str, start: str | None = None) -> list[dict]:
        """Archive ohlcv as {t, c} points (the shape the engine signal/portfolio code expects)."""
        bars = self.archive.ohlcv(symbol, start=start)
        return [{"t": b.get("d"), "c": _f(b.get("c"))}
                for b in bars if _f(b.get("c")) is not None]

    def _returns_by_symbol(self, symbols: list[str]) -> tuple[dict[str, np.ndarray], list[str]]:
        """Per-symbol simple-return arrays from real archive closes; drops empties."""
        out: dict[str, np.ndarray] = {}
        missing: list[str] = []
        for s in symbols:
            r = compute.simple_returns(self._closes(s))
            if r.size >= 2:
                out[s] = r
            else:
                missing.append(s)
        return out, missing

    def _resolve_universe(self, params: dict, default_min: int = 2) -> list[str]:
        """Symbols from explicit ``symbols``, a ``sector``, or the tracked universe."""
        syms = [s.upper().strip().lstrip("$") for s in (params.get("symbols") or []) if s]
        if syms:
            return syms
        sector = (params.get("sector") or "").strip() or None
        uni = self.archive.universe(tracked_only=True)
        if sector:
            sl = sector.lower()
            uni = [u for u in uni if (u.get("sector") or "").lower() == sl]
        return [(u.get("symbol") or "").upper() for u in uni if u.get("symbol")]

    def _factor_exposures(self, symbols: list[str]) -> tuple[list[str], np.ndarray, list[dict]]:
        """Build a (N,K) standardized style-exposure matrix from archive fundamentals.

        Columns: Market (beta), Size (-log mcap), Value (eps/price), Momentum (trailing
        return), Quality (net margin). Names missing every descriptor are dropped and
        reported. Returns ``(resolved_symbols, exposures, used_rows)``.
        """
        rows = self.archive.fundamentals(symbols)
        by = {(r.get("symbol") or "").upper(): r for r in rows}
        rets = self._trailing_returns(symbols)
        beta, size, value, mom, qual, resolved = [], [], [], [], [], []
        for s in symbols:
            r = by.get(s)
            if not r:
                continue
            price = _f(r.get("price"))
            mcap = _f(r.get("market_cap"))
            eps = _f(r.get("eps"))
            beta.append(_f(r.get("beta")) if _f(r.get("beta")) is not None else np.nan)
            size.append(-np.log(mcap) if (mcap and mcap > 0) else np.nan)
            value.append((eps / price) if (eps is not None and price) else np.nan)
            mom.append(rets.get(s) if rets.get(s) is not None else np.nan)
            qual.append(_f(r.get("net_margin")) if _f(r.get("net_margin")) is not None else np.nan)
            resolved.append(s)
        if not resolved:
            return [], np.zeros((0, len(_FACTOR_NAMES))), []
        cols = []
        for raw in (beta, size, value, mom, qual):
            z, _, _ = engine.riskmodel.standardize(np.asarray(raw, dtype=float))
            cols.append(z)
        exposures = np.column_stack(cols)
        used = [by[s] for s in resolved]
        return resolved, exposures, used

    # ============================== COMPUTED: options.* ==============================
    def options_greeks(self, params: dict) -> dict:
        """Black-Scholes price + greeks for ONE European option on agent-supplied inputs.

        Pure math (``compute.bs_price`` + ``compute.bs_greeks``) — every input (S, K, T, r,
        sigma, type) is supplied by the agent, so ``source=computed``/``inputs=agent``. No archive
        is read and no market data is fabricated. ``T`` is in years, ``r``/``sigma`` are decimals
        (e.g. 0.05, 0.2)."""
        S = _req_float(params, "S", "spot")
        K = _req_float(params, "K", "strike")
        T = _req_float(params, "T", "tenor", "years")
        r = _f(params.get("r"))
        if r is None:
            r = _f(params.get("rate")) or 0.0
        sigma = _req_float(params, "sigma", "vol", "volatility")
        opt = (params.get("type") or params.get("option_type") or "call").lower()
        if opt not in ("call", "put"):
            raise ValueError("options.greeks 'type' must be 'call' or 'put'.")
        price = compute.bs_price(S, K, T, r, sigma, opt)
        greeks = compute.bs_greeks(S, K, T, r, sigma, opt)
        data = {
            "type": opt,
            "inputs": {"S": S, "K": K, "T": T, "r": r, "sigma": sigma},
            "price": round(price, 6),
            "greeks": greeks,
        }
        return computed_envelope(data, inputs="agent")

    def options_implied_vol(self, params: dict) -> dict:
        """Implied volatility from an observed option PRICE via BS bisection (agent inputs).

        Returns ``impliedVol=None`` with a NO_SOLUTION warning when the price is outside the
        model's arbitrage-free band (e.g. below intrinsic) rather than fabricating a number."""
        price = _req_float(params, "price", "premium")
        S = _req_float(params, "S", "spot")
        K = _req_float(params, "K", "strike")
        T = _req_float(params, "T", "tenor", "years")
        r = _f(params.get("r"))
        if r is None:
            r = _f(params.get("rate")) or 0.0
        opt = (params.get("type") or params.get("option_type") or "call").lower()
        if opt not in ("call", "put"):
            raise ValueError("options.implied_vol 'type' must be 'call' or 'put'.")
        iv = compute.bs_implied_vol(price, S, K, T, r, opt)
        data = {
            "type": opt,
            "inputs": {"price": price, "S": S, "K": K, "T": T, "r": r},
            "impliedVol": iv,
        }
        warnings = None if iv is not None else [
            warn("NO_SOLUTION", scope=opt,
                 detail="price is outside the model's arbitrage-free band (e.g. below intrinsic)")]
        return computed_envelope(data, inputs="agent", warnings=warnings)

    # ============================== COMPUTED: vol.* ==============================
    def vol_realized(self, params: dict) -> dict:
        """Annualized realized (close-to-close log-return) vol over real archive closes.

        The math is computed, but it runs on REAL archive prices, so ``inputs=doomberg-v1-archive``
        and the archive's freshness rides along on the envelope."""
        if not self.available:
            return self._computed_unavailable()
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("vol.realized needs a 'symbol'.")
        lookback = _i(params.get("lookback"), 0, 0, 100_000)
        bars = self.archive.ohlcv(symbol)
        closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]
        if lookback and len(closes) > lookback + 1:
            closes = closes[-(lookback + 1):]
        rv = compute.realized_vol(closes)
        data = {"symbol": symbol, "lookback": lookback or None, "observations": max(len(closes) - 1, 0),
                "realizedVol": rv}
        warnings = None if rv is not None else [
            warn("PARTIAL_COVERAGE", scope=symbol, detail="fewer than 2 usable closes")]
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS,
                                 warnings=warnings)

    def vol_term_structure(self, params: dict) -> dict:
        """Realized-vol term structure: annualized realized vol at several trailing windows.

        Windows default to [20, 60, 120, 252] trading days; each point uses the trailing
        ``window`` closes. Windows longer than the available history are reported as ``None``."""
        if not self.available:
            return self._computed_unavailable()
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("vol.term_structure needs a 'symbol'.")
        windows = params.get("windows") or [20, 60, 120, 252]
        windows = sorted({_i(w, 20, 2, 100_000) for w in windows})
        bars = self.archive.ohlcv(symbol)
        closes = [_f(b.get("c")) for b in bars if _f(b.get("c")) is not None]
        points = []
        for w in windows:
            tail = closes[-(w + 1):] if len(closes) >= 2 else closes
            rv = compute.realized_vol(tail) if len(tail) >= w + 1 else None
            points.append({"window": w, "realizedVol": rv,
                           "observations": max(len(tail) - 1, 0) if rv is not None else 0})
        slope = None
        solved = [p for p in points if p["realizedVol"] is not None]
        if len(solved) >= 2:
            slope = round(solved[-1]["realizedVol"] - solved[0]["realizedVol"], 6)
        data = {"symbol": symbol, "points": points, "slope": slope,
                "availableCloses": len(closes)}
        warnings = None if solved else [
            warn("PARTIAL_COVERAGE", scope=symbol, detail="not enough history for any window")]
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS,
                                 warnings=warnings)

    # ============================== COMPUTED: correlation.* / factor.* ==============================
    def correlation_matrix(self, params: dict) -> dict:
        """Pearson correlation matrix of daily returns across symbols, on real archive closes.

        Each cell is computed from the per-symbol simple-return series (aligned to the common
        tail). The matrix is symmetric with a 1.0 diagonal; symbols with too little history are
        dropped and reported."""
        if not self.available:
            return self._computed_unavailable()
        symbols = self._resolve_universe(params)
        if len(symbols) < 2:
            raise ValueError("correlation.matrix needs at least 2 symbols.")
        lookback = _i(params.get("lookback"), 0, 0, 100_000)
        rets, missing = self._returns_by_symbol(symbols)
        if lookback:
            rets = {s: (r[-lookback:] if r.size > lookback else r) for s, r in rets.items()}
        syms, cm = compute.correlation_matrix(rets)
        # round for transport; keep exact 1.0 diagonal
        matrix = [[round(float(cm[i][j]), 6) for j in range(len(syms))] for i in range(len(syms))]
        data = {
            "symbols": syms,
            "matrix": matrix,
            "lookback": lookback or None,
            "pairs": [
                {"a": syms[i], "b": syms[j], "corr": matrix[i][j]}
                for i in range(len(syms)) for j in range(i + 1, len(syms))
            ],
        }
        warnings = ([warn("PARTIAL_COVERAGE", scope=",".join(missing), detail="insufficient history")]
                    if missing else None)
        bars = [b for s in syms for b in self.archive.ohlcv(s)]
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS,
                                 warnings=warnings)

    def factor_exposures(self, params: dict) -> dict:
        """Standardized style-factor exposure matrix (Market/Size/Value/Momentum/Quality).

        Built from archive fundamentals via ``engine.riskmodel.standardize`` (cross-sectional
        z-scores). The numbers are computed transforms of real archive descriptors, so
        ``inputs=doomberg-v1-archive``."""
        if not self.available:
            return self._computed_unavailable()
        symbols = self._resolve_universe(params)
        if len(symbols) < 2:
            raise ValueError("factor.exposures needs at least 2 symbols (cross-sectional z-scores).")
        resolved, exposures, used = self._factor_exposures(symbols)
        missing = [s for s in symbols if s not in resolved]
        rows = []
        for i, s in enumerate(resolved):
            rows.append({"symbol": s,
                         "exposures": {name: round(float(exposures[i][k]), 6)
                                       for k, name in enumerate(_FACTOR_NAMES)}})
        data = {"factors": list(_FACTOR_NAMES), "symbols": resolved, "rows": rows}
        warnings = ([warn("PARTIAL_COVERAGE", scope=",".join(missing), detail="no fundamentals row")]
                    if missing else None)
        return computed_envelope(data, freshness=freshness_of(used), inputs=ARCHIVE_INPUTS,
                                 warnings=warnings)

    # ============================== COMPUTED: dcf.* ==============================
    def dcf_value(self, params: dict) -> dict:
        """5-year DCF valuation seeded from a symbol's archive fundamentals.

        ``base_revenue``/``shares``(=mcap/price)/``net_debt`` come from the archive fundamentals
        row; the agent may override any DCF assumption (revenueGrowth/ebitdaMargin/wacc/...). The
        valuation arithmetic is ``compute.dcf_value`` — deterministic, no randomness."""
        if not self.available:
            return self._computed_unavailable()
        symbol = (params.get("symbol") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("dcf.value needs a 'symbol'.")
        rows = self.archive.fundamentals([symbol])
        if not rows:
            return computed_envelope(
                {"symbol": symbol, "valuation": None}, freshness=None, inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol, detail="no fundamentals row")])
        c = rows[0]
        price = _f(c.get("price"))
        mcap = _f(c.get("market_cap"))
        revenue = _f(c.get("revenue"))
        if revenue is None or revenue <= 0:
            return computed_envelope(
                {"symbol": symbol, "valuation": None}, freshness=freshness_of(rows),
                inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol, detail="no revenue to seed DCF")])
        shares = (mcap / price) if (mcap and price) else None
        if not shares or shares <= 0:
            return computed_envelope(
                {"symbol": symbol, "valuation": None}, freshness=freshness_of(rows),
                inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol,
                               detail="cannot derive share count (need market_cap and price)")])
        net_debt = _f(c.get("net_debt")) or 0.0
        # Seed the long-run growth from the archive's revenue_growth when present (it's a fraction).
        assumptions = dict(params.get("assumptions") or {})
        rg = _f(c.get("revenue_growth"))
        if rg is not None and "revenueGrowth" not in assumptions:
            assumptions["revenueGrowth"] = round(rg * 100.0, 2)
        valuation = compute.dcf_value(revenue, shares, net_debt, assumptions)
        upside = (round((valuation["impliedPrice"] - price) / price * 100.0, 2)
                  if (price and valuation["impliedPrice"]) else None)
        data = {
            "symbol": symbol,
            "name": c.get("name") or symbol,
            "inputs": {"baseRevenue": revenue, "shares": round(shares, 0), "netDebt": net_debt,
                       "currentPrice": price, "assumptions": assumptions},
            "valuation": valuation,
            "impliedUpsidePct": upside,
        }
        return computed_envelope(data, freshness=freshness_of(rows), inputs=ARCHIVE_INPUTS)

    # ============================== COMPUTED: portfolio.* ==============================
    def portfolio_optimize(self, params: dict) -> dict:
        """Mean-variance optimal weights over real archive returns (long-only by default).

        Builds the annualized covariance + mean-return vector from real archive return series,
        then runs ``engine.optimize.mean_variance`` (constrained projection). ``mode`` is one of
        ``max_sharpe`` (default), ``min_variance``, ``target_vol``. Weights are long-only and sum
        to ~1.0 (the constraint's ``net``)."""
        if not self.available:
            return self._computed_unavailable()
        symbols = self._resolve_universe(params)
        if len(symbols) < 2:
            raise ValueError("portfolio.optimize needs at least 2 symbols.")
        rets, missing = self._returns_by_symbol(symbols)
        syms = list(rets)
        if len(syms) < 2:
            return computed_envelope(
                {"weights": [], "symbols": syms}, freshness=None, inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=",".join(missing),
                               detail="need >=2 symbols with usable history")])
        cov_syms, cov = compute.covariance_matrix({s: rets[s] for s in syms})
        # Annualized mean return per symbol (aligned to cov_syms order).
        mu = np.array([float(np.mean(rets[s])) * compute.TRADING_DAYS for s in cov_syms])
        mode = (params.get("mode") or "max_sharpe").lower()
        if mode not in ("max_sharpe", "min_variance", "target_vol"):
            mode = "max_sharpe"
        cons = engine.optimize.Constraints(long_only=True, net=1.0)
        result = engine.optimize.mean_variance(mu, cov, mode=mode, cons=cons)
        w = np.asarray(result.weights, dtype=float)
        stats = engine.optimize.portfolio_stats(w, mu, cov)
        weights = [{"symbol": cov_syms[i], "weight": round(float(w[i]), 6)} for i in range(len(cov_syms))]
        weights.sort(key=lambda x: x["weight"], reverse=True)
        data = {
            "mode": mode,
            "symbols": cov_syms,
            "weights": weights,
            "sumWeights": round(float(w.sum()), 6),
            "longOnly": True,
            "stats": {"expReturn": round(stats["expReturn"], 6), "vol": round(stats["vol"], 6),
                      "sharpe": round(stats["sharpe"], 6), "gross": round(stats["gross"], 6),
                      "net": round(stats["net"], 6)},
            "binding": result.binding,
        }
        warnings = ([warn("PARTIAL_COVERAGE", scope=",".join(missing), detail="dropped (no history)")]
                    if missing else None)
        bars = [b for s in cov_syms for b in self.archive.ohlcv(s)]
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS,
                                 warnings=warnings)

    # ============================== COMPUTED: montecarlo.* / scenario.* ==============================
    def montecarlo_simulate(self, params: dict) -> dict:
        """GBM (or bootstrap) terminal-price distribution via ``engine.montecarlo.monte_carlo``.

        Deterministic: the RNG ``seed`` is supplied in params (default 12345). Drives the
        simulation from a real archive symbol's return history when ``symbol`` is given, else from
        agent-supplied ``sigma``/``drift`` (a synthetic normal return sample built from those)."""
        horizon = _i(params.get("horizon"), 252, 1, 5000)
        n_paths = _i(params.get("paths") or params.get("n_paths"), 1000, 100, 100_000)
        seed = _i(params.get("seed"), 12345, 0, 2**31 - 1)
        method = (params.get("method") or "gbm").lower()
        if method not in ("gbm", "bootstrap"):
            method = "gbm"
        symbol = (params.get("symbol") or "").upper().strip().lstrip("$")
        if symbol:
            if not self.available:
                return self._computed_unavailable()
            closes = self._closes(symbol)
            returns = compute.simple_returns(closes)
            if returns.size < 5:
                return computed_envelope(
                    {"symbol": symbol, "fan": [], "summary": None}, freshness=None,
                    inputs=ARCHIVE_INPUTS,
                    warnings=[warn("PARTIAL_COVERAGE", scope=symbol,
                                   detail="insufficient history for simulation")])
            start_value = _f(params.get("S")) or _f(params.get("start_value")) or (
                float(closes[-1]) if closes else 100.0)
            sim = engine.montecarlo.monte_carlo(returns, start_value=start_value, horizon=horizon,
                                                n_paths=n_paths, method=method, seed=seed)
            data = {"symbol": symbol, **sim}
            bars = self.archive.ohlcv(symbol)
            return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)
        # Agent-supplied GBM: build a deterministic synthetic daily-return sample from drift+sigma.
        sigma = _req_float(params, "sigma", "vol", "volatility")  # ANNUAL vol
        drift = _f(params.get("drift"))
        if drift is None:
            drift = _f(params.get("mu")) or 0.0  # ANNUAL drift
        start_value = _f(params.get("S")) or _f(params.get("start_value")) or 100.0
        daily_mu = drift / compute.TRADING_DAYS
        daily_sigma = sigma / math.sqrt(compute.TRADING_DAYS)
        rng = np.random.default_rng(seed)
        sample = daily_mu + daily_sigma * rng.standard_normal(max(60, compute.TRADING_DAYS))
        sim = engine.montecarlo.monte_carlo(sample, start_value=start_value, horizon=horizon,
                                            n_paths=n_paths, method=method, seed=seed)
        data = {"symbol": None, "inputs": {"S": start_value, "sigma": sigma, "drift": drift,
                                           "seed": seed}, **sim}
        return computed_envelope(data, inputs="agent")

    def scenario_project(self, params: dict) -> dict:
        """Baseline-vs-scenario forward projection (``engine.scenario.project_scenario``).

        Baseline is Monte-Carlo over a real symbol's return history; the scenario layers an
        explicit incremental annualized drift (``scenarioDriftPct``) on top — clearly labeled, not
        silently mixed in. Deterministic via a fixed ``seed``."""
        if not self.available:
            return self._computed_unavailable()
        symbol = (params.get("symbol") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("scenario.project needs a 'symbol'.")
        closes = self._closes(symbol)
        returns = compute.simple_returns(closes)
        if returns.size < 5:
            return computed_envelope(
                {"symbol": symbol, "path": [], "baseline": None, "scenario": None}, freshness=None,
                inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol,
                               detail="insufficient history for a scenario projection")])
        drift_pct = _f(params.get("scenarioDriftPct"))
        if drift_pct is None:
            drift_pct = _f(params.get("driftPct")) or 0.0
        horizon = _i(params.get("horizon"), 252, 1, 5000)
        n_paths = _i(params.get("paths") or params.get("n_paths"), 1000, 100, 100_000)
        seed = _i(params.get("seed"), 4242, 0, 2**31 - 1)
        start_value = _f(params.get("start_value")) or (float(closes[-1]) if closes else 100.0)
        proj = engine.scenario.project_scenario(returns, drift_pct, horizon=horizon,
                                                n_paths=n_paths, start_value=start_value, seed=seed)
        data = {"symbol": symbol, "scenarioDriftPct": drift_pct, **proj}
        bars = self.archive.ohlcv(symbol)
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ============================== COMPUTED: risk.* ==============================
    def risk_stress(self, params: dict) -> dict:
        """Estimate a book's P&L under agent-supplied shocks (``engine.stress``).

        Two shock kinds (both grounded in agent-supplied inputs, source=computed):
        - factor shocks: ``exposures`` (factor -> portfolio exposure) x ``shocks`` (factor -> %)
        - asset shocks: ``weights`` (symbol -> NAV fraction) x ``shocks`` (symbol -> %).
        Pure arithmetic — nothing is imputed or fetched."""
        shocks = params.get("shocks") or {}
        if not isinstance(shocks, dict) or not shocks:
            raise ValueError("risk.stress needs a non-empty 'shocks' map.")
        exposures = params.get("exposures")
        weights = params.get("weights")
        if exposures:
            kind = "factor"
            result = engine.stress.factor_shock_pnl(
                {str(k): _f(v) for k, v in exposures.items() if _f(v) is not None},
                {str(k): _f(v) for k, v in shocks.items() if _f(v) is not None})
        elif weights:
            kind = "asset"
            result = engine.stress.asset_shock_pnl(
                {str(k): _f(v) for k, v in weights.items() if _f(v) is not None},
                {str(k): _f(v) for k, v in shocks.items() if _f(v) is not None})
        else:
            raise ValueError("risk.stress needs either 'exposures' (factor) or 'weights' (asset).")
        data = {"kind": kind, **result}
        return computed_envelope(data, inputs="agent")

    # ============================== COMPUTED: backtest tearsheet / walk-forward ==============================
    def tearsheet(self, params: dict) -> dict:
        """Single-strategy backtest tearsheet over a symbol's REAL archive closes.

        Wraps ``engine.backtest.run_backtest`` (curve, drawdown, trade log, full stat block) on
        the archive ohlcv points. The math is computed but the price series is real archive data,
        so ``inputs=doomberg-v1-archive``."""
        if not self.available:
            return self._computed_unavailable()
        symbol = (params.get("symbol") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("tearsheet needs a 'symbol'.")
        points = self._points(symbol)
        if len([p for p in points if p.get("c")]) < 3:
            return computed_envelope(
                {"symbol": symbol, "tearsheet": None}, freshness=None, inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol,
                               detail="insufficient price history for a backtest")])
        strategy = (params.get("strategy") or "momentum").strip()
        result = engine.backtest.run_backtest(
            points, strategy=strategy, params=params.get("params") or {},
            cost_bps=_f(params.get("cost_bps")) if _f(params.get("cost_bps")) is not None else 5.0)
        data = {"symbol": symbol, **result}
        bars = self.archive.ohlcv(symbol)
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    def walkforward_run(self, params: dict) -> dict:
        """Anchored walk-forward validation + overfitting diagnostics on real archive closes.

        Wraps ``engine.backtest.run_walk_forward``. Always carries a ``coverage`` block; when the
        real history is too short for >=2 out-of-sample folds it sets ``coverage.usable=False`` and
        explains why rather than fabricating folds."""
        if not self.available:
            return self._computed_unavailable()
        symbol = (params.get("symbol") or "").upper().strip().lstrip("$")
        if not symbol:
            raise ValueError("walkforward.run needs a 'symbol'.")
        points = self._points(symbol)
        if len([p for p in points if p.get("c")]) < 3:
            return computed_envelope(
                {"symbol": symbol, "walkforward": None}, freshness=None, inputs=ARCHIVE_INPUTS,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol,
                               detail="insufficient price history for walk-forward validation")])
        strategy = (params.get("strategy") or "momentum").strip()
        n_splits = _i(params.get("n_splits"), 5, 2, 50)
        result = engine.backtest.run_walk_forward(points, strategy=strategy, n_splits=n_splits)
        data = {"symbol": symbol, **result}
        bars = self.archive.ohlcv(symbol)
        return computed_envelope(data, freshness=freshness_of(bars), inputs=ARCHIVE_INPUTS)

    # ============================== fundamentals.* ==============================
    def fundamentals_get(self, params: dict) -> dict:
        """Single-name fundamentals (build_fundamentals): metric cards from the archive row,
        with the latest available point-in-time report attached as context (still pit=False —
        the headline metrics are restated)."""
        if not self.available:
            return self._unavailable()
        symbol = (params.get("symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("fundamentals.get needs a 'symbol'.")
        rows = self.archive.fundamentals([symbol])
        if not rows:
            return envelope(
                {"symbol": symbol, "name": symbol, "metrics": [], "pending": True},
                freshness=None,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol, detail="no fundamentals row")],
            )
        c = rows[0]
        metrics = [
            {"label": "Last Price", "value": fmt_usd(_f(c.get("price"))), "change": _f(c.get("change_pct"))},
            {"label": "Market Cap", "value": fmt_usd(_f(c.get("market_cap"))), "change": None},
            {"label": "P/E (TTM)", "value": (f"{_f(c.get('pe_ratio')):.1f}" if _f(c.get("pe_ratio")) else "N/A"), "change": None},
            {"label": "Revenue (TTM)", "value": fmt_usd(_f(c.get("revenue"))), "change": None},
            {"label": "Net Margin", "value": (f"{_f(c.get('net_margin')):.1f}%" if _f(c.get("net_margin")) is not None else "—"), "change": None},
            {"label": "EPS (TTM)", "value": (f"${_f(c.get('eps')):.2f}" if _f(c.get("eps")) is not None else "—"), "change": None},
            {"label": "Dividend Yield", "value": (f"{_f(c.get('dividend_yield')):.2f}%" if _f(c.get("dividend_yield")) is not None else "—"), "change": None},
            {"label": "Beta", "value": (f"{_f(c.get('beta')):.2f}" if _f(c.get("beta")) is not None else "—"), "change": None},
            {"label": "52W High", "value": fmt_usd(_f(c.get("week52_high"))), "change": None},
            {"label": "52W Low", "value": fmt_usd(_f(c.get("week52_low"))), "change": None},
        ]
        latest_pit = self.archive.fundamentals_pit(symbol, date.today().isoformat())
        data = {
            "symbol": symbol,
            "name": c.get("name") or symbol,
            "metrics": metrics,
            "description": c.get("description"),
            "revenueGrowth": _f(c.get("revenue_growth")),
            "earningsDate": c.get("earnings_date"),
            "latestReport": (
                {"periodEnd": latest_pit.get("period_end"), "reportDate": latest_pit.get("report_date"),
                 "revenue": _f(latest_pit.get("revenue")), "eps": _f(latest_pit.get("eps"))}
                if latest_pit else None
            ),
        }
        return envelope(data, freshness=freshness_of(rows))

    def fundamentals_compare(self, params: dict) -> dict:
        """Peer comparison table (build_comparison) across the archive fundamentals rows."""
        if not self.available:
            return self._unavailable()
        symbols = [s.upper() for s in (params.get("symbols") or []) if s]
        if len(symbols) < 2:
            raise ValueError("fundamentals.compare needs at least 2 symbols.")
        rows = self.archive.fundamentals(symbols)
        by_sym = {(r.get("symbol") or "").upper(): r for r in rows}
        metric_labels = ["Price", "Mkt Cap", "P/E", "Rev (TTM)", "Net Margin", "EPS", "Div Yield", "Beta"]
        companies = []
        missing = []
        for s in symbols:
            c = by_sym.get(s)
            if not c:
                missing.append(s)
                continue
            companies.append({
                "symbol": s,
                "name": c.get("name") or s,
                "values": [
                    {"label": "Price", "value": fmt_usd(_f(c.get("price")))},
                    {"label": "Mkt Cap", "value": fmt_usd(_f(c.get("market_cap")))},
                    {"label": "P/E", "value": (f"{_f(c.get('pe_ratio')):.1f}" if _f(c.get("pe_ratio")) else "N/A")},
                    {"label": "Rev (TTM)", "value": fmt_usd(_f(c.get("revenue")))},
                    {"label": "Net Margin", "value": (f"{_f(c.get('net_margin')):.1f}%" if _f(c.get("net_margin")) is not None else "—")},
                    {"label": "EPS", "value": (f"${_f(c.get('eps')):.2f}" if _f(c.get("eps")) is not None else "—")},
                    {"label": "Div Yield", "value": (f"{_f(c.get('dividend_yield')):.2f}%" if _f(c.get("dividend_yield")) is not None else "—")},
                    {"label": "Beta", "value": (f"{_f(c.get('beta')):.2f}" if _f(c.get("beta")) is not None else "—")},
                ],
            })
        warnings = [warn("PARTIAL_COVERAGE", scope=",".join(missing))] if missing else None
        data = {
            "title": "Peer Comparison: " + " vs ".join(symbols),
            "metricLabels": metric_labels,
            "companies": companies,
        }
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    def fundamentals_pit(self, params: dict) -> dict:
        """THE PIT unlock: the latest report with report_date <= as_of (true point-in-time).

        This is the ONLY skill that returns ``pit: True`` — it reads ``fundamentals_pit``, whose
        rows are stamped with the real report (filing) date, so a backtest can ask 'what was known
        on date X?' without lookahead."""
        if not self.available:
            return self._unavailable()
        symbol = (params.get("symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("fundamentals.pit needs a 'symbol'.")
        as_of = params.get("as_of") or params.get("asOf") or date.today().isoformat()
        row = self.archive.fundamentals_pit(symbol, as_of)
        if not row:
            return envelope(
                {"symbol": symbol, "asOf": as_of, "report": None},
                freshness=None,
                pit=True,
                warnings=[warn("PARTIAL_COVERAGE", scope=symbol,
                               detail=f"no report on/before {as_of}")],
            )
        report = {
            "symbol": symbol,
            "periodEnd": row.get("period_end"),
            "reportDate": row.get("report_date"),
            "revenue": _f(row.get("revenue")),
            "netIncome": _f(row.get("net_income")),
            "netMargin": _f(row.get("net_margin")),
            "eps": _f(row.get("eps")),
            "estimated": bool(row.get("report_estimated")),
            "reportSource": row.get("source"),
        }
        data = {"symbol": symbol, "asOf": as_of, "report": report}
        return envelope(data, freshness=freshness_of([row]), pit=True)

    # ============================== analyst.* ==============================
    def analyst_ratings(self, params: dict) -> dict:
        """Wall Street consensus + price-target band + recent changes (build_analyst_ratings)."""
        if not self.available:
            return self._unavailable()
        symbol = (params.get("symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("analyst.ratings needs a 'symbol'.")
        rows = self.archive.analyst_ratings([symbol])
        if not rows:
            data = {"symbol": symbol, "name": symbol, "covered": False,
                    "note": f"No analyst coverage found for {symbol}."}
            return envelope(data, freshness=None,
                            warnings=[warn("PARTIAL_COVERAGE", scope=symbol)])
        r = rows[0]
        current = _f(r.get("current_price"))
        target_mean = _f(r.get("target_mean"))
        implied = (round((target_mean - current) / current * 100, 1)
                   if (target_mean and current) else None)
        distribution = {
            "strongBuy": r.get("strong_buy"), "buy": r.get("buy"), "hold": r.get("hold"),
            "sell": r.get("sell"), "strongSell": r.get("strong_sell"),
        }
        data = {
            "symbol": symbol,
            "name": r.get("name") or symbol,
            "covered": bool(r.get("covered")),
            "consensus": {
                "key": r.get("consensus_key"),
                "label": consensus_label(r.get("consensus_key"), _f(r.get("recommendation_mean"))),
                "mean": _f(r.get("recommendation_mean")),
                "numAnalysts": r.get("num_analysts"),
                "distribution": distribution,
            },
            "priceTarget": {
                "current": current,
                "mean": target_mean,
                "high": _f(r.get("target_high")),
                "low": _f(r.get("target_low")),
                "median": _f(r.get("target_median")),
                "impliedUpsidePct": implied,
            },
            "changes": (r.get("changes") or [])[:10],
        }
        return envelope(data, freshness=freshness_of(rows))

    # ============================== congress.* ==============================
    def congress_trades(self, params: dict) -> dict:
        """STOCK Act congressional disclosures (build_congress_trades) with notable highlights
        and an honest reporting-lag note."""
        if not self.available:
            return self._unavailable()
        ticker = (params.get("ticker") or params.get("symbol") or "").strip().upper() or None
        member = (params.get("member") or "").strip() or None
        limit = _i(params.get("limit"), 60, 5, 200)
        rows = self.archive.congress_trades(ticker=ticker, member=member, limit=limit)
        trades = []
        for r in rows:
            txn = (r.get("txn_type") or "").lower()
            t_type = "buy" if "buy" in txn or txn == "purchase" else (
                "sell" if "sell" in txn or "sale" in txn else (
                    "exchange" if "exchange" in txn else txn or None))
            lag = _lag_days(r.get("transaction_date"), r.get("disclosure_date"))
            trades.append({
                "id": r.get("id"),
                "member": r.get("member"),
                "chamber": r.get("chamber"),
                "party": r.get("party") or r.get("party_code"),
                "ticker": r.get("ticker"),
                "type": t_type,
                "amountRange": r.get("amount_range"),
                "amountLow": _f(r.get("amount_low")),
                "amountHigh": _f(r.get("amount_high")),
                "transactionDate": r.get("transaction_date"),
                "disclosureDate": r.get("disclosure_date"),
                "lagDays": lag,
                "url": r.get("source_url"),
            })
        buys = sum(1 for t in trades if t["type"] == "buy")
        sells = sum(1 for t in trades if t["type"] == "sell")
        exch = sum(1 for t in trades if t["type"] == "exchange")
        lags = [t["lagDays"] for t in trades if isinstance(t["lagDays"], int)]
        avg_lag = round(sum(lags) / len(lags), 1) if lags else None
        max_lag = max(lags) if lags else None
        members = {t["member"] for t in trades if t["member"]}
        scope = ticker or member or "Recent activity"
        data = {
            "scope": scope,
            "ticker": ticker,
            "trades": trades,
            "highlights": _congress_highlights(trades),
            "stats": {
                "total": len(trades), "buys": buys, "sells": sells, "exchanges": exch,
                "avgLagDays": avg_lag, "maxLagDays": max_lag, "uniqueMembers": len(members),
            },
            "lagNote": ("Members must disclose within ~45 days under the STOCK Act, so this "
                        "reflects activity from days-to-weeks ago, not real time."
                        + (f" Average lag here is {avg_lag:.0f} days." if avg_lag is not None else "")),
        }
        return envelope(data, freshness=freshness_of(rows))

    # ============================== insider.* ==============================
    def insider_activity(self, params: dict) -> dict:
        """SEC Form 4/5 insider transactions for one ticker (build_insider_activity) with a
        net open-market buy-vs-sell summary."""
        if not self.available:
            return self._unavailable()
        symbol = params.get("symbol") or (params.get("symbols") or [None])[0]
        if not symbol:
            raise ValueError("insider.activity needs a 'symbol'.")
        sym = str(symbol).upper().strip()
        limit = _i(params.get("limit"), 100, 1, 500)
        rows = self.archive.insider_transactions(sym, limit=limit)
        buy_shares = sell_shares = buy_value = sell_value = 0.0
        buy_count = sell_count = option_count = other_count = 0
        buyers: dict = {}
        sellers: dict = {}
        insiders: set = set()
        issuer = None
        out_rows = []
        for r in rows:
            issuer = issuer or r.get("issuer_name")
            insider = r.get("insider_name")
            if insider:
                insiders.add(insider)
            code = (r.get("transaction_code") or "").upper()
            shares = _f(r.get("shares")) or 0.0
            value = _f(r.get("value"))
            out_rows.append({
                "insider": insider, "role": r.get("role"), "code": code,
                "type": r.get("transaction_type"), "shares": shares, "price": _f(r.get("price")),
                "value": value, "transactionDate": r.get("transaction_date"),
                "filingDate": r.get("filing_date"), "form": r.get("form"), "url": r.get("url"),
            })
            if code == _INSIDER_BUY:
                buy_count += 1
                buy_shares += shares
                buy_value += value or 0.0
                b = buyers.setdefault(insider or "Unknown",
                                      {"insider": insider or "Unknown", "role": r.get("role"),
                                       "shares": 0.0, "value": 0.0})
                b["shares"] += shares
                b["value"] += value or 0.0
            elif code == _INSIDER_SELL:
                sell_count += 1
                sell_shares += shares
                sell_value += value or 0.0
                s = sellers.setdefault(insider or "Unknown",
                                       {"insider": insider or "Unknown", "role": r.get("role"),
                                        "shares": 0.0, "value": 0.0})
                s["shares"] += shares
                s["value"] += value or 0.0
            elif code in _INSIDER_OPTION:
                option_count += 1
            else:
                other_count += 1
        net_shares = buy_shares - sell_shares
        net_value = buy_value - sell_value
        if buy_count == 0 and sell_count == 0:
            sentiment = "no open-market activity"
        elif net_value > 0 or (net_value == 0 and net_shares > 0):
            sentiment = "net buying"
        elif net_value < 0 or (net_value == 0 and net_shares < 0):
            sentiment = "net selling"
        else:
            sentiment = "balanced"
        data = {
            "symbol": sym,
            "issuerName": issuer,
            "rows": out_rows[:60],
            "count": len(rows),
            "shown": min(len(rows), 60),
            "summary": {
                "buyCount": buy_count, "sellCount": sell_count,
                "optionExerciseCount": option_count, "otherCount": other_count,
                "buyShares": buy_shares, "sellShares": sell_shares,
                "buyValue": buy_value, "sellValue": sell_value,
                "netShares": net_shares, "netValue": net_value,
                "sentiment": sentiment, "uniqueInsiders": len(insiders),
            },
            "topBuyers": sorted(buyers.values(), key=lambda x: x["value"] or x["shares"], reverse=True)[:5],
            "topSellers": sorted(sellers.values(), key=lambda x: x["value"] or x["shares"], reverse=True)[:5],
        }
        warnings = None if rows else [warn("PARTIAL_COVERAGE", scope=sym, detail="no insider filings")]
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    # ============================== institutional.* ==============================
    def _inst_assemble(self, sym: str) -> tuple[dict, list[dict]]:
        """Aggregate 13F holdings into per-manager positions with QoQ deltas (the shared
        building block for institutional.holders + institutional.flows)."""
        holdings = self.archive.inst_holdings(ticker=sym)
        # Per-manager report periods (newest first) from inst_filings, joined by cik.
        ciks = sorted({h.get("cik") for h in holdings if h.get("cik")})
        filings_by_cik: dict[str, list[dict]] = defaultdict(list)
        all_filings: list[dict] = []
        for cik in ciks:
            fs = self.archive.inst_filings(cik=cik)
            fs = sorted(fs, key=lambda f: str(f.get("period") or ""), reverse=True)
            filings_by_cik[cik] = fs
            all_filings.extend(fs)

        # Aggregate SHARE positions (exclude option positions, put_call != "") by (cik, period).
        share_pos: dict = defaultdict(lambda: {"shares": 0.0, "value": 0.0, "url": None})
        issuer_name = cusip = None
        for h in holdings:
            if (h.get("put_call") or "").strip():
                continue
            key = (h.get("cik"), str(h.get("period") or ""))
            sp = share_pos[key]
            sp["shares"] += _f(h.get("shares")) or 0.0
            sp["value"] += _f(h.get("value")) or 0.0
            sp["url"] = h.get("url") or sp["url"]
            issuer_name = issuer_name or h.get("name")
            cusip = cusip or h.get("cusip")

        _eps = 1.0
        rows: list[dict] = []
        latest_periods: list[str] = []
        for cik in ciks:
            plist = filings_by_cik.get(cik) or []
            # fall back to periods seen in holdings when no filing rows exist
            if not plist:
                periods = sorted({str(h.get("period") or "") for h in holdings if h.get("cik") == cik},
                                 reverse=True)
                plist = [{"period": p} for p in periods if p]
            if not plist:
                continue
            latest_period = str(plist[0].get("period") or "")
            prior_period = str(plist[1].get("period")) if len(plist) > 1 else None
            institution = plist[0].get("institution") or cik
            total_value = _f(plist[0].get("total_value")) or 0.0
            latest = share_pos.get((cik, latest_period))
            prior = share_pos.get((cik, prior_period)) if prior_period else None
            lat_sh = latest["shares"] if latest else 0.0
            lat_val = latest["value"] if latest else 0.0
            pri_sh = prior["shares"] if prior else 0.0
            pri_val = prior["value"] if prior else 0.0
            if lat_sh <= 0 and pri_sh <= 0:
                continue
            has_prior = prior_period is not None
            if lat_sh > 0 and has_prior and pri_sh <= 0:
                change = "new"
            elif lat_sh <= 0 and pri_sh > 0:
                change = "exited"
            elif lat_sh > 0 and pri_sh > 0:
                d = lat_sh - pri_sh
                change = "added" if d > _eps else ("trimmed" if d < -_eps else "unchanged")
            else:
                change = "unchanged"
            rows.append({
                "institution": institution, "cik": cik, "shares": lat_sh, "value": lat_val,
                "pctOfPortfolio": (lat_val / total_value) if total_value > 0 else None,
                "period": latest_period,
                "priorShares": pri_sh if has_prior else None,
                "priorValue": pri_val if has_prior else None,
                "deltaShares": (lat_sh - pri_sh) if has_prior else None,
                "deltaValue": (lat_val - pri_val) if has_prior else None,
                "changePct": ((lat_sh - pri_sh) / pri_sh * 100.0) if (has_prior and pri_sh > 0) else None,
                "change": change, "hasPrior": has_prior,
                "url": (latest or prior or {}).get("url") or plist[0].get("url"),
            })
            if lat_sh > 0:
                latest_periods.append(latest_period)
        report_period = max(latest_periods) if latest_periods else None
        assembled = {
            "symbol": sym, "name": issuer_name, "cusip": cusip,
            "reportPeriod": report_period,
            "rows": rows,
            "holders": [r for r in rows if r["shares"] > 0],
            "managersWithData": len(ciks),
        }
        # freshness across holdings + filings rows used
        return assembled, holdings + all_filings

    def institutional_holdings(self, params: dict) -> dict:
        """Top institutional holders of one ticker from 13F filings (build_institutional_holders),
        with QoQ change classification (new/added/trimmed/exited)."""
        if not self.available:
            return self._unavailable()
        sym = _inst_symbol(params)
        a, used = self._inst_assemble(sym)
        holders = sorted(a["holders"], key=lambda r: (r["value"] or 0.0, r["shares"] or 0.0), reverse=True)
        counts = {"new": 0, "added": 0, "trimmed": 0, "exited": 0, "unchanged": 0}
        total_value = total_shares = net_delta_shares = net_delta_value = 0.0
        for r in holders:
            counts[r["change"]] = counts.get(r["change"], 0) + 1
            total_value += r["value"] or 0.0
            total_shares += r["shares"] or 0.0
            if r["deltaShares"] is not None:
                net_delta_shares += r["deltaShares"]
            if r["deltaValue"] is not None:
                net_delta_value += r["deltaValue"]
        data = {
            "title": f"Institutional Holders — {a['name'] or sym}",
            "symbol": sym, "name": a["name"], "cusip": a["cusip"],
            "reportPeriod": a["reportPeriod"],
            "holders": holders[:50],
            "summary": {
                "totalValue": total_value, "totalShares": total_shares,
                "holderCount": len(holders),
                "newCount": counts["new"], "addedCount": counts["added"],
                "trimmedCount": counts["trimmed"], "exitedCount": counts["exited"],
                "unchangedCount": counts["unchanged"],
                "netDeltaShares": net_delta_shares, "netDeltaValue": net_delta_value,
            },
            "coverage": {"managersWithData": a["managersWithData"], "managersHolding": len(holders)},
        }
        warnings = None if holders else [warn("PARTIAL_COVERAGE", scope=sym, detail="no 13F holders")]
        return envelope(data, freshness=freshness_of(used), warnings=warnings)

    def institutional_flows(self, params: dict) -> dict:
        """QoQ institutional fund flows in one ticker (build_institutional_flows): biggest
        buyers (new+added) and sellers (trimmed+exited) ranked by estimated dollars traded."""
        if not self.available:
            return self._unavailable()
        sym = _inst_symbol(params)
        a, used = self._inst_assemble(sym)

        def _flow_row(r: dict) -> dict:
            lat_sh, lat_val = r.get("shares") or 0.0, r.get("value") or 0.0
            pri_sh, pri_val = r.get("priorShares") or 0.0, r.get("priorValue") or 0.0
            price = (lat_val / lat_sh) if lat_sh > 0 else ((pri_val / pri_sh) if pri_sh > 0 else 0.0)
            dsh = r.get("deltaShares") or 0.0
            return {
                "institution": r["institution"], "cik": r["cik"], "change": r["change"],
                "shares": lat_sh, "value": lat_val, "deltaShares": dsh,
                "deltaValue": r.get("deltaValue") or 0.0, "tradeValue": dsh * price,
                "period": r["period"], "url": r["url"],
            }

        comparable = [_flow_row(r) for r in a["rows"]
                      if r.get("hasPrior") and r.get("deltaShares") is not None]
        buyers = sorted([r for r in comparable if r["change"] in ("new", "added")],
                        key=lambda r: r["tradeValue"], reverse=True)
        sellers = sorted([r for r in comparable if r["change"] in ("trimmed", "exited")],
                         key=lambda r: r["tradeValue"])
        total_bought = sum(r["tradeValue"] for r in buyers)
        total_sold = sum(-r["tradeValue"] for r in sellers)
        data = {
            "title": f"Institutional Flows — {a['name'] or sym}",
            "symbol": sym, "name": a["name"], "cusip": a["cusip"],
            "reportPeriod": a["reportPeriod"],
            "buyers": buyers[:15], "sellers": sellers[:15],
            "summary": {
                "buyerCount": len(buyers), "sellerCount": len(sellers),
                "newCount": sum(1 for r in buyers if r["change"] == "new"),
                "exitedCount": sum(1 for r in sellers if r["change"] == "exited"),
                "totalBought": total_bought, "totalSold": total_sold,
                "netValue": total_bought - total_sold,
            },
            "coverage": {"managersWithData": a["managersWithData"], "comparableManagers": len(comparable)},
        }
        warnings = None if comparable else [
            warn("PARTIAL_COVERAGE", scope=sym, detail="no comparable prior-quarter filings")]
        return envelope(data, freshness=freshness_of(used), warnings=warnings)

    # ============================== etf.* ==============================
    def etf_holdings(self, params: dict) -> dict:
        """Ranked constituents of an ETF (build_etf_holdings) with top-N concentration."""
        if not self.available:
            return self._unavailable()
        etf = (params.get("etf") or params.get("symbol") or params.get("ticker") or "").upper().strip()
        if not etf:
            raise ValueError("etf.holdings needs an 'etf' ticker.")
        rows = self.archive.etf_holdings(etf)
        rows = sorted(rows, key=lambda h: (_f(h.get("weight")) or 0.0), reverse=True)
        out = [{"rank": i + 1, "symbol": (h.get("symbol") or "").upper(),
                "name": h.get("name") or h.get("symbol"),
                "weight": round(_f(h.get("weight")) or 0.0, 4)}
               for i, h in enumerate(rows)]
        weights = [r["weight"] for r in out]
        data = {
            "title": f"{etf} · Holdings",
            "etf": etf,
            "rows": out,
            "holdingsCount": len(out),
            "coverage": round(sum(weights), 4),
            "top5": round(sum(weights[:5]), 4),
            "top10": round(sum(weights[:10]), 4),
        }
        warnings = None if out else [warn("PARTIAL_COVERAGE", scope=etf, detail="no holdings on file")]
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    def etf_exposure(self, params: dict) -> dict:
        """Reverse lookup: which ETFs hold a stock, and at what weight (build_etf_exposure)."""
        if not self.available:
            return self._unavailable()
        sym = (params.get("symbol") or params.get("ticker") or "").upper().strip().lstrip("$")
        if not sym:
            raise ValueError("etf.exposure needs a 'symbol'.")
        rows = self.archive.etf_exposure(sym)
        out = sorted([{"etf": (r.get("etf") or "").upper(),
                       "name": r.get("name"),
                       "weight": round(_f(r.get("weight")) or 0.0, 4),
                       "asOf": r.get("as_of")}
                      for r in rows], key=lambda r: r["weight"], reverse=True)
        data = {
            "title": f"{sym} · ETF Exposure",
            "symbol": sym,
            "rows": out,
            "etfCount": len(out),
            "totalWeight": round(sum(r["weight"] for r in out), 4),
        }
        warnings = None if out else [warn("PARTIAL_COVERAGE", scope=sym, detail="not in any tracked ETF")]
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    # ============================== sentiment.* ==============================
    def sentiment_get(self, params: dict) -> dict:
        """Persisted sentiment snapshot for a symbol/sector (build_sentiment), real rows only."""
        if not self.available:
            return self._unavailable()
        scope = (params.get("scope") or params.get("symbol") or params.get("sector") or "").strip()
        if params.get("scope_type"):
            scope_type = params["scope_type"]
        elif params.get("symbol"):
            scope_type = "symbol"
        elif params.get("sector"):
            scope_type = "sector"
        else:
            scope_type = "topic"
        if not scope:
            raise ValueError("sentiment.get needs a 'scope' (symbol/sector/topic).")
        row = self.archive.sentiment(scope_type, scope)
        if not row:
            return envelope(
                {"scope": scope, "scopeType": scope_type, "overall": None},
                freshness=None,
                warnings=[warn("PARTIAL_COVERAGE", scope=scope, detail="no sentiment snapshot")],
            )
        data = {
            "scope": scope,
            "scopeType": scope_type,
            "overall": _f(row.get("overall")),
            "label": row.get("label"),
            "sources": row.get("sources") or [],
            "trend": row.get("trend") or [],
        }
        return envelope(data, freshness=freshness_of([row]))

    # ============================== macro.* ==============================
    def macro_dashboard(self, params: dict) -> dict:
        """Macro tiles grouped by asset class (build_macro_dashboard) from macro_prices/quotes,
        plus a rule-based market-regime read."""
        if not self.available:
            return self._unavailable()
        macro = self.archive.macro() or {}
        prices = macro.get("prices") or []
        quotes = {(_q.get("symbol") or "").upper(): _q for _q in (macro.get("quotes") or [])}
        tiles = []
        for p in prices:
            sym = (p.get("symbol") or "").upper()
            q = quotes.get(sym) or {}
            tiles.append({
                "symbol": sym,
                "name": p.get("name") or sym,
                "price": _f(p.get("price")) if p.get("price") is not None else _f(q.get("price")),
                "changePct": _f(p.get("change_pct")) if p.get("change_pct") is not None else _f(q.get("change_pct")),
                "sparkline": q.get("sparkline"),
            })
        data = {
            "title": "Macro Dashboard",
            "tiles": tiles,
            "count": len(tiles),
            "regime": _macro_regime(tiles),
        }
        return envelope(data, freshness=freshness_of(prices + (macro.get("quotes") or [])))

    # ============================== universe.* ==============================
    def universe_list(self, params: dict) -> dict:
        """Investable-universe overview (build_data_universe): symbols, sectors, coverage."""
        if not self.available:
            return self._unavailable()
        sector = (params.get("sector") or params.get("scope") or "").strip() or None
        limit = _i(params.get("limit"), 150, 10, 400)
        tracked_only = params.get("tracked_only", True)
        uni = self.archive.universe(tracked_only=bool(tracked_only))
        if sector:
            sl = sector.lower()
            uni = [u for u in uni if (u.get("sector") or "").lower() == sl]
        sectors_meta = {(s.get("id") or "").lower(): s.get("name") for s in self.archive.sectors()}
        rows = []
        by_sector: dict[str, int] = defaultdict(int)
        delisted = 0
        for u in uni:
            sym = (u.get("symbol") or "").upper()
            sec = u.get("sector")
            status = u.get("status")
            if status and status.lower() in ("delisted", "inactive"):
                delisted += 1
            if sec:
                by_sector[sec] += 1
            rows.append({
                "symbol": sym,
                "name": u.get("name") or sym,
                "sector": sectors_meta.get((sec or "").lower(), sec),
                "industry": u.get("industry"),
                "country": u.get("country"),
                "exchange": u.get("exchange"),
                "status": status,
                "tracked": bool(u.get("tracked")),
            })
        rows = rows[:limit]
        sectors = sorted(
            [{"id": k, "name": sectors_meta.get(k.lower(), k), "count": v} for k, v in by_sector.items()],
            key=lambda s: s["count"], reverse=True,
        )
        data = {
            "title": f"Data Universe — {sector}" if sector else "Data Universe — Coverage",
            "summary": {
                "totalSymbols": len(uni),
                "shown": len(rows),
                "trackedCount": sum(1 for u in uni if u.get("tracked")),
                "delistedCount": delisted,
                "sectorCount": len(sectors),
            },
            "sectors": sectors,
            "rows": rows,
        }
        return envelope(data, freshness=freshness_of(uni))


    # ============================== delegation: extended_skills ==============================
    def seasonality_monthly(self, params): return self._ext.seasonality_monthly(params)
    def seasonality_heatmap(self, params): return self._ext.seasonality_heatmap(params)
    def vol_iv_rank(self, params): return self._ext.vol_iv_rank(params)
    def vol_vrp(self, params): return self._ext.vol_vrp(params)
    def vol_anomaly_score(self, params): return self._ext.vol_anomaly_score(params)
    def vol_character(self, params): return self._ext.vol_character(params)
    def technical_indicators(self, params): return self._ext.technical_indicators(params)
    def dividends(self, params): return self._ext.dividends(params)

    # ============================== delegation: short_skills ==============================
    def short_interest(self, params): return self._short.short_interest(params)
    def short_volume(self, params): return self._short.short_volume(params)
    def failures_to_deliver(self, params): return self._short.failures_to_deliver(params)
    def short_screener(self, params): return self._short.short_screener(params)

    # ============================== delegation: macro_extended ==============================
    def economic_calendar(self, params): return self._macro.economic_calendar(params)
    def fda_calendar(self, params): return self._macro.fda_calendar(params)
    def commodity_prices(self, params): return self._macro.commodity_prices(params)
    def forex_rates(self, params): return self._macro.forex_rates(params)
    def crypto_prices(self, params): return self._macro.crypto_prices(params)
    def vix_term_structure(self, params): return self._macro.vix_term_structure(params)
    def market_tide(self, params): return self._macro.market_tide(params)

    # ============================== delegation: financials_skills ==============================
    def financials_income(self, params): return self._fin.financials_income(params)
    def financials_balance(self, params): return self._fin.financials_balance(params)
    def financials_cashflow(self, params): return self._fin.financials_cashflow(params)
    def earnings_transcript(self, params): return self._fin.earnings_transcript(params)
    def earnings_calendar(self, params): return self._fin.earnings_calendar(params)
    def stock_splits(self, params): return self._fin.stock_splits(params)

    # ============================== delegation: congress_extended_skills ==============================
    def politician_portfolio(self, params): return self._cong_ext.politician_portfolio(params)
    def congress_late_filings(self, params): return self._cong_ext.congress_late_filings(params)
    def congress_screener(self, params): return self._cong_ext.congress_screener(params)


# ----------------------------- module-level helpers -----------------------------
def _inst_symbol(params: dict) -> str:
    symbol = params.get("symbol") or (params.get("symbols") or [None])[0]
    if not symbol:
        raise ValueError("institutional ownership needs a 'symbol'.")
    return str(symbol).upper().strip()


def _lag_days(txn_date: str | None, disc_date: str | None) -> int | None:
    if not txn_date or not disc_date:
        return None
    try:
        t = date.fromisoformat(str(txn_date)[:10])
        d = date.fromisoformat(str(disc_date)[:10])
        return (d - t).days
    except (TypeError, ValueError):
        return None


def _congress_highlights(trades: list[dict]) -> list[dict]:
    """Clustered buying (several members, one name) + individually large buys/sells."""
    clusters: list = []
    by_ticker: dict = defaultdict(set)
    for t in trades:
        if t.get("type") == "buy" and t.get("ticker"):
            by_ticker[t["ticker"]].add(t.get("member"))
    for tk, members in by_ticker.items():
        members = {m for m in members if m}
        if len(members) >= _CONGRESS_CLUSTER_MIN:
            clusters.append({
                "kind": "cluster_buy", "label": f"Cluster buy · {tk}",
                "detail": f"{len(members)} members bought {tk} in this window",
                "ticker": tk, "members": sorted(members),
            })
    clusters.sort(key=lambda h: len(h["members"]), reverse=True)
    larges: list = []
    for t in trades:
        hi = t.get("amountHigh")
        if hi and hi >= _CONGRESS_LARGE_THRESHOLD and t.get("type") in ("buy", "sell"):
            larges.append((hi, {
                "kind": "large_buy" if t["type"] == "buy" else "large_sale",
                "label": f"Large {t['type']} · {t.get('member')}"
                         + (f" · {t['ticker']}" if t.get("ticker") else ""),
                "detail": f"{t.get('amountRange') or 'amount n/a'} "
                          f"({t.get('chamber') or '—'}, {t.get('party') or '—'})",
                "ticker": t.get("ticker"),
                "members": [t.get("member")] if t.get("member") else [],
            }))
    larges.sort(key=lambda p: p[0], reverse=True)
    return (clusters + [h for _, h in larges])[:8]


def _macro_regime(tiles: list[dict]) -> dict | None:
    """Rule-based regime read from the 1D tile moves (no LLM). Ported from build_macro_dashboard.

    Symbols are matched by common aliases so it works on whatever macro symbols the archive holds.
    """
    by_symbol = {(t.get("symbol") or "").upper(): _f(t.get("changePct")) for t in tiles}

    def pick(*names: str) -> float | None:
        for n in names:
            if n in by_symbol and by_symbol[n] is not None:
                return by_symbol[n]
        return None

    equity_syms = ("SPX", "SPY", "ES", "NDX", "QQQ", "DJI", "RUT")
    equity_moves = [by_symbol[s] for s in equity_syms if by_symbol.get(s) is not None]
    if not equity_moves:
        return None
    eq = sum(equity_moves) / len(equity_moves)
    gold = pick("GOLD", "XAU", "GC")
    oil = pick("WTI", "CL", "OIL", "BRENT")
    vix = pick("VIX")
    y10 = pick("US10Y", "TNX", "UST10Y")

    EQ_T, G_T, OIL_T, Y_T = 0.10, 0.10, 0.30, 0.05
    up, dn = eq > EQ_T, eq < -EQ_T
    parts: list[str] = []
    eq_phrase = "equities bid" if up else ("equities sold" if dn else "equities flat")
    if up:
        if ((y10 is not None and y10 < -Y_T) or (oil is not None and oil < OIL_T)) and \
           (gold is not None and gold < G_T) and not (oil is not None and oil > OIL_T):
            label, headline = "soft_landing", "Soft Landing"
        elif vix is not None and vix > 0 and (gold is not None and gold > G_T):
            label, headline = "risk_off", "Risk-Off Rally"
        else:
            label, headline = "risk_on", "Risk-On"
        parts.append(eq_phrase)
        if gold is not None:
            parts.append("gold bid" if gold > G_T else "gold soft")
    elif dn:
        if (gold is not None and gold > G_T) and (oil is not None and oil > OIL_T):
            label, headline = "stagflation", "Stagflation Watch"
        else:
            label, headline = "risk_off", "Risk-Off"
        parts.append(eq_phrase)
        if vix is not None and vix > 0:
            parts.append("vol bid")
    else:
        label, headline = "neutral", "Neutral / Mixed"
        parts.append(eq_phrase)
    return {"label": label, "headline": headline, "summary": ", ".join(parts),
            "equityMove": round(eq, 2)}


# tool name -> SkillSet method. Kept SEPARATE from api.TOOLS (the core data tools) to avoid
# any conflict. The MCP gateway advertises one @mcp.tool per entry; the REST gateway can share.
SKILLS: dict[str, str] = {
    "market.news": "market_news",
    "market.screener": "market_screener",
    "market.movers": "market_movers",
    "fundamentals.get": "fundamentals_get",
    "fundamentals.compare": "fundamentals_compare",
    "fundamentals.pit": "fundamentals_pit",
    "analyst.ratings": "analyst_ratings",
    "congress.trades": "congress_trades",
    "insider.activity": "insider_activity",
    "institutional.holdings": "institutional_holdings",
    "institutional.flows": "institutional_flows",
    "etf.holdings": "etf_holdings",
    "etf.exposure": "etf_exposure",
    "sentiment.get": "sentiment_get",
    "macro.dashboard": "macro_dashboard",
    "universe.list": "universe_list",
    # ---- COMPUTED skills (source="computed"): pure math on agent inputs or real archive series ----
    "options.greeks": "options_greeks",
    "options.implied_vol": "options_implied_vol",
    "vol.realized": "vol_realized",
    "vol.term_structure": "vol_term_structure",
    "correlation.matrix": "correlation_matrix",
    "factor.exposures": "factor_exposures",
    "dcf.value": "dcf_value",
    "portfolio.optimize": "portfolio_optimize",
    "montecarlo.simulate": "montecarlo_simulate",
    "scenario.project": "scenario_project",
    "risk.stress": "risk_stress",
    "tearsheet": "tearsheet",
    "walkforward.run": "walkforward_run",
    # ---- extended_skills ----
    "seasonality.monthly": "seasonality_monthly",
    "seasonality.heatmap": "seasonality_heatmap",
    "vol.iv_rank": "vol_iv_rank",
    "vol.vrp": "vol_vrp",
    "vol.anomaly_score": "vol_anomaly_score",
    "vol.character": "vol_character",
    "technical.indicators": "technical_indicators",
    "dividends": "dividends",
    # ---- short_skills ----
    "short.interest": "short_interest",
    "short.volume": "short_volume",
    "short.ftd": "failures_to_deliver",
    "short.screener": "short_screener",
    # ---- macro_extended ----
    "economic.calendar": "economic_calendar",
    "fda.calendar": "fda_calendar",
    "commodity.prices": "commodity_prices",
    "forex.rates": "forex_rates",
    "crypto.prices": "crypto_prices",
    "vix.term_structure": "vix_term_structure",
    "market.tide": "market_tide",
    # ---- financials_skills ----
    "financials.income": "financials_income",
    "financials.balance": "financials_balance",
    "financials.cashflow": "financials_cashflow",
    "earnings.transcript": "earnings_transcript",
    "earnings.calendar": "earnings_calendar",
    "stock.splits": "stock_splits",
    # ---- congress_extended_skills ----
    "politician.portfolio": "politician_portfolio",
    "congress.late_filings": "congress_late_filings",
    "congress.screener": "congress_screener",
}
