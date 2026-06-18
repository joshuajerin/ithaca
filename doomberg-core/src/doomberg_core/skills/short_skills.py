"""Short interest, short volume, failures-to-deliver, and squeeze screener skills.

``ShortSkills(archive)`` exposes four methods over the v1 archive short-data tables.
When the archive is unavailable (``archive is None``) every method returns an
ARCHIVE_UNAVAILABLE envelope rather than crashing.  When rows are missing from the
archive the methods fall back to yfinance for ``short_interest`` / ``short_screener``
and return empty series for volume / FTD data.
"""
from __future__ import annotations

from typing import Any

from .archive import ArchiveGateway
from .envelope import (
    ARCHIVE_UNAVAILABLE,
    envelope,
    freshness_of,
    warn,
)

__all__ = ["ShortSkills", "SHORT_DDL"]

# ---------------------------------------------------------------------------
# Schema DDL – apply once against the archive Postgres instance
# ---------------------------------------------------------------------------
SHORT_DDL = """
CREATE TABLE IF NOT EXISTS archive.short_interest (
  symbol               text                NOT NULL,
  short_interest_shares bigint,
  float_shares         bigint,
  short_float_pct      double precision,
  days_to_cover        double precision,
  updated_at           timestamptz         NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_short_interest_symbol
  ON archive.short_interest(symbol);

CREATE TABLE IF NOT EXISTS archive.short_volume (
  symbol       text             NOT NULL,
  d            date             NOT NULL,
  short_volume bigint,
  total_volume bigint,
  short_ratio  double precision,
  updated_at   timestamptz      NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_short_volume_symbol_d
  ON archive.short_volume(symbol, d);

CREATE TABLE IF NOT EXISTS archive.ftd (
  symbol     text             NOT NULL,
  d          date             NOT NULL,
  quantity   bigint,
  price      double precision,
  amount     double precision,
  updated_at timestamptz      NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ftd_symbol_d
  ON archive.ftd(symbol, d);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def _squeeze_score(short_float_pct: float | None, days_to_cover: float | None) -> float | None:
    """Simple squeeze heuristic: SI% * DTC / 100 — higher = more coiled."""
    si = _f(short_float_pct)
    dtc = _f(days_to_cover)
    if si is None or dtc is None:
        return None
    return round(si * dtc / 100.0, 4)


# ---------------------------------------------------------------------------
# ShortSkills
# ---------------------------------------------------------------------------
class ShortSkills:
    """Archive-backed short-selling data skills.

    ``archive`` is duck-typed to :class:`~doomberg_core.skills.archive.ArchiveGateway`
    (specifically the ``PgArchiveGateway`` implementation) and may be ``None`` before
    the archive is configured.
    """

    def __init__(self, archive: ArchiveGateway | None):
        self.archive = archive

    # ----------------------------- gate -----------------------------
    @property
    def available(self) -> bool:
        return self.archive is not None

    def _unavailable(self) -> dict:
        return envelope(None, freshness=None, pit=False, warnings=[dict(ARCHIVE_UNAVAILABLE)])

    # ================================================================
    # 1. short_interest
    # ================================================================
    def short_interest(self, params: dict) -> dict:
        """Current short interest snapshot for *symbol*.

        Archive table ``archive.short_interest`` is queried first.  When no rows
        are found the method falls back to ``yfinance`` so callers always get a
        best-effort answer.

        Returns
        -------
        dict
            Envelope whose ``data`` contains:
            symbol, short_interest_shares, float_shares, short_float_pct,
            days_to_cover, updated_at, squeeze_score.
        """
        symbol: str = str(params.get("symbol", "")).upper()
        if not symbol:
            return envelope(None, warnings=[warn("MISSING_PARAM", scope="symbol",
                                                  detail="symbol is required")])

        warnings: list[dict] = []
        rows: list[dict] = []

        if self.available:
            rows = self.archive._rows(
                "SELECT symbol, short_interest_shares, float_shares, "
                "       short_float_pct, days_to_cover, updated_at "
                "FROM archive.short_interest "
                "WHERE symbol = %s "
                "ORDER BY updated_at DESC LIMIT 1",
                (symbol,),
            )

        if not rows:
            # Fall back to yfinance
            try:
                import yfinance as yf  # type: ignore[import]

                info = yf.Ticker(symbol).info
                si_shares = info.get("sharesShort")
                float_sh = info.get("floatShares")
                raw_pct = info.get("shortPercentOfFloat")
                si_pct = round(float(raw_pct) * 100, 4) if raw_pct is not None else None
                dtc = info.get("shortRatio")
                from datetime import datetime, timezone

                updated = datetime.now(timezone.utc).isoformat()
                rows = [
                    {
                        "symbol": symbol,
                        "short_interest_shares": si_shares,
                        "float_shares": float_sh,
                        "short_float_pct": si_pct,
                        "days_to_cover": dtc,
                        "updated_at": updated,
                    }
                ]
                warnings.append(
                    warn("LIVE_FALLBACK", scope=symbol,
                         detail="archive had no rows; data fetched live from yfinance")
                )
            except Exception as exc:  # noqa: BLE001
                return envelope(
                    None,
                    warnings=[warn("FETCH_ERROR", scope=symbol, detail=str(exc))],
                )

        row = rows[0]
        si_pct = _f(row.get("short_float_pct"))
        dtc = _f(row.get("days_to_cover"))
        data = {
            "symbol": row.get("symbol", symbol),
            "short_interest_shares": row.get("short_interest_shares"),
            "float_shares": row.get("float_shares"),
            "short_float_pct": si_pct,
            "days_to_cover": dtc,
            "updated_at": row.get("updated_at"),
            "squeeze_score": _squeeze_score(si_pct, dtc),
        }
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    # ================================================================
    # 2. short_volume
    # ================================================================
    def short_volume(self, params: dict) -> dict:
        """Daily short-volume series for *symbol*.

        Parameters
        ----------
        params : dict
            symbol (str), days (int, default 30, clamped 1–365).
        """
        symbol: str = str(params.get("symbol", "")).upper()
        if not symbol:
            return envelope(None, warnings=[warn("MISSING_PARAM", scope="symbol",
                                                  detail="symbol is required")])

        days: int = _i(params.get("days", 30), 30, 1, 365)
        warnings: list[dict] = []

        if not self.available:
            return self._unavailable()

        rows = self.archive._rows(
            "SELECT symbol, d, short_volume, total_volume, short_ratio, updated_at "
            "FROM archive.short_volume "
            "WHERE symbol = %s "
            "ORDER BY d DESC LIMIT %s",
            (symbol, days),
        )

        if not rows:
            warnings.append(warn("NO_DATA", scope=symbol,
                                 detail="no short volume records in archive"))

        # Reverse to chronological order for the series
        series = [
            {
                "date": r.get("d"),
                "short_volume": r.get("short_volume"),
                "total_volume": r.get("total_volume"),
                "short_ratio": _f(r.get("short_ratio")),
            }
            for r in reversed(rows)
        ]

        # 30-day average ratio
        ratios = [_f(s["short_ratio"]) for s in series if _f(s["short_ratio"]) is not None]
        avg_ratio = round(sum(ratios) / len(ratios), 4) if ratios else None

        # Simple trend: compare first-half avg vs second-half avg
        trend: str | None = None
        if len(ratios) >= 4:
            mid = len(ratios) // 2
            first_half = sum(ratios[:mid]) / mid
            second_half = sum(ratios[mid:]) / (len(ratios) - mid)
            if second_half > first_half * 1.05:
                trend = "increasing"
            elif second_half < first_half * 0.95:
                trend = "decreasing"
            else:
                trend = "flat"

        data = {
            "symbol": symbol,
            "series": series,
            "avg_ratio_30d": avg_ratio,
            "trend": trend,
        }
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    # ================================================================
    # 3. failures_to_deliver
    # ================================================================
    def failures_to_deliver(self, params: dict) -> dict:
        """SEC failures-to-deliver records for *symbol*.

        Parameters
        ----------
        params : dict
            symbol (str), limit (int, default 20, clamped 1–500).
        """
        symbol: str = str(params.get("symbol", "")).upper()
        if not symbol:
            return envelope(None, warnings=[warn("MISSING_PARAM", scope="symbol",
                                                  detail="symbol is required")])

        limit: int = _i(params.get("limit", 20), 20, 1, 500)
        warnings: list[dict] = []

        if not self.available:
            return self._unavailable()

        rows = self.archive._rows(
            "SELECT symbol, d, quantity, price, amount, updated_at "
            "FROM archive.ftd "
            "WHERE symbol = %s "
            "ORDER BY d DESC LIMIT %s",
            (symbol, limit),
        )

        if not rows:
            warnings.append(warn("NO_DATA", scope=symbol,
                                 detail="no FTD records in archive for this symbol"))

        records = [
            {
                "date": r.get("d"),
                "quantity": r.get("quantity"),
                "price": _f(r.get("price")),
                "amount": _f(r.get("amount")),
            }
            for r in rows
        ]

        total_quantity = sum(r["quantity"] for r in records if r["quantity"] is not None)
        total_amount = sum(r["amount"] for r in records if r["amount"] is not None)
        last_date = records[0]["date"] if records else None

        data = {
            "symbol": symbol,
            "ftd_records": records,
            "total_quantity": total_quantity,
            "total_amount": round(total_amount, 2),
            "last_date": last_date,
        }
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    # ================================================================
    # 4. short_screener
    # ================================================================
    def short_screener(self, params: dict) -> dict:
        """Screen for high-short-interest squeeze candidates.

        Parameters
        ----------
        params : dict
            min_si_pct (float, default 20) — minimum short-float %.
            max_days_to_cover (float | None) — optional DTC ceiling.
            sector (str | None) — optional sector filter.
            limit (int, default 50, clamped 1–500).

        Returns
        -------
        dict
            Envelope whose ``data`` contains a ``screener`` list ranked by
            ``squeeze_potential = short_float_pct * days_to_cover``.
        """
        min_si: float = float(params.get("min_si_pct", 20.0))
        max_dtc: float | None = _f(params.get("max_days_to_cover"))
        sector: str | None = params.get("sector")
        limit: int = _i(params.get("limit", 50), 50, 1, 500)
        warnings: list[dict] = []

        if not self.available:
            return self._unavailable()

        # Build query with optional sector join
        clauses = ["si.short_float_pct >= %s"]
        qparams: list[Any] = [min_si]

        if max_dtc is not None:
            clauses.append("si.days_to_cover <= %s")
            qparams.append(max_dtc)

        where_clause = " AND ".join(clauses)

        if sector:
            sql = (
                "SELECT si.symbol, si.short_float_pct, si.days_to_cover, "
                "       u.sector, u.name, si.updated_at "
                "FROM archive.short_interest si "
                "LEFT JOIN archive.universe u ON u.symbol = si.symbol "
                f"WHERE {where_clause} AND u.sector = %s "
                "ORDER BY si.short_float_pct * COALESCE(si.days_to_cover, 0) DESC "
                "LIMIT %s"
            )
            qparams.extend([sector, limit])
        else:
            sql = (
                "SELECT si.symbol, si.short_float_pct, si.days_to_cover, "
                "       u.sector, u.name, si.updated_at "
                "FROM archive.short_interest si "
                "LEFT JOIN archive.universe u ON u.symbol = si.symbol "
                f"WHERE {where_clause} "
                "ORDER BY si.short_float_pct * COALESCE(si.days_to_cover, 0) DESC "
                "LIMIT %s"
            )
            qparams.append(limit)

        rows = self.archive._rows(sql, qparams)

        # If archive is empty, fall back to yfinance for a basic universe
        if not rows:
            warnings.append(
                warn("LIVE_FALLBACK", scope="short_screener",
                     detail="archive.short_interest is empty; fetching live from yfinance")
            )
            try:
                rows = self._screener_yf_fallback(min_si, max_dtc, sector, limit)
            except Exception as exc:  # noqa: BLE001
                warnings.append(warn("FETCH_ERROR", scope="short_screener", detail=str(exc)))
                rows = []

        screener = []
        for r in rows:
            si_pct = _f(r.get("short_float_pct"))
            dtc = _f(r.get("days_to_cover"))
            squeeze_potential = round(si_pct * dtc, 2) if si_pct is not None and dtc is not None else None
            screener.append(
                {
                    "symbol": r.get("symbol"),
                    "short_float_pct": si_pct,
                    "days_to_cover": dtc,
                    "squeeze_potential": squeeze_potential,
                    "sector": r.get("sector"),
                    "name": r.get("name"),
                }
            )

        data = {"screener": screener}
        return envelope(data, freshness=freshness_of(rows), warnings=warnings)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _screener_yf_fallback(
        self,
        min_si: float,
        max_dtc: float | None,
        sector: str | None,
        limit: int,
    ) -> list[dict]:
        """Fetch short interest for universe symbols via yfinance and filter."""
        import yfinance as yf  # type: ignore[import]
        from datetime import datetime, timezone

        # Pull universe symbols from archive if available, else use a small default set
        universe_symbols: list[str] = []
        if self.available:
            try:
                universe_rows = self.archive._rows(
                    "SELECT symbol FROM archive.universe ORDER BY symbol"
                )
                universe_symbols = [r["symbol"] for r in universe_rows if r.get("symbol")]
            except Exception:
                pass

        if not universe_symbols:
            # Minimal fallback universe — covers well-known high-SI names
            universe_symbols = [
                "GME", "AMC", "BBBY", "WISH", "CLOV", "SPCE", "MVIS",
                "NAKD", "SNDL", "TLRY", "EXPR", "KOSS",
            ]

        results: list[dict] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for sym in universe_symbols:
            if len(results) >= limit:
                break
            try:
                info = yf.Ticker(sym).info
                raw_pct = info.get("shortPercentOfFloat")
                if raw_pct is None:
                    continue
                si_pct = float(raw_pct) * 100
                dtc = info.get("shortRatio")

                if si_pct < min_si:
                    continue
                if max_dtc is not None and dtc is not None and float(dtc) > max_dtc:
                    continue

                results.append(
                    {
                        "symbol": sym,
                        "short_float_pct": si_pct,
                        "days_to_cover": dtc,
                        "sector": info.get("sector"),
                        "name": info.get("shortName") or info.get("longName"),
                        "updated_at": now_iso,
                    }
                )
            except Exception:
                continue

        # Sort by squeeze_potential descending
        results.sort(
            key=lambda r: (
                (_f(r.get("short_float_pct")) or 0.0) * (_f(r.get("days_to_cover")) or 0.0)
            ),
            reverse=True,
        )
        return results[:limit]
