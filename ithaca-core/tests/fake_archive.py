"""An in-memory ArchiveGateway with tiny fixtures, for the skill-catalog tests.

Implements the ``ithaca_core.skills.ArchiveGateway`` protocol structurally (no inheritance) so
the same object Stream 1 will ship in Postgres is exercised here against fixtures. Rows use the
canonical ``archive.*`` column names from the data-layer contract.
"""
from __future__ import annotations

import numpy as np


def _ohlcv(symbol: str, closes: list[float], start_day: int = 1) -> list[dict]:
    rows = []
    for i, c in enumerate(closes):
        d = f"2024-01-{start_day + i:02d}"
        rows.append({"symbol": symbol, "d": d, "o": c, "h": c, "l": c, "c": c, "v": 1_000_000.0,
                     "updated_at": "2024-06-01T00:00:00Z"})
    return rows


def _long_series(symbol: str, n: int = 300, start: float = 100.0, drift: float = 0.0004,
                 amp: float = 0.02, seed: int = 7) -> list[dict]:
    """A deterministic ~n-day close series (sinusoid + drift) with real day-over-day moves.

    Long enough to exercise the COMPUTED skills that need history (realized vol over 252-day
    windows, GBM monte-carlo's >=5 returns, backtests / walk-forward folds). Fully deterministic
    — no RNG — so numeric assertions are stable across runs.
    """
    import datetime as _dt

    base = _dt.date(2022, 1, 3)
    rows = []
    price = start
    for i in range(n):
        # smooth, mean-reverting wiggle + slight upward drift; strictly positive closes
        step = drift + amp * np.sin(i / 9.0 + seed) * 0.5
        price = max(1.0, price * (1.0 + step))
        d = (base + _dt.timedelta(days=i)).isoformat()
        rows.append({"symbol": symbol, "d": d, "o": price, "h": price * 1.01, "l": price * 0.99,
                     "c": round(price, 4), "v": 2_000_000.0, "updated_at": "2024-06-01T00:00:00Z"})
    return rows


