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

from collections import defaultdict
from datetime import date
from typing import Any

from .archive import ArchiveGateway
from .envelope import (
    ARCHIVE_UNAVAILABLE,
    consensus_label,
    envelope,
    fmt_usd,
    freshness_of,
    warn,
)

__all__ = ["SkillSet", "SKILLS"]

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


class SkillSet:
    """Declarative, archive-backed skills. ``archive`` is duck-typed to ``ArchiveGateway``."""

    def __init__(self, archive: ArchiveGateway | None):
        self.archive = archive

    # ----------------------------- gate -----------------------------
    def _unavailable(self) -> dict:
        return envelope(None, freshness=None, pit=False, warnings=[dict(ARCHIVE_UNAVAILABLE)])

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
    dxy = pick("DXY", "USD")
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
}
