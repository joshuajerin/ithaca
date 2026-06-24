"""Financials skills: income statement, balance sheet, cash flow, earnings transcripts,
earnings calendar, and stock splits — backed by yfinance with optional FMP fallback."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from .archive import ArchiveGateway
from .envelope import (
    envelope,
    warn,
)

ARCHIVE_INPUTS = "doomberg-v1-archive"


def _NOW_ISO() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v: Any) -> float | None:
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


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    try:
        s = str(v)
        return None if s in ("nan", "NaT", "None") else s
    except Exception:
        return None


def _df_val(df: Any, row_label: str, col_idx: int = 0) -> float | None:
    """Extract a single scalar from a yfinance DataFrame by row label and column index."""
    try:
        import pandas as pd  # noqa: F401

        if df is None or df.empty:
            return None
        # yfinance DataFrames have string row-labels and Timestamp columns
        if row_label not in df.index:
            return None
        cols = list(df.columns)
        if col_idx >= len(cols):
            return None
        val = df.at[row_label, cols[col_idx]]
        return _f(val)
    except Exception:
        return None


def _col_date(col: Any) -> str | None:
    """Convert a pandas Timestamp column header to an ISO date string."""
    try:
        return col.date().isoformat()
    except Exception:
        return _safe_str(col)


class FinancialsSkills:
    """Mixin-style class: instances carry an optional archive and are wired into SkillSet."""

    def __init__(self, archive: ArchiveGateway | None = None) -> None:
        self.archive = archive

    @property
    def available(self) -> bool:
        return self.archive is not None

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _yf_ticker(self, symbol: str):  # -> yfinance.Ticker
        try:
            import yfinance as yf

            return yf.Ticker(symbol)
        except ImportError as exc:
            raise RuntimeError("yfinance is required for financials skills") from exc

    def _fmp_get(self, path: str, params: dict | None = None) -> list[dict] | None:
        """GET from FMP free-tier API; returns None when the key is absent."""
        api_key = os.environ.get("FMP_API_KEY")
        if not api_key:
            return None
        base = "https://financialmodelingprep.com/api/v3"
        try:
            r = requests.get(
                f"{base}/{path.lstrip('/')}",
                params={**(params or {}), "apikey": api_key},
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  1. financials.income
    # ------------------------------------------------------------------ #

    def financials_income(self, params: dict) -> dict:
        """Quarterly income statements for a ticker (yfinance + optional FMP fallback).

        Returns revenue, gross profit, operating income, net income, EPS, EBITDA, and
        shares outstanding across up to ``periods`` quarters.
        """
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip()
        if not symbol:
            raise ValueError("financials.income requires a 'symbol'.")
        periods = _i(params.get("periods"), 8, 1, 40)

        statements: list[dict] = []
        warnings: list[dict] = []
        freshness: str | None = None

        # ---- yfinance primary ----
        try:
            ticker = self._yf_ticker(symbol)
            df = ticker.quarterly_income_stmt
            if df is not None and not df.empty:
                cols = list(df.columns)[:periods]
                for col in cols:
                    def _v(label: str) -> float | None:
                        return _df_val(df, label, list(df.columns).index(col))

                    ebitda = _v("EBITDA") or _v("Ebitda")
                    # yfinance uses "Basic EPS" / "Diluted EPS"
                    eps = _v("Diluted EPS") or _v("Basic EPS") or _v("EPS Diluted")
                    statements.append({
                        "period": _col_date(col),
                        "revenue": _v("Total Revenue") or _v("Revenue"),
                        "gross_profit": _v("Gross Profit"),
                        "operating_income": _v("Operating Income") or _v("EBIT"),
                        "net_income": _v("Net Income") or _v("Net Income Common Stockholders"),
                        "eps": eps,
                        "ebitda": ebitda,
                        "shares_outstanding": _v("Diluted Average Shares") or _v("Basic Average Shares"),
                    })
                if statements:
                    freshness = _NOW_ISO()
        except Exception as exc:
            warnings.append(warn("YFINANCE_ERROR", scope=symbol, detail=str(exc)))

        # ---- FMP fallback ----
        if not statements:
            fmp_rows = self._fmp_get(f"income-statement/{symbol}", {"limit": periods, "period": "quarter"})
            if fmp_rows:
                for row in fmp_rows[:periods]:
                    statements.append({
                        "period": row.get("date"),
                        "revenue": _f(row.get("revenue")),
                        "gross_profit": _f(row.get("grossProfit")),
                        "operating_income": _f(row.get("operatingIncome")),
                        "net_income": _f(row.get("netIncome")),
                        "eps": _f(row.get("eps")),
                        "ebitda": _f(row.get("ebitda")),
                        "shares_outstanding": _f(row.get("weightedAverageShsOut")),
                    })
                freshness = _NOW_ISO()
            else:
                warnings.append(warn("NO_DATA", scope=symbol, detail="no income data from yfinance or FMP"))

        data = {"symbol": symbol, "statements": statements}
        return envelope(data, freshness=freshness, warnings=warnings or None)

    # ------------------------------------------------------------------ #
    #  2. financials.balance
    # ------------------------------------------------------------------ #

    def financials_balance(self, params: dict) -> dict:
        """Quarterly balance sheet snapshots for a ticker.

        Returns total assets, total liabilities, equity, cash, debt, and book value per share.
        """
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip()
        if not symbol:
            raise ValueError("financials.balance requires a 'symbol'.")
        periods = _i(params.get("periods"), 8, 1, 40)

        statements: list[dict] = []
        warnings: list[dict] = []
        freshness: str | None = None

        try:
            ticker = self._yf_ticker(symbol)
            df = ticker.quarterly_balance_sheet
            if df is not None and not df.empty:
                cols = list(df.columns)[:periods]
                for col in cols:
                    def _v(label: str, _col=col, _df=df) -> float | None:
                        return _df_val(_df, label, list(_df.columns).index(_col))

                    total_assets = _v("Total Assets")
                    total_liabilities = _v("Total Liabilities Net Minority Interest") or _v("Total Liab")
                    equity = _v("Stockholders Equity") or _v("Total Stockholders Equity") or _v("Common Stock Equity")
                    cash = _v("Cash And Cash Equivalents") or _v("Cash") or _v("Cash Cash Equivalents And Short Term Investments")
                    debt = _v("Total Debt") or _v("Long Term Debt")
                    shares = _v("Ordinary Shares Number") or _v("Share Issued")
                    bvps = (equity / shares) if (equity and shares and shares > 0) else None

                    statements.append({
                        "period": _col_date(col),
                        "total_assets": total_assets,
                        "total_liabilities": total_liabilities,
                        "equity": equity,
                        "cash": cash,
                        "debt": debt,
                        "book_value_per_share": bvps,
                    })
                if statements:
                    freshness = _NOW_ISO()
        except Exception as exc:
            warnings.append(warn("YFINANCE_ERROR", scope=symbol, detail=str(exc)))

        if not statements:
            warnings.append(warn("NO_DATA", scope=symbol, detail="no balance sheet data available"))

        data = {"symbol": symbol, "statements": statements}
        return envelope(data, freshness=freshness, warnings=warnings or None)

    # ------------------------------------------------------------------ #
    #  3. financials.cashflow
    # ------------------------------------------------------------------ #

    def financials_cashflow(self, params: dict) -> dict:
        """Quarterly cash flow statements for a ticker.

        Returns operating, investing, and financing cash flows, plus free cash flow,
        capex, and dividends paid.
        """
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip()
        if not symbol:
            raise ValueError("financials.cashflow requires a 'symbol'.")
        periods = _i(params.get("periods"), 8, 1, 40)

        statements: list[dict] = []
        warnings: list[dict] = []
        freshness: str | None = None

        try:
            ticker = self._yf_ticker(symbol)
            df = ticker.quarterly_cashflow
            if df is not None and not df.empty:
                cols = list(df.columns)[:periods]
                for col in cols:
                    def _v(label: str, _col=col, _df=df) -> float | None:
                        return _df_val(_df, label, list(_df.columns).index(_col))

                    operating_cf = _v("Operating Cash Flow") or _v("Total Cash From Operating Activities")
                    investing_cf = _v("Investing Cash Flow") or _v("Total Cash From Investing Activities") or _v("Total Cashflows From Investing Activities")
                    financing_cf = _v("Financing Cash Flow") or _v("Total Cash From Financing Activities")
                    capex = _v("Capital Expenditure") or _v("Capital Expenditures")
                    free_cf = _v("Free Cash Flow") or (
                        (operating_cf + capex) if (operating_cf is not None and capex is not None) else None
                    )
                    dividends = _v("Common Stock Dividend Paid") or _v("Dividends Paid") or _v("Payment Of Dividends")

                    statements.append({
                        "period": _col_date(col),
                        "operating_cf": operating_cf,
                        "investing_cf": investing_cf,
                        "financing_cf": financing_cf,
                        "free_cf": free_cf,
                        "capex": capex,
                        "dividends_paid": dividends,
                    })
                if statements:
                    freshness = _NOW_ISO()
        except Exception as exc:
            warnings.append(warn("YFINANCE_ERROR", scope=symbol, detail=str(exc)))

        if not statements:
            warnings.append(warn("NO_DATA", scope=symbol, detail="no cash flow data available"))

        data = {"symbol": symbol, "statements": statements}
        return envelope(data, freshness=freshness, warnings=warnings or None)

    # ------------------------------------------------------------------ #
    #  4. earnings.transcript
    # ------------------------------------------------------------------ #

    def earnings_transcript(self, params: dict) -> dict:
        """Earnings call transcript for a ticker/quarter via FMP API (requires FMP_API_KEY).

        When no FMP key is configured, returns a clear error instead of crashing.
        """
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip()
        if not symbol:
            raise ValueError("earnings.transcript requires a 'symbol'.")
        year = params.get("year")
        quarter = params.get("quarter")

        api_key = os.environ.get("FMP_API_KEY")
        if not api_key:
            data = {
                "symbol": symbol,
                "year": year,
                "quarter": quarter,
                "transcript_text": None,
                "date": None,
                "error": "earnings transcripts require FMP_API_KEY",
            }
            return envelope(
                data,
                freshness=None,
                warnings=[warn("CONFIG_MISSING", scope=symbol, detail="FMP_API_KEY not set; transcript unavailable")],
            )

        fmp_params: dict = {}
        if quarter:
            fmp_params["quarter"] = quarter
        if year:
            fmp_params["year"] = year

        rows = self._fmp_get(f"earning_call_transcript/{symbol}", fmp_params)

        if not rows:
            data = {
                "symbol": symbol,
                "year": year,
                "quarter": quarter,
                "transcript_text": None,
                "date": None,
                "error": "no transcript found for the requested period",
            }
            return envelope(
                data,
                freshness=None,
                warnings=[warn("NO_DATA", scope=symbol, detail="FMP returned no transcript")],
            )

        first = rows[0] if isinstance(rows, list) else rows
        data = {
            "symbol": symbol,
            "year": first.get("year", year),
            "quarter": first.get("quarter", quarter),
            "transcript_text": first.get("content"),
            "date": first.get("date"),
        }
        return envelope(data, freshness=_NOW_ISO())

    # ------------------------------------------------------------------ #
    #  5. earnings.calendar
    # ------------------------------------------------------------------ #

    def earnings_calendar(self, params: dict) -> dict:
        """Upcoming earnings dates for one or more symbols (or the full tracked universe).

        Uses yfinance ticker.calendar; falls back to the archive universe for bulk fetches.
        """
        raw_symbols = params.get("symbols")
        days_ahead = _i(params.get("days_ahead"), 30, 1, 365)
        warnings: list[dict] = []
        freshness: str | None = None

        # Resolve symbol list
        if raw_symbols:
            if isinstance(raw_symbols, str):
                symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
            else:
                symbols = [str(s).upper().strip() for s in raw_symbols]
        elif self.archive is not None:
            try:
                uni = self.archive.universe(tracked_only=True)
                symbols = [(r.get("symbol") or "").upper().strip() for r in uni if r.get("symbol")]
            except Exception as exc:
                symbols = []
                warnings.append(warn("ARCHIVE_ERROR", detail=str(exc)))
        else:
            symbols = []
            warnings.append(warn("NO_SYMBOLS", detail="no symbols provided and no archive available"))

        cutoff = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        upcoming: list[dict] = []

        for sym in symbols:
            try:
                ticker = self._yf_ticker(sym)
                cal = ticker.calendar
                if cal is None:
                    continue
                # cal is a dict with keys like "Earnings Date", "EPS Estimate", etc.
                earn_dates = cal.get("Earnings Date") or []
                if not isinstance(earn_dates, list):
                    earn_dates = [earn_dates]
                eps_est = _f(cal.get("EPS Estimate"))
                rev_est = _f(cal.get("Revenue Estimate") or cal.get("Revenue Low"))
                fiscal_q = _safe_str(cal.get("Fiscal Year Ends") or cal.get("Next Fiscal Year End"))

                for ed in earn_dates:
                    try:
                        if hasattr(ed, "isoformat"):
                            ed_dt = ed
                            ed_iso = ed.isoformat()
                        else:
                            ed_dt = datetime.fromisoformat(str(ed)).replace(tzinfo=timezone.utc)
                            ed_iso = ed_dt.isoformat()

                        if hasattr(ed_dt, "tzinfo") and ed_dt.tzinfo is None:
                            ed_dt = ed_dt.replace(tzinfo=timezone.utc)

                        if ed_dt <= cutoff:
                            upcoming.append({
                                "symbol": sym,
                                "date": ed_iso,
                                "eps_estimate": eps_est,
                                "revenue_estimate": rev_est,
                                "fiscal_quarter": fiscal_q,
                            })
                    except Exception:
                        pass
                freshness = _NOW_ISO()
            except Exception as exc:
                warnings.append(warn("YFINANCE_ERROR", scope=sym, detail=str(exc)))

        # Sort by date ascending
        upcoming.sort(key=lambda r: r.get("date") or "")

        data = {"upcoming": upcoming, "count": len(upcoming), "days_ahead": days_ahead}
        return envelope(data, freshness=freshness, warnings=warnings or None)

    # ------------------------------------------------------------------ #
    #  6. stock.splits
    # ------------------------------------------------------------------ #

    def stock_splits(self, params: dict) -> dict:
        """Historical stock splits for a ticker (yfinance).

        Returns each split's date, ratio, and a human-readable description.
        """
        symbol = (params.get("symbol") or params.get("ticker") or "").upper().strip()
        if not symbol:
            raise ValueError("stock.splits requires a 'symbol'.")
        years = _i(params.get("years"), 10, 1, 50)

        warnings: list[dict] = []
        freshness: str | None = None
        splits: list[dict] = []

        try:
            ticker = self._yf_ticker(symbol)
            series = ticker.splits
            if series is not None and not series.empty:
                cutoff_year = datetime.now(timezone.utc).year - years
                for ts, ratio in series.items():
                    try:
                        yr = ts.year if hasattr(ts, "year") else int(str(ts)[:4])
                        if yr < cutoff_year:
                            continue
                        date_str = ts.date().isoformat() if hasattr(ts, "date") else _safe_str(ts)
                        r = _f(ratio)
                        if r is None:
                            continue
                        # Format: "2:1 split" etc. — ratio is the multiplier (e.g. 2.0 = 2-for-1)
                        numer = int(r) if r == int(r) else r
                        description = f"{numer}-for-1 split" if r > 1 else f"1-for-{int(1/r)} reverse split"
                        splits.append({"date": date_str, "ratio": r, "description": description})
                    except Exception:
                        pass
                freshness = _NOW_ISO()
        except Exception as exc:
            warnings.append(warn("YFINANCE_ERROR", scope=symbol, detail=str(exc)))

        if not splits:
            warnings.append(warn("NO_DATA", scope=symbol, detail=f"no splits in the last {years} years"))

        splits.sort(key=lambda r: r.get("date") or "")
        data = {"symbol": symbol, "splits": splits, "total_splits": len(splits)}
        return envelope(data, freshness=freshness, warnings=warnings or None)