class FakeArchive:
    """Tiny deterministic fixtures covering every skill the catalog exposes."""

    def __init__(self) -> None:
        self._ohlcv = {
            "NVDA": _ohlcv("NVDA", [100.0, 110.0, 120.0, 150.0]),
            "AMD": _ohlcv("AMD", [80.0, 82.0, 78.0, 90.0]),
            "TSM": _ohlcv("TSM", [60.0, 61.0, 62.0, 66.0]),
            # Long deterministic series for the COMPUTED skills that need real history.
            "LONG": _long_series("LONG", n=300, seed=3),
            "LONG2": _long_series("LONG2", n=300, seed=11, start=50.0, amp=0.03),
        }
        self._universe = [
            {"symbol": "NVDA", "name": "NVIDIA Corp", "sector": "semiconductors", "tracked": True,
             "pending": False, "country": "US", "exchange": "NASDAQ", "industry": "Semiconductors",
             "status": "active", "updated_at": "2024-06-01T00:00:00Z"},
            {"symbol": "AMD", "name": "Advanced Micro Devices", "sector": "semiconductors",
             "tracked": True, "pending": False, "country": "US", "exchange": "NASDAQ",
             "industry": "Semiconductors", "status": "active", "updated_at": "2024-06-01T00:00:00Z"},
            {"symbol": "TSM", "name": "Taiwan Semiconductor", "sector": "semiconductors",
             "tracked": True, "pending": False, "country": "TW", "exchange": "NYSE",
             "industry": "Semiconductors", "status": "active", "updated_at": "2024-06-01T00:00:00Z"},
            {"symbol": "OLD", "name": "Delisted Co", "sector": "industrials", "tracked": False,
             "pending": False, "country": "US", "exchange": "NYSE", "industry": "Misc",
             "status": "delisted", "updated_at": "2020-06-01T00:00:00Z"},
        ]
        # LONG / LONG2 carry long ohlcv + fundamentals fixtures for the COMPUTED skills but are
        # intentionally kept OUT of the universe so the universe.list counts stay unchanged.
        self._sectors = [
            {"id": "semiconductors", "name": "Semiconductors", "updated_at": "2024-06-01T00:00:00Z"},
            {"id": "industrials", "name": "Industrials", "updated_at": "2024-06-01T00:00:00Z"},
        ]
        self._fundamentals = {
            "NVDA": {"symbol": "NVDA", "name": "NVIDIA Corp", "price": 150.0, "change_pct": 2.5,
                     "market_cap": 3.5e12, "pe_ratio": 65.0, "volume": 5e7, "revenue": 6e10,
                     "net_margin": 48.0, "eps": 2.5, "dividend_yield": 0.03, "beta": 1.7,
                     "week52_high": 160.0, "week52_low": 40.0, "description": "GPUs.",
                     "is_live": True, "revenue_growth": 0.9, "earnings_date": "2024-05-22",
                     "updated_at": "2024-06-01T00:00:00Z"},
            "AMD": {"symbol": "AMD", "name": "Advanced Micro Devices", "price": 90.0,
                    "change_pct": -1.2, "market_cap": 1.5e11, "pe_ratio": 40.0, "volume": 3e7,
                    "revenue": 2.3e10, "net_margin": 12.0, "eps": 1.1, "dividend_yield": 0.0,
                    "beta": 1.9, "week52_high": 120.0, "week52_low": 70.0, "description": "CPUs.",
                    "is_live": True, "revenue_growth": 0.1, "earnings_date": "2024-04-30",
                    "updated_at": "2024-06-02T00:00:00Z"},
            "TSM": {"symbol": "TSM", "name": "Taiwan Semiconductor", "price": 66.0,
                    "change_pct": 0.4, "market_cap": 6e11, "pe_ratio": 25.0, "volume": 1e7,
                    "revenue": 7e10, "net_margin": 38.0, "eps": 5.2, "dividend_yield": 1.8,
                    "beta": 1.1, "week52_high": 70.0, "week52_low": 50.0, "description": "Fab.",
                    "is_live": True, "revenue_growth": 0.2, "earnings_date": "2024-04-18",
                    "net_debt": -5e9, "updated_at": "2024-06-01T00:00:00Z"},
            "LONG": {"symbol": "LONG", "name": "Long Co", "price": 120.0, "change_pct": 0.3,
                     "market_cap": 1.2e11, "pe_ratio": 30.0, "volume": 2e6, "revenue": 4e10,
                     "net_margin": 20.0, "eps": 4.0, "dividend_yield": 0.5, "beta": 1.2,
                     "week52_high": 130.0, "week52_low": 90.0, "description": "Long series.",
                     "is_live": True, "revenue_growth": 0.12, "earnings_date": "2024-05-01",
                     "net_debt": 1e10, "updated_at": "2024-06-01T00:00:00Z"},
            "LONG2": {"symbol": "LONG2", "name": "Long Two Co", "price": 60.0, "change_pct": -0.2,
                      "market_cap": 3e10, "pe_ratio": 18.0, "volume": 1e6, "revenue": 1.5e10,
                      "net_margin": 14.0, "eps": 3.3, "dividend_yield": 1.2, "beta": 0.9,
                      "week52_high": 70.0, "week52_low": 45.0, "description": "Long series two.",
                      "is_live": True, "revenue_growth": 0.06, "earnings_date": "2024-05-02",
                      "net_debt": 2e9, "updated_at": "2024-06-01T00:00:00Z"},
        }
        self._pit = {
            "NVDA": [
                {"symbol": "NVDA", "period_end": "2023-10-31", "report_date": "2023-11-21",
                 "revenue": 1.81e10, "net_income": 9.24e9, "net_margin": 51.0, "eps": 4.02,
                 "report_estimated": False, "source": "edgar", "updated_at": "2023-11-21T00:00:00Z"},
                {"symbol": "NVDA", "period_end": "2024-01-31", "report_date": "2024-02-21",
                 "revenue": 2.21e10, "net_income": 1.23e10, "net_margin": 55.6, "eps": 5.16,
                 "report_estimated": False, "source": "edgar", "updated_at": "2024-02-21T00:00:00Z"},
            ],
        }
        self._analyst = {
            "NVDA": {"symbol": "NVDA", "name": "NVIDIA Corp", "covered": True,
                     "consensus_key": "strong_buy", "recommendation_mean": 1.3, "num_analysts": 45,
                     "strong_buy": 30, "buy": 12, "hold": 3, "sell": 0, "strong_sell": 0,
                     "target_mean": 180.0, "target_high": 220.0, "target_low": 140.0,
                     "target_median": 175.0, "current_price": 150.0,
                     "changes": [{"firm": "Morgan Stanley", "action": "upgrade", "date": "2024-05-01"}],
                     "source": "yahoo", "updated_at": "2024-06-01T00:00:00Z"},
        }
        self._news = [
            {"id": "n1", "headline": "NVDA beats earnings", "source": "Reuters", "summary": "Big beat.",
             "url": "http://x/1", "published_at": "2024-05-23T12:00:00Z", "sentiment": "positive",
             "tickers": ["NVDA"], "sector": "semiconductors", "fetched_at": "2024-05-23T13:00:00Z"},
            {"id": "n2", "headline": "Chip demand cools", "source": "Bloomberg", "summary": "Soft.",
             "url": "http://x/2", "published_at": "2024-05-20T09:00:00Z", "sentiment": "negative",
             "tickers": ["AMD"], "sector": "semiconductors", "fetched_at": "2024-05-20T10:00:00Z"},
        ]
        self._sentiment = {
            ("symbol", "NVDA"): {"scope_type": "symbol", "scope": "NVDA", "overall": 0.42,
                                 "label": "bullish",
                                 "sources": [{"channel": "Reddit", "score": 0.4, "volume": 1200}],
                                 "trend": [{"t": "2024-05-20", "score": 0.4}],
                                 "updated_at": "2024-06-01T00:00:00Z"},
        }
        self._congress = [
            {"id": "c1", "member": "Rep A", "chamber": "House", "party": "R", "party_code": "R",
             "ticker": "NVDA", "txn_type": "buy", "raw_type": "Purchase",
             "amount_range": "$250,001 - $500,000", "amount_low": 250001.0, "amount_high": 500000.0,
             "transaction_date": "2024-04-01", "disclosure_date": "2024-05-01",
             "source_url": "http://h/1", "fetched_at": "2024-05-02T00:00:00Z"},
            {"id": "c2", "member": "Rep B", "chamber": "House", "party": "D", "party_code": "D",
             "ticker": "NVDA", "txn_type": "buy", "raw_type": "Purchase",
             "amount_range": "$1,001 - $15,000", "amount_low": 1001.0, "amount_high": 15000.0,
             "transaction_date": "2024-04-05", "disclosure_date": "2024-05-10",
             "source_url": "http://h/2", "fetched_at": "2024-05-11T00:00:00Z"},
        ]
        self._insider = {
            "NVDA": [
                {"accession_no": "a1", "txn_seq": 0, "symbol": "NVDA", "cik": "0001045810",
                 "issuer_name": "NVIDIA Corp", "insider_name": "Jensen Huang", "role": "CEO",
                 "transaction_code": "S", "transaction_type": "Sale", "acquired_disposed": "D",
                 "security_title": "Common", "is_derivative": False, "shares": 100000.0,
                 "price": 150.0, "value": 1.5e7, "shares_owned_after": 9e8,
                 "transaction_date": "2024-05-15", "filing_date": "2024-05-17", "form": "4",
                 "url": "http://e/1", "source": "edgar", "updated_at": "2024-05-17T00:00:00Z"},
                {"accession_no": "a2", "txn_seq": 0, "symbol": "NVDA", "cik": "0001045810",
                 "issuer_name": "NVIDIA Corp", "insider_name": "Director X", "role": "Director",
                 "transaction_code": "P", "transaction_type": "Purchase", "acquired_disposed": "A",
                 "security_title": "Common", "is_derivative": False, "shares": 5000.0,
                 "price": 148.0, "value": 740000.0, "shares_owned_after": 20000.0,
                 "transaction_date": "2024-05-10", "filing_date": "2024-05-12", "form": "4",
                 "url": "http://e/2", "source": "edgar", "updated_at": "2024-05-12T00:00:00Z"},
            ],
        }
        # Two managers, two periods → one "added", one "new" classification.
        self._inst_holdings = [
            {"cik": "C1", "period": "2024-03-31", "cusip": "67066G104", "put_call": "",
             "institution": "Vanguard", "ticker": "NVDA", "name": "NVIDIA Corp",
             "shares": 200000.0, "value": 3.0e7, "url": "http://13f/1", "accession_no": "f1",
             "source": "edgar", "updated_at": "2024-05-15T00:00:00Z"},
            {"cik": "C1", "period": "2023-12-31", "cusip": "67066G104", "put_call": "",
             "institution": "Vanguard", "ticker": "NVDA", "name": "NVIDIA Corp",
             "shares": 150000.0, "value": 2.0e7, "url": "http://13f/0", "accession_no": "f0",
             "source": "edgar", "updated_at": "2024-02-15T00:00:00Z"},
            {"cik": "C2", "period": "2024-03-31", "cusip": "67066G104", "put_call": "",
             "institution": "BlackRock", "ticker": "NVDA", "name": "NVIDIA Corp",
             "shares": 90000.0, "value": 1.35e7, "url": "http://13f/2", "accession_no": "f2",
             "source": "edgar", "updated_at": "2024-05-15T00:00:00Z"},
            # C3 (Citadel) filed both quarters but only HOLDS NVDA now → a true "new" position.
            {"cik": "C3", "period": "2024-03-31", "cusip": "67066G104", "put_call": "",
             "institution": "Citadel", "ticker": "NVDA", "name": "NVIDIA Corp",
             "shares": 30000.0, "value": 4.5e6, "url": "http://13f/3", "accession_no": "f3",
             "source": "edgar", "updated_at": "2024-05-15T00:00:00Z"},
        ]
        self._inst_filings = {
            "C1": [
                {"cik": "C1", "period": "2024-03-31", "institution": "Vanguard", "accession_no": "f1",
                 "form": "13F-HR", "filing_date": "2024-05-15", "url": "http://13f/1",
                 "total_value": 5.0e11, "positions": 4000, "source": "edgar",
                 "updated_at": "2024-05-15T00:00:00Z"},
                {"cik": "C1", "period": "2023-12-31", "institution": "Vanguard", "accession_no": "f0",
                 "form": "13F-HR", "filing_date": "2024-02-15", "url": "http://13f/0",
                 "total_value": 4.8e11, "positions": 3900, "source": "edgar",
                 "updated_at": "2024-02-15T00:00:00Z"},
            ],
            "C2": [
                {"cik": "C2", "period": "2024-03-31", "institution": "BlackRock", "accession_no": "f2",
                 "form": "13F-HR", "filing_date": "2024-05-15", "url": "http://13f/2",
                 "total_value": 6.0e11, "positions": 5000, "source": "edgar",
                 "updated_at": "2024-05-15T00:00:00Z"},
            ],
            "C3": [
                {"cik": "C3", "period": "2024-03-31", "institution": "Citadel", "accession_no": "f3",
                 "form": "13F-HR", "filing_date": "2024-05-15", "url": "http://13f/3",
                 "total_value": 2.0e11, "positions": 8000, "source": "edgar",
                 "updated_at": "2024-05-15T00:00:00Z"},
                {"cik": "C3", "period": "2023-12-31", "institution": "Citadel", "accession_no": "f3b",
                 "form": "13F-HR", "filing_date": "2024-02-15", "url": "http://13f/3b",
                 "total_value": 1.9e11, "positions": 7800, "source": "edgar",
                 "updated_at": "2024-02-15T00:00:00Z"},
            ],
        }
        self._etf_holdings = {
            "SOXX": [
                {"etf": "SOXX", "symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.10,
                 "as_of": "2024-05-31", "source": "issuer", "updated_at": "2024-06-01T00:00:00Z"},
                {"etf": "SOXX", "symbol": "AMD", "name": "AMD", "weight": 0.07,
                 "as_of": "2024-05-31", "source": "issuer", "updated_at": "2024-06-01T00:00:00Z"},
            ],
            "QQQ": [
                {"etf": "QQQ", "symbol": "NVDA", "name": "NVIDIA Corp", "weight": 0.06,
                 "as_of": "2024-05-31", "source": "issuer", "updated_at": "2024-06-02T00:00:00Z"},
            ],
        }
        self._macro = {
            "prices": [
                {"symbol": "SPX", "name": "S&P 500", "price": 5300.0, "change_pct": 0.5,
                 "updated_at": "2024-06-01T00:00:00Z"},
                {"symbol": "GOLD", "name": "Gold", "price": 2350.0, "change_pct": -0.2,
                 "updated_at": "2024-06-01T00:00:00Z"},
                {"symbol": "US10Y", "name": "10Y", "price": 4.2, "change_pct": -0.1,
                 "updated_at": "2024-06-01T00:00:00Z"},
            ],
            "quotes": [
                {"symbol": "SPX", "price": 5300.0, "change_pct": 0.5,
                 "sparkline": [5290, 5300], "is_live": True, "updated_at": "2024-06-01T00:00:00Z"},
            ],
        }

    # ---- prices ----
    def ohlcv(self, symbol, start=None, end=None):
        rows = self._ohlcv.get(symbol.upper(), [])
        if start:
            rows = [r for r in rows if r["d"] >= start]
        if end:
            rows = [r for r in rows if r["d"] <= end]
        return [dict(r) for r in rows]

    def ohlcv_panel(self, symbols, start=None, end=None):
        resolved = [s.upper() for s in symbols if s.upper() in self._ohlcv]
        if not resolved:
            return [], np.zeros((0, 0)), []
        per = {}
        for s in resolved:
            per[s] = {r["d"]: float(r["c"]) for r in self.ohlcv(s, start, end)}
        common = sorted(set.intersection(*(set(per[s]) for s in resolved)))
        closes = np.array([[per[s][d] for s in resolved] for d in common], dtype=float)
        return common, closes, resolved

    # ---- reference ----
    def universe(self, tracked_only=True):
        rows = self._universe
        if tracked_only:
            rows = [r for r in rows if r.get("tracked")]
        return [dict(r) for r in rows]

    def sectors(self):
        return [dict(r) for r in self._sectors]

    # ---- fundamentals ----
    def fundamentals(self, symbols):
        out = []
        for s in symbols:
            r = self._fundamentals.get(s.upper())
            if r:
                out.append(dict(r))
        return out

    def fundamentals_pit(self, symbol, as_of):
        reports = self._pit.get(symbol.upper(), [])
        eligible = [r for r in reports if str(r["report_date"]) <= str(as_of)]
        if not eligible:
            return None
        return dict(max(eligible, key=lambda r: r["report_date"]))

    # ---- analyst / news / sentiment ----
    def analyst_ratings(self, symbols):
        out = []
        for s in symbols:
            r = self._analyst.get(s.upper())
            if r:
                out.append(dict(r))
        return out

    def news(self, ticker=None, sector=None, limit=50):
        rows = self._news
        if ticker:
            rows = [r for r in rows if ticker.upper() in (r.get("tickers") or [])]
        if sector:
            rows = [r for r in rows if (r.get("sector") or "").lower() == sector.lower()]
        rows = sorted(rows, key=lambda r: r.get("published_at") or "", reverse=True)
        return [dict(r) for r in rows[:limit]]

    def sentiment(self, scope_type, scope):
        r = self._sentiment.get((scope_type, scope.upper())) or self._sentiment.get((scope_type, scope))
        return dict(r) if r else None

    # ---- ownership / flows ----
    def congress_trades(self, ticker=None, member=None, limit=100):
        rows = self._congress
        if ticker:
            rows = [r for r in rows if (r.get("ticker") or "").upper() == ticker.upper()]
        if member:
            rows = [r for r in rows if r.get("member") == member]
        return [dict(r) for r in rows[:limit]]

    def insider_transactions(self, symbol, limit=100):
        return [dict(r) for r in self._insider.get(symbol.upper(), [])[:limit]]

    def inst_holdings(self, ticker=None, cik=None, period=None):
        rows = self._inst_holdings
        if ticker:
            rows = [r for r in rows if (r.get("ticker") or "").upper() == ticker.upper()]
        if cik:
            rows = [r for r in rows if r.get("cik") == cik]
        if period:
            rows = [r for r in rows if str(r.get("period")) == str(period)]
        return [dict(r) for r in rows]

    def inst_filings(self, cik=None, period=None):
        if cik:
            rows = self._inst_filings.get(cik, [])
        else:
            rows = [f for fs in self._inst_filings.values() for f in fs]
        if period:
            rows = [r for r in rows if str(r.get("period")) == str(period)]
        return [dict(r) for r in rows]

    def etf_holdings(self, etf):
        return [dict(r) for r in self._etf_holdings.get(etf.upper(), [])]

    def etf_exposure(self, symbol):
        out = []
        for etf, holds in self._etf_holdings.items():
            for h in holds:
                if (h.get("symbol") or "").upper() == symbol.upper():
                    row = dict(h)
                    out.append(row)
        return out

    # ---- macro ----
    def macro(self):
        return {"prices": [dict(p) for p in self._macro["prices"]],
                "quotes": [dict(q) for q in self._macro["quotes"]]}
