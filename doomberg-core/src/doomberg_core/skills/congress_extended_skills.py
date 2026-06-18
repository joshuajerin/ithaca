"""Congress extended skills: politician portfolio reconstruction, late filing detection,
and a congress member screener — backed by archive.congress_trades + optional live feeds."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from .archive import ArchiveGateway
from .envelope import (
    ARCHIVE_UNAVAILABLE,
    computed_envelope,
    envelope,
    freshness_of,
    warn,
)

ARCHIVE_INPUTS = "doomberg-v1-archive"

_NOW_ISO = lambda: datetime.now(timezone.utc).isoformat()


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


def _lag_days(txn_date: Any, disc_date: Any) -> int | None:
    """Calendar days between a transaction date and its disclosure date."""
    try:
        fmt = "%Y-%m-%d"
        t = datetime.strptime(str(txn_date)[:10], fmt)
        d = datetime.strptime(str(disc_date)[:10], fmt)
        return (d - t).days
    except Exception:
        return None


def _txn_type(raw: str | None) -> str:
    """Normalise raw transaction-type strings to buy / sell / exchange / other."""
    if not raw:
        return "other"
    txn = raw.lower()
    if "buy" in txn or txn == "purchase":
        return "buy"
    if "sell" in txn or "sale" in txn:
        return "sell"
    if "exchange" in txn:
        return "exchange"
    return txn


class CongressExtendedSkills:
    """Mixin-style class: instances carry an optional archive and are wired into SkillSet."""

    def __init__(self, archive: ArchiveGateway | None = None) -> None:
        self.archive = archive

    @property
    def available(self) -> bool:
        return self.archive is not None

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _unavailable(self) -> dict:
        return envelope(None, freshness=None, pit=False, warnings=[dict(ARCHIVE_UNAVAILABLE)])

    def _yf_price(self, symbol: str) -> float | None:
        """Fetch the latest close price via yfinance; returns None on any error."""
        try:
            import yfinance as yf

            t = yf.Ticker(symbol)
            hist = t.history(period="2d")
            if hist is not None and not hist.empty:
                return _f(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def _quiver_congress(self) -> list[dict] | None:
        """Fetch bulk congress trading data from Quiver Quant free API."""
        try:
            r = requests.get(
                "https://api.quiverquant.com/beta/bulk/CongressTrading",
                headers={"accept": "application/json"},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  1. congress.politician_portfolio
    # ------------------------------------------------------------------ #

    def politician_portfolio(self, params: dict) -> dict:
        """Reconstruct the estimated current portfolio of a named Congress member.

        Aggregates all archived buy and sell disclosures by ticker to compute net direction
        (long vs exited) and optionally estimates a current market value via yfinance.
        """
        if not self.available:
            return self._unavailable()

        name = (params.get("name") or "").strip()
        if not name:
            raise ValueError("congress.politician_portfolio requires a 'name'.")

        # Pull all trades for this politician (no ticker filter, high limit)
        rows = self.archive.congress_trades(member=name, limit=500)

        if not rows:
            data = {
                "name": name,
                "portfolio": [],
                "total_tickers": 0,
                "note": "No trades found for this politician in the archive.",
            }
            return envelope(
                data,
                freshness=None,
                warnings=[warn("NO_DATA", scope=name, detail="no archive rows for member")],
            )

        # Aggregate by ticker
        by_ticker: dict[str, dict] = defaultdict(lambda: {
            "buys": 0, "sells": 0, "exchanges": 0,
            "buy_amount_low": 0.0, "sell_amount_low": 0.0,
            "last_date": None, "last_type": None,
        })

        for r in rows:
            ticker = (r.get("ticker") or "").upper().strip()
            if not ticker:
                continue
            txn = _txn_type(r.get("txn_type"))
            agg = by_ticker[ticker]

            if txn == "buy":
                agg["buys"] += 1
                agg["buy_amount_low"] += _f(r.get("amount_low")) or 0.0
            elif txn == "sell":
                agg["sells"] += 1
                agg["sell_amount_low"] += _f(r.get("amount_low")) or 0.0
            elif txn == "exchange":
                agg["exchanges"] += 1

            txn_date = r.get("transaction_date")
            if txn_date and (agg["last_date"] is None or str(txn_date) > str(agg["last_date"])):
                agg["last_date"] = txn_date
                agg["last_type"] = txn

        # Build portfolio rows; optionally enrich with current prices
        portfolio = []
        for ticker, agg in sorted(by_ticker.items()):
            net_buy = agg["buys"] - agg["sells"]
            direction = "long" if net_buy > 0 else ("exited" if net_buy < 0 else "flat")

            current_price = self._yf_price(ticker) if ticker else None
            # Rough estimated value: net buy amount (mid-point of ranges used)
            estimated_value = (agg["buy_amount_low"] - agg["sell_amount_low"]) or None

            portfolio.append({
                "ticker": ticker,
                "net_transactions": net_buy,
                "buys": agg["buys"],
                "sells": agg["sells"],
                "exchanges": agg["exchanges"],
                "estimated_direction": direction,
                "last_transaction_date": str(agg["last_date"]) if agg["last_date"] else None,
                "last_transaction_type": agg["last_type"],
                "estimated_net_amount_low": estimated_value,
                "current_price": current_price,
            })

        # Sort by most recent activity
        portfolio.sort(key=lambda r: r.get("last_transaction_date") or "", reverse=True)

        data = {
            "name": name,
            "portfolio": portfolio,
            "total_tickers": len(portfolio),
            "long_positions": sum(1 for r in portfolio if r["estimated_direction"] == "long"),
            "exited_positions": sum(1 for r in portfolio if r["estimated_direction"] == "exited"),
        }
        return envelope(data, freshness=freshness_of(rows))

    # ------------------------------------------------------------------ #
    #  2. congress.late_filings
    # ------------------------------------------------------------------ #

    def congress_late_filings(self, params: dict) -> dict:
        """Members who filed their STOCK Act disclosures more than 45 days after the trade.

        Primary source: Quiver Quant bulk API. Fallback: archive.congress_trades lag filter.
        """
        if not self.available:
            return self._unavailable()

        days = _i(params.get("days"), 365, 1, 3650)
        limit = _i(params.get("limit"), 50, 1, 500)
        warnings: list[dict] = []
        late_filings: list[dict] = []
        used_rows: list[dict] = []

        # ---- Quiver Quant live feed ----
        quiver_rows = self._quiver_congress()
        if quiver_rows:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            for row in quiver_rows:
                txn_date_raw = row.get("TransactionDate") or row.get("Date")
                disc_date_raw = row.get("DisclosureDate") or row.get("Filed")
                if not txn_date_raw or not disc_date_raw:
                    continue
                lag = _lag_days(txn_date_raw, disc_date_raw)
                if lag is None or lag <= 45:
                    continue
                # Date filter
                try:
                    txn_dt = datetime.strptime(str(txn_date_raw)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if txn_dt < cutoff_date:
                        continue
                except Exception:
                    pass
                late_filings.append({
                    "member": row.get("Representative") or row.get("Name"),
                    "ticker": (row.get("Ticker") or "").upper(),
                    "transaction_date": str(txn_date_raw)[:10],
                    "disclosure_date": str(disc_date_raw)[:10],
                    "days_late": lag,
                    "amount": row.get("Range") or row.get("Amount"),
                    "transaction_type": _txn_type(row.get("Transaction") or row.get("Type")),
                })
        else:
            warnings.append(warn("QUIVER_UNAVAILABLE", detail="Quiver Quant API unavailable; using archive"))

            # ---- Archive fallback ----
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            # Pull a large batch and filter in Python
            archive_rows = self.archive.congress_trades(ticker=None, member=None, limit=2000)
            used_rows = archive_rows
            for r in archive_rows:
                txn_date_raw = r.get("transaction_date")
                disc_date_raw = r.get("disclosure_date")
                if not txn_date_raw or not disc_date_raw:
                    continue
                lag = _lag_days(txn_date_raw, disc_date_raw)
                if lag is None or lag <= 45:
                    continue
                try:
                    txn_dt = datetime.strptime(str(txn_date_raw)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if txn_dt < cutoff_date:
                        continue
                except Exception:
                    pass
                late_filings.append({
                    "member": r.get("member"),
                    "ticker": (r.get("ticker") or "").upper(),
                    "transaction_date": str(txn_date_raw)[:10],
                    "disclosure_date": str(disc_date_raw)[:10],
                    "days_late": lag,
                    "amount": r.get("amount_range"),
                    "transaction_type": _txn_type(r.get("txn_type")),
                })

        # Sort by days_late desc, apply limit
        late_filings.sort(key=lambda r: r.get("days_late") or 0, reverse=True)
        late_filings = late_filings[:limit]

        lags = [r["days_late"] for r in late_filings if isinstance(r.get("days_late"), int)]
        avg_lag = round(sum(lags) / len(lags), 1) if lags else None
        members = {r["member"] for r in late_filings if r.get("member")}

        data = {
            "late_filings": late_filings,
            "count": len(late_filings),
            "unique_members": len(members),
            "avg_days_late": avg_lag,
            "max_days_late": max(lags) if lags else None,
            "days_window": days,
            "note": ("STOCK Act requires disclosure within ~45 days of a transaction. "
                     "These filings exceeded that threshold."),
        }
        return envelope(data, freshness=freshness_of(used_rows) or _NOW_ISO(), warnings=warnings or None)

    # ------------------------------------------------------------------ #
    #  3. congress.screener
    # ------------------------------------------------------------------ #

    def congress_screener(self, params: dict) -> dict:
        """Rank Congress members by trading activity and stats from the archive.

        Returns each member's trade count, unique tickers, most-traded names, and last trade date.
        Sort options: total_trades, active_tickers, last_trade_date (default: total_trades).
        """
        if not self.available:
            return self._unavailable()

        min_trades = _i(params.get("min_trades"), 5, 1, 1000)
        sort_by = (params.get("sort_by") or "total_trades").strip().lower()
        limit = _i(params.get("limit"), 50, 1, 500)

        # Pull all trades (large batch for aggregation)
        rows = self.archive.congress_trades(ticker=None, member=None, limit=5000)

        # Aggregate per politician
        stats: dict[str, dict] = defaultdict(lambda: {
            "chamber": None, "party": None,
            "total_trades": 0, "buys": 0, "sells": 0,
            "tickers": defaultdict(int),
            "last_trade_date": None,
        })

        for r in rows:
            member = (r.get("member") or "").strip()
            if not member:
                continue
            agg = stats[member]
            # Capture chamber/party from first seen row
            if agg["chamber"] is None and r.get("chamber"):
                agg["chamber"] = r["chamber"]
            if agg["party"] is None and r.get("party") or r.get("party_code"):
                agg["party"] = r.get("party") or r.get("party_code")

            agg["total_trades"] += 1
            txn = _txn_type(r.get("txn_type"))
            if txn == "buy":
                agg["buys"] += 1
            elif txn == "sell":
                agg["sells"] += 1

            ticker = (r.get("ticker") or "").upper().strip()
            if ticker:
                agg["tickers"][ticker] += 1

            txn_date = r.get("transaction_date")
            if txn_date and (agg["last_trade_date"] is None or
                             str(txn_date) > str(agg["last_trade_date"])):
                agg["last_trade_date"] = txn_date

        # Build output rows
        politicians: list[dict] = []
        for name, agg in stats.items():
            if agg["total_trades"] < min_trades:
                continue
            tickers_sorted = sorted(agg["tickers"].items(), key=lambda x: x[1], reverse=True)
            most_traded = [t for t, _ in tickers_sorted[:5]]
            politicians.append({
                "name": name,
                "chamber": agg["chamber"],
                "party": agg["party"],
                "total_trades": agg["total_trades"],
                "buys": agg["buys"],
                "sells": agg["sells"],
                "active_tickers": len(agg["tickers"]),
                "most_traded_tickers": most_traded,
                "last_trade_date": str(agg["last_trade_date"]) if agg["last_trade_date"] else None,
            })

        # Sort
        valid_sorts = {"total_trades", "active_tickers", "last_trade_date"}
        if sort_by not in valid_sorts:
            sort_by = "total_trades"

        if sort_by == "last_trade_date":
            politicians.sort(key=lambda r: r.get("last_trade_date") or "", reverse=True)
        else:
            politicians.sort(key=lambda r: r.get(sort_by) or 0, reverse=True)

        politicians = politicians[:limit]

        data = {
            "politicians": politicians,
            "count": len(politicians),
            "sort_by": sort_by,
            "min_trades_filter": min_trades,
            "total_trades_in_archive": len(rows),
        }
        return envelope(data, freshness=freshness_of(rows))
